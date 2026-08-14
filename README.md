# Onscript MCP Server

MCP (Model Context Protocol) server that lets AI agents interact with Onscript user accounts via natural language.

**Repo:** `OnscriptSocialFi/MCP`
**Production URL:** `https://mcp.onscript.xyz/mcp`
**Get Started page:** `https://onscript.xyz/mcp-get-started`

---

## What This Does

AI agents (Claude Desktop, Cursor, VS Code, ChatGPT, Windsurf, Claude Code) connect to this server and use tools to manage a user's Onscript account — creating posts, checking analytics, viewing connected platforms.

The user authorizes via OAuth in their browser. The MCP server then makes authenticated calls to the Onscript backend API on their behalf.

---

## Architecture

```
AI Agent (Claude Desktop, Cursor, etc.)
  → MCP Server (mcp.onscript.xyz/mcp)
    → Onscript Backend API (localhost:5000)
      → Social platforms (Twitter, LinkedIn, Farcaster, etc.)
```

**Three components:**
1. **MCP Server** (`server.ts`) — fastMCP + zod, HTTP transport, 8 tools
2. **Token Server** (same process, port 3099) — receives tokens from webapp frontend
3. **Frontend** (webappv2) — auto-sends token on sign-in, periodic sync every 20 min

---

## Tools

| Tool | Description |
|---|---|
| `get_profile` | View OnScript profile |
| `create_post` | Create draft, published, or scheduled posts |
| `list_posts` | List posts with filters |
| `get_post` | Get specific post details |
| `get_connected_accounts` | See connected social platforms |
| `get_analytics` | View posting analytics |
| `check_token` | Check if auth token is set |

---

## Token Flow (Frontend → MCP Server)

This is how the MCP server gets and keeps the user's auth token.

### On Sign-In

```
User signs in (OTP verification)
  → useAuth.ts: verifyOTP() receives access_token from backend
  → sendTokenToMCPServer(token) — POST to localhost:3099/token
  → MCP server: saveToken() — updates ACCESS_TOKEN in memory + writes to .env
  → startPeriodicTokenSync(token) — pushes token every 20 min
```

### Three Mechanisms Keep Token Fresh

1. **Immediate send** — on sign-in, token is sent to MCP server right away
2. **Retry on failure** — if MCP server is offline, retry every 5 min for 50 min (tries ports 3099-3103)
3. **Periodic sync** — every 20 min, push token to MCP server (runs until sign-out)

### Why Periodic Sync Is Needed

- Retry stops after 50 minutes — if user signs in again later, no retry running
- MCP server may restart and load old `.env`
- Periodic sync ensures MCP server always has latest token

### Key Functions

**Frontend (`src/hooks/useAuth.ts`):**
- `sendTokenToMCPServer(token)` — tries ports 3099-3103, returns boolean
- `startTokenRetry(token)` — retry every 5 min for 50 min on failure
- `startPeriodicTokenSync(token)` — push every 20 min until sign-out
- `clearTokenRetry()` — clears both retry and periodic sync (called on sign-out)

**MCP Server (`server.ts`):**
- `saveToken(token)` — writes to `.env` + updates `ACCESS_TOKEN` in memory + sends `sendResourceUpdated` notification
- `tokenServer` — HTTP server on port 3099, receives POST `/token`

### Token Refresh in MCP Server

When the MCP server receives a new token, it:
1. Saves to `.env` (for restart persistence)
2. Updates `ACCESS_TOKEN` in memory (immediate effect — next tool call uses new token)
3. Calls `server.sendResourceUpdated("onscript://token-status")` — notifies subscribed MCP clients

The token is live in memory the moment `saveToken()` runs. No disconnect/reconnect needed for tool calls. The `sendResourceUpdated` notification is the MCP-idiomatic way to tell clients to re-read.

---

## Running Locally

### Prerequisites

- Node.js 18+
- Backend running at `http://172.21.208.142:5000` (or whatever your WSL IP is)

### Setup

```bash
cd MCP
npm install
cp .env.example .env  # or create .env manually
```

