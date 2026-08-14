# Periodic Token Sync Plan

## Problem

MCP server gets stuck with old token. The retry mechanism only runs for 50 minutes then stops. If user signs in again hours later, no retry running, old token stays forever.

**Root cause:** One-time push on sign-in. No ongoing sync.

**Note:** Backend token is lifelong — doesn't expire until user signs out. So the token sent on sign-in is always valid.

---

## Current Flow

```
Sign-in → send token to MCP server → done
                                        ↓ fail
                                   retry for 50 min → stop → stuck with old token
```

---

## Solution: Periodic Token Sync

### What

Push token from webapp to MCP server every 20 minutes. Runs indefinitely until sign-out.

### Why

- Retry stops after 50 minutes — if user signs in again later, no retry running
- MCP server may restart and load old `.env`
- Token is lifelong — so periodic sync just ensures MCP server has the latest one

### Flow

```
Sign-in → send token → start periodic sync (every 20 min)
                          ↓
                       20 min → send token → MCP server updates
                       20 min → send token → MCP server updates
                          ... (runs until sign-out)
```

### Changes

**File: `src/hooks/useAuth.ts`** — only file changed

1. Add `PERIODIC_SYNC_INTERVAL = 20 * 60 * 1000` constant
2. Add `periodicSyncId` variable at module level
3. Add `startPeriodicTokenSync(token)` function
4. Update `clearTokenRetry()` to also clear `periodicSyncId`
5. Call `startPeriodicTokenSync(token)` in `verifyOTP` after token send

**File: `mcp/server.ts`** — NO CHANGES

### Implementation

```typescript
// Module-level constant
const PERIODIC_SYNC_INTERVAL = 20 * 60 * 1000; // 20 minutes

// Module-level variable
let periodicSyncId: ReturnType<typeof setInterval> | null = null;

// Updated clearTokenRetry
function clearTokenRetry() {
  if (retryIntervalId) {
    clearInterval(retryIntervalId);
    retryIntervalId = null;
    retryAttempts = 0;
  }
  if (periodicSyncId) {
    clearInterval(periodicSyncId);
    periodicSyncId = null;
  }
}

// New function
function startPeriodicTokenSync(token: string) {
  if (periodicSyncId) {
    clearInterval(periodicSyncId);
    periodicSyncId = null;
  }
  periodicSyncId = setInterval(async () => {
    const ok = await sendTokenToMCPServer(token);
    if (ok) {
      console.log(`[auth] Periodic token sync succeeded`);
    } else {
      console.log(`[auth] Periodic token sync failed — MCP server offline`);
    }
  }, PERIODIC_SYNC_INTERVAL);
}

// In verifyOTP:
const token = res.data?.access_token;
if (token) {
  const success = await sendTokenToMCPServer(token);
  if (!success) {
    startTokenRetry(token);
  }
  startPeriodicTokenSync(token);
}
```

### Console Output

```
[auth] Token sent to MCP server on port 3099          ← sign-in
[auth] Periodic token sync succeeded                   ← 20 min later
[auth] Periodic token sync succeeded                   ← 40 min later
[auth] Periodic token sync failed — MCP server offline ← 60 min later
[auth] Periodic token sync succeeded                   ← 80 min later
```

---

## Audit 1: Edge Cases, Memory Leaks, Race Conditions

| Check | Finding |
|-------|---------|
| Memory leak | `periodicSyncId` cleared in `clearTokenRetry()` — FIXED |
| Race condition | Two rapid `verifyOTP`: second `startPeriodicTokenSync()` clears first — SAFE |
| Cleanup on sign-out | `clearTokenRetry()` clears both retry and periodic sync — FIXED |
| Page refresh | Periodic sync lost, but token in localStorage, next sign-in restarts — ACCEPTABLE |
| Multiple tabs | Each tab runs own sync. Idempotent — ACCEPTABLE |
| Token captured in closure | Old sync cleared when new token arrives — SAFE |
| Async in setInterval | `sendTokenToMCPServer` catches all errors — SAFE |
| Token validity | Lifelong token — always valid until sign-out — SAFE |

---

## Audit 2: Verify Assumptions

| Assumption | Verified? |
|------------|-----------|
| `saveToken()` is idempotent | Yes — overwrites `ACCESS_TOKEN` and `.env` |
| `clearTokenRetry()` exists | Yes — implemented in previous step |
| `sendTokenToMCPServer()` returns boolean | Yes — `true` on success, `false` if all ports fail |
| Periodic sync runs until sign-out | Yes — `clearTokenRetry()` stops it |
| 20-minute interval reasonable | Yes — frequent enough, not spammy |
| No server changes needed | Yes — `saveToken()` handles updates |
| Token captured at sign-in is valid | Yes — lifelong token, fresh from backend |
| `startPeriodicTokenSync()` replaces old sync | Yes — clears `periodicSyncId` first |

---

## Audit Result: NO ISSUES FOUND

Both audits pass. Plan is solid.
