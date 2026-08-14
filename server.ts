import "dotenv/config";
import { FastMCP, UserError } from "fastmcp";
import { z } from "zod";
import http from "http";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV_PATH = path.join(__dirname, ".env");

const BACKEND_URL = process.env.BACKEND_URL || "http://172.21.208.142:5000";
export const TOKEN_PORT = parseInt(process.env.TOKEN_PORT || "3099");

let ACCESS_TOKEN = process.env.ACCESS_TOKEN || "";

// Redirect logs to stderr so stdout stays clean for MCP protocol (stdio transport)
const log = (...args: any[]) => console.error("[mcp]", ...args);

// ── Save token to .env ──
function saveToken(token: string) {
  const envContent = fs.existsSync(ENV_PATH) ? fs.readFileSync(ENV_PATH, "utf8") : "";
  const lines = envContent.split("\n").filter(l => l.trim());
  const updated: string[] = [];
  let found = false;
  for (const line of lines) {
    if (line.startsWith("ACCESS_TOKEN=")) {
      updated.push(`ACCESS_TOKEN=${token}`);
      found = true;
    } else {
      updated.push(line);
    }
  }
  if (!found) updated.push(`ACCESS_TOKEN=${token}`);
  fs.writeFileSync(ENV_PATH, updated.join("\n") + "\n");
  ACCESS_TOKEN = token;
  log(`Token saved: ${token.substring(0, 16)}...`);
  // Notify subscribed MCP clients that the token changed
  try { server.sendResourceUpdated("onscript://token-status"); } catch {}
}

// ── Token server ──
export const tokenServer = http.createServer((req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") { res.writeHead(200); res.end(); return; }
  if (req.method === "POST" && req.url === "/token") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const { access_token } = JSON.parse(body);
        if (!access_token) {
          log("Token server: no access_token");
          res.writeHead(400); res.end("No token"); return;
        }
        saveToken(access_token);
        res.writeHead(200); res.end("ok");
      } catch {
        log("Token server: bad JSON");
        res.writeHead(400); res.end("Bad JSON");
      }
    });
    return;
  }
  res.writeHead(404); res.end("not found");
});

tokenServer.on("error", (e: any) => {
  if (e.code === "EADDRINUSE") log(`Token port ${TOKEN_PORT} in use`);
  else log("Token server error:", e.message);
});

// ── Call backend ──
async function api(path: string, options: RequestInit = {}) {
  if (!ACCESS_TOKEN) {
    log("No access token — sign in to webapp");
    throw new UserError("No access token. Sign in to the webapp first.");
  }
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${ACCESS_TOKEN}`, ...options.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    if (res.status === 401) throw new UserError("Token expired. Sign in again.");
    if (res.status === 402) throw new UserError("Plan limit reached.");
    throw new UserError(`Backend error ${res.status}: ${body}`);
  }
  return res.json();
}

// ── MCP Server ──
export const server = new FastMCP({ name: "onscript", version: "0.1.0" });

server.addTool({
  name: "get_profile", description: "View your OnScript profile",
  parameters: z.object({}),
  execute: async () => ({ content: [{ type: "text" as const, text: JSON.stringify(await api("/users/profile"), null, 2) }] }),
});

server.addTool({
  name: "create_post", description: "Create a post on OnScript. Detects connected accounts automatically.",
  parameters: z.object({
    content: z.string().describe("Post content text"),
    status: z.enum(["DRAFT", "PUBLISHING", "SCHEDULED"]).describe("DRAFT saves without posting, PUBLISHING posts immediately, SCHEDULED requires scheduled_at"),
    scheduled_at: z.number().optional().describe("Unix epoch in seconds. Required if status is SCHEDULED"),
  }),
  execute: async ({ content, status, scheduled_at }) => {
    // Fetch connected accounts to get platform + connected_account_id
    const accounts: any[] = await api("/integrations/connected-accounts");
    const active = accounts.filter((a: any) => a.is_active);
    if (active.length === 0) throw new UserError("No connected social accounts. Connect one in the webapp first.");
    const primary = active.find((a: any) => a.is_primary) || active[0];
    const platformMap: Record<string, string> = {
      twitter: "TWITTER", x: "TWITTER", linkedin: "LINKEDIN", farcaster: "FARCASTER",
      facebook: "FACEBOOK", instagram: "INSTAGRAM", youtube: "YOUTUBE", tiktok: "TIKTOK",
    };
    const platformName = platformMap[primary.platform.toLowerCase()] || primary.platform.toUpperCase();
    const body: any = {
      status,
      platforms: [{ platform: platformName, connected_account_id: primary.id, text: content, media_ids: [] }],
    };
    if (status === "SCHEDULED") {
      if (!scheduled_at) throw new UserError("scheduled_at (unix seconds) is required for SCHEDULED posts");
      body.scheduled_at = scheduled_at;
    }
    return { content: [{ type: "text" as const, text: JSON.stringify(await api("/posts", { method: "POST", body: JSON.stringify(body) }), null, 2) }] };
  },
});

server.addTool({
  name: "list_posts", description: "List your posts",
  parameters: z.object({
    limit: z.number().optional().describe("Number of posts"),
    status: z.string().optional().describe("Filter by status"),
  }),
  execute: async ({ limit, status }) => {
    const p = new URLSearchParams();
    if (limit) p.set("limit", String(limit));
    if (status) p.set("status", status);
    return { content: [{ type: "text" as const, text: JSON.stringify(await api(`/posts?${p}`), null, 2) }] };
  },
});

server.addTool({
  name: "get_post", description: "Get a specific post",
  parameters: z.object({ post_id: z.string().describe("Post ID") }),
  execute: async ({ post_id }) => ({ content: [{ type: "text" as const, text: JSON.stringify(await api(`/posts/${post_id}`), null, 2) }] }),
});

server.addTool({
  name: "get_connected_accounts", description: "See connected social platforms",
  parameters: z.object({}),
  execute: async () => ({ content: [{ type: "text" as const, text: JSON.stringify(await api("/integrations/connected-accounts"), null, 2) }] }),
});

server.addTool({
  name: "get_analytics", description: "View posting analytics",
  parameters: z.object({ period: z.string().optional().describe("Time period (7d, 30d, 90d)") }),
  execute: async ({ period }) => ({ content: [{ type: "text" as const, text: JSON.stringify(await api(`/users/profile/analytics${period ? `?period=${period}` : ""}`), null, 2) }] }),
});

// ── Token status resource (notifies subscribed clients on change) ──
server.addResource({
  name: "token-status",
  uri: "onscript://token-status",
  description: "Current authentication token status",
  load: async () => ({
    text: JSON.stringify({ hasToken: !!ACCESS_TOKEN, lastUpdated: new Date().toISOString() }),
    mimeType: "application/json",
  }),
});

server.addTool({
  name: "check_token", description: "Check if authentication token is set",
  parameters: z.object({}),
  execute: async () => ({ content: [{ type: "text" as const, text: JSON.stringify({ hasToken: !!ACCESS_TOKEN }, null, 2) }] }),
});

// ── Start entry points ──
// server.ts: no auto-start — inspector / start-http.ts handle transport

if (ACCESS_TOKEN) {
  log(`Token loaded: ${ACCESS_TOKEN.substring(0, 16)}...`);
} else {
  log("No token — sign in to webapp to send one");
}