### .env

```
BACKEND_URL=http://172.21.208.142:5000
ACCESS_TOKEN=your_token_here
TOKEN_PORT=3099
MCP_SERVER_PORT=3000
```

### Start

```bash
# HTTP mode (for production / Claude Desktop)
npx tsx start-http.ts

# Stdio mode (for testing / opencode)
npx tsx start-stdio.ts
```

### Test

```bash
# Start server
cd MCP && npx tsx server.ts

# Test MCP connection
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

---

## Backend Endpoints Used

The MCP server calls these Onscript backend endpoints:

| MCP Tool | Backend Endpoint | Method |
|---|---|---|
| `get_profile` | `/users/profile` | GET |
| `create_post` | `/integrations/connected-accounts` + `/posts` | GET + POST |
| `list_posts` | `/posts` | GET |
| `get_post` | `/posts/{id}` | GET |
| `get_connected_accounts` | `/integrations/connected-accounts` | GET |
| `get_analytics` | `/users/profile/analytics` | GET |
| `check_token` | (no backend call) | — |

All endpoints require `Authorization: Bearer <token>` header.

---

## OAuth 2.1 Flow (Claude Connectors)

This is how users authorize Claude Desktop (or any MCP client) to access their Onscript account.

### The Flow

```
Claude Desktop                    Backend (mcp.onscript.xyz)              Frontend (app.onscript.xyz)
     |                                    |                                      |
     |-- GET /mcp/authorize ----------->  |                                      |
     |   (no token yet)                   |                                      |
     |                                    |-- 401 + WWW-Authenticate ----------> |
     |                                    |   (points to .well-known metadata)   |
     |                                    |                                      |
     |-- GET /.well-known/... ---------->|                                      |
     |<-- { auth server URL } -----------|                                      |
     |                                    |                                      |
     |-- GET /mcp/authorize?state=... -->|------------------------------------->|
     |                                    |   (consent page in browser)          |
     |                                    |                                      |
     |                                    |<-- POST /auth/mcp/authorize --------|
     |                                    |    (issues authorization code)       |
     |                                    |                                      |
     |-- POST /auth/mcp/token ---------->|
     |   { code, code_verifier }         |
     |<-- { access_token, refresh_token }|                                      |
     |                                    |                                      |
     |-- Bearer token on all requests -->|
