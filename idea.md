# MCP Production Plan — OAuth + Authorization Page

## Architecture Overview

Like Notion, Onscript will use a **remote HTTP MCP server** with OAuth 2.1 authorization. No local server needed — Claude Desktop connects directly to `mcp.onscript.xyz/mcp`.

### How It Works (User Flow)

```
1. User opens Claude Desktop → Settings → Connectors → searches "Onscript"
2. User clicks "Connect" on Onscript
3. Claude Desktop sends request to mcp.onscript.xyz/mcp (no token)
4. Server returns 401 + WWW-Authenticate header pointing to metadata
5. Claude discovers auth server from Protected Resource Metadata
6. Claude opens browser to app.onscript.xyz/mcp/authorize?state=...
7. If not signed in → redirects to webapp sign-in (email + OTP)
8. After sign-in → redirects back to /mcp/authorize
9. User sees "Connect with Onscript MCP" consent screen
10. User clicks "Continue" (authorizes)
11. Server generates authorization code, redirects to Claude's callback
12. Claude exchanges code for access_token + refresh_token
13. Claude stores tokens, sends Bearer token on all future MCP requests
14. Tools work — user can talk to Claude and it uses Onscript tools
```

### How to Publish to Claude Connectors (and other clients)

**Claude Desktop / Claude Web / ChatGPT / Cursor / etc.**

To appear in Claude's connector search, you need to:

1. **Register with Anthropic** — Submit your MCP server URL to Anthropic's connector directory
   - Fill out the form at: https://docs.anthropic.com/en/docs/claude/connectors
   - Provide: server URL (`https://mcp.onscript.xyz/mcp`), description, logo, privacy policy
   - Anthropic reviews and adds you to the searchable directory

2. **Implement the MCP spec correctly** — Claude validates:
   - `/.well-known/oauth-protected-resource` metadata endpoint
   - `/.well-known/oauth-authorization-server` metadata endpoint
   - OAuth 2.1 with PKCE (S256)
   - Proper `WWW-Authenticate` headers on 401
   - HTTPS in production

3. **For other clients** (Cursor, VS Code, Windsurf, ChatGPT):
   - Each has their own connector marketplace or directory
   - Most just need the MCP server URL — users paste it in config
   - No approval needed for manual config

4. **Marketing page** — `app.onscript.xyz/mcp-get-started`
   - Public docs page with setup instructions for each client
   - Linked from the consent screen and marketing site
   - SEO-optimized so users find it when searching "Onscript MCP"

### Auth Flow (Simplified)

```
User clicks "Connect" in Claude
  → Claude opens browser to app.onscript.xyz/mcp/authorize?state=...
  → Page checks: is user logged in?
    → NO: redirect to / (webapp sign-in page)
      → User signs in with email + OTP
      → Redirect back to /mcp/authorize?state=...
    → YES: show consent screen
  → User sees "Connect with Onscript MCP" + permissions list
  → User clicks "Continue"
  → Server issues authorization code
  → Redirect to Claude's callback with code + state
  → Claude exchanges code for tokens
  → Done — tools work
```

### URLs

