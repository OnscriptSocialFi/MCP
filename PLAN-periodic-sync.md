# MCP Token Periodic Sync Plan

## Problem

MCP server gets stuck with old token. Even though `sendTokenToMCPServer` fires on sign-in, if it fails or the user signs in again later, the MCP server keeps the old token. The retry mechanism only runs for 50 minutes then stops.

**Root cause:** One-time push on sign-in. No ongoing sync.

---

## Current Flow

```
Sign-in → send token to MCP server → done
                                        ↓ fail
                                   retry for 50 min → stop → stuck with old token
```

**What exists:**
- `useAuth.ts:467-474` — sends token on sign-in, retries for 50 min
- `server.ts:21-38` — `saveToken()` updates `ACCESS_TOKEN` in memory + writes to `.env`
- `server.ts:15` — `let ACCESS_TOKEN = process.env.ACCESS_TOKEN` (read once at startup)

**Why it fails:**
1. MCP server already running with old token
2. New token send fails (server briefly offline)
3. Retry runs for 50 min then stops
4. User signs in again hours later — retry is gone, old token stuck

---

## Solution: Periodic Token Sync

### Changes

**File: `src/hooks/useAuth.ts`**

1. Add `PERIODIC_SYNC_INTERVAL = 20 * 60 * 1000` (20 minutes)
2. After sign-in, start a periodic sync that sends token to MCP server every 20 minutes
3. Sync runs indefinitely while user is signed in
4. Stops on sign-out (`clearTokenRetry()` also clears periodic sync)
5. Logs each sync attempt

**File: `mcp/server.ts`** — NO CHANGES NEEDED
- `saveToken()` already handles duplicate tokens (idempotent)
- `ACCESS_TOKEN` variable is updated in real-time

### New Flow

```
Sign-in → send token → start periodic sync (every 20 min)
                          ↓
                       20 min → send token → MCP server updates
                       20 min → send token → MCP server updates
                       20 min → send token → MCP server updates
                          ... (runs until sign-out)
```

### Implementation

```typescript
// Add to module-level constants
const PERIODIC_SYNC_INTERVAL = 20 * 60 * 1000; // 20 minutes

// Add to module-level variables
let periodicSyncId: ReturnType<typeof setInterval> | null = null;

// Add to clearTokenRetry()
function clearTokenRetry() {
  if (retryIntervalId) {
    clearInterval(retryIntervalId);
    retryIntervalId = null;
    retryAttempts = 0;
  }
  // Also clear periodic sync
  if (periodicSyncId) {
    clearInterval(periodicSyncId);
    periodicSyncId = null;
  }
}

// Add new function
function startPeriodicTokenSync(token: string) {
  // Clear any existing sync first
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

// In verifyOTP, after token send:
const token = res.data?.access_token;
if (token) {
  const success = await sendTokenToMCPServer(token);
  if (!success) {
    startTokenRetry(token);
  }
  // Always start periodic sync (even if first send succeeded)
  startPeriodicTokenSync(token);
}
```

### Console Output

```
[auth] Token sent to MCP server on port 3099          ← sign-in
[auth] Periodic token sync succeeded                   ← 20 min later
[auth] Periodic token sync succeeded                   ← 40 min later
[auth] Periodic token sync failed — MCP server offline ← 60 min later (server restarted)
[auth] Periodic token sync succeeded                   ← 80 min later (server back)
```

---

## Why This Works

1. **Continuous sync** — token is pushed every 20 minutes, not just on sign-in
2. **Covers restarts** — if MCP server restarts with old .env, next sync updates it
3. **Covers failed sends** — if first send fails, periodic sync keeps trying
4. **Stops on sign-out** — `clearTokenRetry()` clears both retry and periodic sync
5. **Idempotent** — sending same token twice is harmless (server just overwrites)
6. **No server changes** — MCP server already handles token updates correctly

---

## Edge Cases

| Case | Behavior |
|------|----------|
| MCP server offline during sync | Log failure, try again in 20 min |
| User signs out | `clearTokenRetry()` stops periodic sync |
| User signs in again | `startPeriodicTokenSync()` replaces old sync |
| Same token sent twice | Idempotent — server overwrites with same value |
| Page refresh | Periodic sync lost, but next sign-in restarts it |

---

## Testing

1. Start webapp + MCP server → sign in → verify token sent
2. Wait 20 min → verify periodic sync fires
3. Stop MCP server → verify sync fails gracefully
4. Restart MCP server → verify sync succeeds on next interval
5. Sign out → verify periodic sync stops