```

### Routes to Build

| Route | Method | What It Does | Status |
|---|---|---|---|
| `/.well-known/oauth-protected-resource` | GET | Static JSON — tells Claude where to auth | [TODO #269](https://github.com/OnscriptSocialFi/backend/issues/269) |
| `/.well-known/oauth-authorization-server` | GET | Static JSON — auth server endpoints | [TODO #269](https://github.com/OnscriptSocialFi/backend/issues/269) |
| `/auth/mcp/authorize` | GET | Show consent page (redirect to frontend) | [TODO #268](https://github.com/OnscriptSocialFi/backend/issues/268) |
| `/auth/mcp/authorize` | POST | Issue authorization code, redirect back to Claude | [TODO #268](https://github.com/OnscriptSocialFi/backend/issues/268) |
| `/auth/mcp/token` | POST | Exchange code + PKCE for access_token + refresh_token | [TODO #268](https://github.com/OnscriptSocialFi/backend/issues/268) |
| `/auth/mcp/refresh` | POST | Exchange refresh_token for new access_token | [TODO #268](https://github.com/OnscriptSocialFi/backend/issues/268) |
| `/auth/mcp/revoke` | POST | Revoke tokens (user disconnects) | [TODO #268](https://github.com/OnscriptSocialFi/backend/issues/268) |

### Protected Resource Metadata Response

```json
{
  "resource": "https://mcp.onscript.xyz/mcp",
  "bearer_methods_supported": ["header"],
  "authorization_servers": ["https://app.onscript.xyz"],
  "scopes_supported": ["mcp:tools:read", "mcp:tools:write"]
}
```

### Auth Server Metadata Response

```json
{
  "issuer": "https://app.onscript.xyz",
  "authorization_endpoint": "https://app.onscript.xyz/mcp/authorize",
  "token_endpoint": "https://mcp.onscript.xyz/auth/mcp/token",
  "response_types_supported": ["code"],
  "code_challenge_methods_supported": ["S256"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "scopes_supported": ["mcp:tools:read", "mcp:tools:write"]
}
```

### Token Exchange Details

- Validate authorization code + PKCE code_verifier (S256)
- Issue JWT access_token (1 hour expiry) + refresh_token (7 days)
- JWT claims: `sub` (user_id), `aud` (mcp.onscript.xyz), `scope`, `exp`, `iat`
- Refresh token rotated on use
- Cron job cleans revoked/expired tokens every 5 minutes

### DB Table: `mcp_tokens`

| Column | Type | Purpose |
|---|---|---|
| `id` | TEXT (ULID) | Token ID |
| `user_id` | TEXT | FK to users |
| `access_token` | TEXT | Hashed JWT |
| `refresh_token` | TEXT | Hashed refresh token |
| `client_id` | TEXT | MCP client identifier |
| `scope` | TEXT | Granted scopes |
| `expires_at` | INTEGER | Access token expiry (epoch) |
| `refresh_expires_at` | INTEGER | Refresh token expiry (epoch) |
| `created_at` | INTEGER | Creation timestamp |
| `revoked_at` | INTEGER | Revocation timestamp (nullable) |

---

## Production Deployment

See `idea.md` for the full production plan. Summary:

### What's Needed

1. **Deploy MCP server** to `mcp.onscript.xyz` with Streamable HTTP transport
2. **Add auth middleware** — validate Bearer token on every request
3. **Add OAuth 2.1 endpoints** — `/auth/mcp/authorize`, `/auth/mcp/token`, `/auth/mcp/refresh`, `/auth/mcp/revoke`
4. **Add .well-known metadata** — `/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`
5. **Submit to Claude Connectors Directory** — `claude.ai/admin-settings/directory/submissions/new`

### Claude Connectors Directory

To appear in Claude's connector search:
1. Review submission guidelines: `claude.com/docs/connectors/building/submission`
2. Ensure server meets security standards
3. Submit through the submission portal (requires Team or Enterprise org)
4. All tools need `title` and `readOnlyHint`/`destructiveHint` annotations
5. Need: OAuth 2.0, privacy policy, test credentials, HTTPS

### Other Clients

No submission needed — users just paste the server URL:
- **Cursor** — Settings → MCP → Add new server
- **VS Code** — `.vscode/mcp.json`
- **Windsurf** — `mcp_config.json`
- **ChatGPT** — Settings → Connectors
- **Claude Code** — `claude mcp add --transport http onscript https://mcp.onscript.xyz/mcp`

---

## File Structure

```
MCP/
├── server.ts           # MCP server + token server (main file)
├── start-http.ts       # HTTP transport entry point
├── start-stdio.ts      # Stdio transport entry point
├── package.json        # Dependencies (fastmcp, zod, dotenv)
├── tsconfig.json       # TypeScript config
├── .env                # Token storage (auto-updated, gitignored)
├── .gitignore          # Excludes node_modules, .env, logs
├── idea.md             # Full production plan (OAuth, Claude Connectors)
├── PLAN.md             # Periodic token sync plan
├── PLAN-periodic-sync.md  # Earlier version of sync plan
└── README.md           # This file
```

---

## Known Issues

1. **Token refresh** — MCP server updates token in memory immediately, but MCP clients (Claude Desktop) may not re-read until disconnected/reconnected. `sendResourceUpdated` notification is sent but only works for subscribed clients.
2. **create_post** — requires connected social accounts. If user has none, tool throws "No connected social accounts."
3. **mcp.onscript.xyz** — not live yet. Backend dev (@adophilus) is setting it up.

---

## Tags

- **@adophilus** — backend: deploy MCP server, add OAuth endpoints, .well-known metadata, route for /mcp-get-started
- **@ghost** — frontend: token sync flow, get-started page on website