| URL | Purpose |
|---|---|
| `mcp.onscript.xyz/mcp` | MCP server endpoint (Streamable HTTP) |
| `mcp.onscript.xyz/.well-known/oauth-protected-resource` | Protected Resource Metadata (RFC 9728) |
| `mcp.onscript.xyz/.well-known/oauth-authorization-server` | Auth server metadata (RFC 8414) |
| `app.onscript.xyz/mcp-get-started` | Get-started docs page (like Notion's) |
| `app.onscript.xyz/mcp/authorize` | Authorization/consent page (OAuth) |
| `app.onscript.xyz/mcp/callback` | OAuth callback (receives code) |

### Dev URLs

| URL | Purpose |
|---|---|
| `localhost:5000/mcp` | MCP server (local backend) |
| `localhost:3004/mcp-get-started` | Get-started page (local frontend) |

---

## What We Need to Build

### 1. Backend: MCP Auth Endpoints

**New routes in `@onscript/api`:**

| Endpoint | Method | Purpose |
|---|---|---|
| `/.well-known/oauth-protected-resource` | GET | RFC 9728 metadata — tells clients where to auth |
| `/.well-known/oauth-authorization-server` | GET | RFC 8414 — auth server endpoints metadata |
| `/auth/mcp/authorize` | GET | Validate state, show consent, issue code |
| `/auth/mcp/token` | POST | Exchange code for access_token + refresh_token |
| `/auth/mcp/refresh` | POST | Exchange refresh_token for new access_token |
| `/auth/mcp/revoke` | POST | Revoke tokens (user disconnects) |

**Protected Resource Metadata response:**
```json
{
  "resource": "https://mcp.onscript.xyz/mcp",
  "bearer_methods_supported": ["header"],
  "authorization_servers": ["https://app.onscript.xyz"],
  "scopes_supported": ["mcp:tools:read", "mcp:tools:write"]
}
```

**Auth Server Metadata response:**
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

**Token exchange:**
- Validate authorization code + PKCE code_verifier
- Issue JWT access_token (short-lived: 1 hour) + refresh_token (7 days)
- JWT claims: `sub` (user_id), `aud` (mcp.onscript.xyz), `scope`, `exp`, `iat`

### 2. Backend: Token Infrastructure

**New table: `mcp_tokens`**
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

**Token lifecycle:**
- Access token: 1 hour expiry
- Refresh token: 7 days, rotated on use
- Cron job: clean revoked/expired tokens every 5 minutes

### 3. MCP Server: HTTP Transport

**Replace stdio with Streamable HTTP:**

Current (stdio):
```ts
server.start({ transportType: "stdio" });
```

Production (HTTP):
```ts
server.start({
  transportType: "http-stream",
  http: {
    port: parseInt(process.env.PORT || "3232"),
    basePath: "/mcp",
  }
});
```

**Add auth middleware:**
- Validate Bearer token on every request
- Return 401 with `WWW-Authenticate` header if no token
- Extract user_id from validated JWT
- Pass user context to tool handlers

**Add Protected Resource Metadata endpoint:**
- Serve at `/.well-known/oauth-protected-resource`
- Include `authorization_servers` pointing to `app.onscript.xyz`

### 4. Frontend: Get-Started Page (`app.onscript.xyz/mcp-get-started`)

**Like Notion's "Connect to Notion MCP" docs page.** This is a public documentation page, not part of the app. Shows users how to connect Onscript to their MCP client.

**Page structure (matching Notion's layout):**

```
┌─────────────────────────────────────────────────────┐
│  [Onscript Logo]                                    │
│                                                     │
│  Connect to Onscript MCP                            │
│  Connect an MCP client to your Onscript account.    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Claude Desktop                              │    │
│  │                                             │    │
│  │ 1. Open Settings → Connectors               │    │
│  │ 2. Select "Add Connector"                   │    │
│  │ 3. Enter: https://mcp.onscript.xyz/mcp      │    │
│  │ 4. Complete the OAuth flow                  │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Cursor                                      │    │
│  │                                             │    │
│  │ 1. Open Settings → MCP → Add new server     │    │
│  │ 2. Paste config:                            │    │
│  │    { "mcpServers": { "onscript": {          │    │
│  │      "url": "https://mcp.onscript.xyz/mcp"  │    │
│  │    }}}                                      │    │
│  │ 3. Save and restart                         │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ VS Code (GitHub Copilot)                    │    │
│  │                                             │    │
│  │ 1. Create .vscode/mcp.json:                 │    │
│  │    { "servers": { "onscript": {             │    │
│  │      "type": "http",                        │    │
│  │      "url": "https://mcp.onscript.xyz/mcp"  │    │
│  │    }}}                                      │    │
│  │ 2. Run "MCP: List Servers"                  │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Claude Code                                 │    │
│  │                                             │    │
│  │ $ claude mcp add --transport http \         │    │
│  │   onscript https://mcp.onscript.xyz/mcp     │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Windsurf                                    │    │
│  │                                             │    │
│  │ 1. Open Settings → MCP                      │    │
│  │ 2. Add to mcp_config.json:                  │    │
│  │    { "mcpServers": { "onscript": {          │    │
│  │      "serverUrl": "https://mcp.onscript..." │    │
│  │    }}}                                      │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ ChatGPT                                     │    │
│  │                                             │    │
│  │ 1. Go to Settings → Connectors              │    │
│  │ 2. Add Connector:                           │    │
│  │    https://mcp.onscript.xyz/mcp             │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Other MCP clients                           │    │
│  │                                             │    │
│  │ Streamable HTTP: https://mcp.onscript.xyz/mcp│   │
│  │ SSE: https://mcp.onscript.xyz/sse           │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Troubleshooting                             │    │
│  │                                             │    │
│  │ • Auth issues → Disconnect and reconnect    │    │
│  │ • Token expired → Sign in again             │    │
│  │ • Tools not showing → Restart your client   │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  What Onscript MCP can do:                          │
│  ✓ Create and schedule posts                        │
│  ✓ View your analytics                              │
│  ✓ Manage connected platforms                       │
│  ✓ View your profile                                │
└─────────────────────────────────────────────────────┘
```

**Design principles:**
- Dark theme (#0a0a0a background, #16a34a accent)
- Each client section is a collapsible accordion
- Code snippets in monospace with copy button
- Responsive — works on mobile
- Public page (no auth required to view)
- SEO-friendly (proper meta tags, structured data)

**Components to build:**
- `McpGetStarted` — main page layout
- `ClientAccordion` — collapsible section for each client
- `CodeBlock` — syntax-highlighted code with copy button
- `TroubleshootingAccordion` — expandable FAQ section

### 5. Frontend: Authorization Page (`app.onscript.xyz/mcp/authorize`)

**Simplified consent-only page.** Like Notion's — no sign-in form, just authorization:

- Page loads with `?state=...&redirect_uri=...&code_challenge=...` from Claude
- Checks if user is logged in (reads token from localStorage)
  - If not logged in → redirects to webapp sign-in (`/?redirect=current_url`)
  - After sign-in → redirects back to authorize page
- Shows consent screen:
  - Onscript logo + "Connect with Onscript"
  - "Grant Claude access to Onscript"
  - Account selector (user's name + email + plan)
  - Permissions list with green checkmarks
  - "Continue" button (green) → calls `/auth/mcp/authorize` → redirects to Claude
  - "Cancel" button → redirects to Claude with `access_denied`
- No token display, no manual paste — all automatic
- Uses light theme (white background) to match Notion's consent screen

### 6. MCP Server: Tool Changes

**Current tools use `session.accessToken` (env var).** Production tools use validated JWT:

```ts
// Current (MVP)
execute: async (_args, { session }) => {
  const token = getToken(session?.accessToken);
  return api("/users/profile", {}, token);
}

// Production
execute: async (_args, { session }) => {
  // session.authInfo contains validated JWT claims
  const userId = session.authInfo.sub;
  return api("/users/profile", {}, session.authInfo.token);
}
```

---

## Implementation Phases

### Phase 1: Backend Auth Endpoints (Week 1)
- [ ] Add `mcp_tokens` table migration
- [ ] Implement `/auth/mcp/authorize` (validate state, issue code)
- [ ] Implement `/auth/mcp/token` (exchange code, issue JWT)
- [ ] Implement `/auth/mcp/refresh` (rotate refresh token)
- [ ] Implement `/auth/mcp/revoke` (revoke tokens)
- [ ] Add `/.well-known/oauth-protected-resource` metadata
- [ ] Add `/.well-known/oauth-authorization-server` metadata
- [ ] Add JWT signing (RS256 with rotating keys)
- [ ] Add token cleanup cron job

### Phase 2: MCP Server HTTP Transport (Week 1-2)
- [ ] Switch from stdio to Streamable HTTP transport
- [ ] Add auth middleware (validate Bearer token)
- [ ] Add Protected Resource Metadata endpoint
- [ ] Update tool handlers to use JWT claims
- [ ] Deploy to `mcp.onscript.xyz`
- [ ] Test with MCP Inspector (HTTP mode)

### Phase 3: Get-Started Page + Authorization Page (Week 2)
- [ ] Build `app.onscript.xyz/mcp-get-started` docs page
- [ ] Build `ClientAccordion` component (collapsible per-client instructions)
- [ ] Build `CodeBlock` component (syntax highlighting + copy)
- [ ] Add Claude Desktop, Cursor, VS Code, Claude Code, Windsurf, ChatGPT sections
- [ ] Add troubleshooting section
- [ ] Build authorization page (`app.onscript.xyz/mcp/authorize`)
- [ ] Build consent screen component
- [ ] Wire OAuth authorize flow
- [ ] Test full flow: Claude Desktop → authorize → token → tools

### Phase 4: Testing & Hardening (Week 2-3)
- [ ] Test with Claude Desktop (Pro/Max plan)
- [ ] Test with Cursor, VS Code, Windsurf
- [ ] Test token refresh flow
- [ ] Test concurrent tool calls
- [ ] Test token revocation
- [ ] Test session expiry during MCP usage
- [ ] Security audit: PKCE, audience validation, scope enforcement

### Phase 5: Production Launch (Week 3)
- [ ] Deploy MCP server to `mcp.onscript.xyz`
- [ ] Deploy get-started page to `app.onscript.xyz/mcp-get-started`
- [ ] Deploy authorization page to `app.onscript.xyz/mcp/authorize`
- [ ] Update documentation
- [ ] Announce to users

---

## Bug Predictions (Updated)

### Bug 1: Claude Desktop redirect_uri mismatch
**Scenario**: Claude sends `http://localhost:PORT/callback` but backend expects `https://app.onscript.xyz/mcp/callback`.
**Impact**: OAuth flow fails with "redirect_uri mismatch".
**Fix**: Accept both localhost (dev) and production redirect URIs. Store allowed URIs per client.

### Bug 2: PKCE code_verifier race condition
**Scenario**: User opens authorize page in two tabs, both generate different code_challenges.
**Impact**: Second tab's code_verifier doesn't match first tab's code_challenge.
**Fix**: Only allow one pending authorization per user. Invalidate previous on new request.

### Bug 3: JWT audience validation fails
**Scenario**: Token issued for `mcp.onscript.xyz` but MCP server expects `https://mcp.onscript.xyz/mcp`.
**Impact**: All tool calls fail with "invalid token".
**Fix**: Normalize audience URI. Accept both with and without trailing path.

### Bug 4: Refresh token rotation fails
**Scenario**: User's refresh token is valid but rotation endpoint returns new token with different `sub`.
**Impact**: User's identity changes mid-session.
**Fix**: Validate `sub` matches on every refresh. Never change user_id during rotation.

### Bug 5: Connector page shows "unauthorized" for new users
**Scenario**: New user hits `app.onscript.xyz/mcp` without an account.
**Impact**: Confusing error. Should show sign-up flow.
**Fix**: Detect new users, redirect to sign-up with return URL.

### Bug 6: MCP server doesn't handle CORS
**Scenario**: Browser-based MCP client (ChatGPT web) sends preflight OPTIONS request.
**Impact**: Request blocked by CORS. Tools don't work in browser.
**Fix**: Add CORS headers for `mcp.onscript.xyz` and `app.onscript.xyz`.

### Bug 7: Token expiry not communicated to Claude
**Scenario**: Access token expires after 1 hour. Claude doesn't know to refresh.
**Impact**: Tools fail silently. User sees "tool execution failed".
**Fix**: MCP server returns 401 with `WWW-Authenticate` header. Claude auto-refreshes.

### Bug 8: Multiple MCP clients conflict
**Scenario**: User connects Claude Desktop AND Cursor. Both get separate tokens.
**Impact**: Tokens work independently but user expects unified state.
**Fix**: Tokens are per-client. Document this clearly. Show connected clients in settings.

### Bug 9: Authorization page doesn't work in all browsers
**Scenario**: User's default browser blocks third-party cookies or has strict CSP.
**Impact**: OAuth flow can't complete. User stuck on blank page.
**Fix**: Use redirect-based flow (not popup). Handle cookie blocking gracefully.

### Bug 10: Backend JWT signing key rotation breaks existing tokens
**Scenario**: Backend rotates signing keys. Existing tokens signed with old key fail validation.
**Impact**: All connected users get logged out simultaneously.
**Fix**: Support multiple signing keys (JWKS endpoint with key rotation). Accept tokens signed by any valid key.

---

## Open Questions

1. **Should we use Auth0/Okta or build our own auth server?**
   - Auth0/Okta: faster to implement, handles PKCE, token rotation, key rotation
   - Custom: more control, no vendor lock-in, but more work
   - Recommendation: Use existing backend auth + add OAuth endpoints. Don't add a new provider.

2. **Streamable HTTP vs SSE?**
   - Streamable HTTP: newer, recommended by MCP spec, supports bidirectional
   - SSE: older, simpler, more clients support it
   - Recommendation: Streamable HTTP primary, SSE fallback (like Notion)

3. **Should the MCP server be a separate service or part of the backend?**
   - Separate: cleaner separation, can scale independently
   - Part of backend: simpler deployment, shared auth
   - Recommendation: Separate service for production scalability

4. **Do we need Dynamic Client Registration (RFC 7591)?**
   - Yes: any MCP client can connect without pre-registration
   - No: we can pre-register known clients (Claude, Cursor, etc.)
   - Recommendation: Start without, add later if needed
