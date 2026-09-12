"""OnScript MCP server — Python / FastMCP port of the original TypeScript server.

Mirrors the TS implementation's tools, the local token-drop HTTP server, and
the token-status resource. One behavioral gap is called out where the two
libraries genuinely differ — see the note above `save_token`.
"""

from __future__ import annotations

import errno
import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from typing_extensions import Annotated

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"

load_dotenv(ENV_PATH)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:3007")
TOKEN_PORT = int(os.environ.get("TOKEN_PORT", "3099"))

_access_token: str = os.environ.get("ACCESS_TOKEN", "")
_token_lock = threading.Lock()


def log(*args: Any) -> None:
    """Write to stderr so stdout stays clean for the MCP stdio transport."""
    print("[mcp]", *args, file=sys.stderr, flush=True)


mcp = FastMCP(name="onscript-mcp",website_url="https://onscript.xyz",icons=[Icon(src="./onscript.png")])


# ── Save token to .env ──
def save_token(token: str) -> None:
    global _access_token
    lines: list[str] = []
    found = False
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text().splitlines():
            if not raw.strip():
                continue
            if raw.startswith("ACCESS_TOKEN="):
                lines.append(f"ACCESS_TOKEN={token}")
                found = True
            else:
                lines.append(raw)
    if not found:
        lines.append(f"ACCESS_TOKEN={token}")
    ENV_PATH.write_text("\n".join(lines) + "\n")

    with _token_lock:
        _access_token = token
    log(f"Token saved: {token[:16]}...")

    # NOTE — genuine gap vs. the TS version, not an oversight:
    # the TS `fastmcp` library's `server.sendResourceUpdated()` broadcasts to
    # every connected session. Python's `fastmcp`/MCP SDK only exposes
    # `ctx.session.send_resource_updated(uri)`, which needs an active request
    # context — there isn't one here, since this fires from the token HTTP
    # server's own thread, outside any MCP request. There's no public,
    # supported way to reach "all current sessions" from outside a request.
    # If clients need to learn about a token refresh, either have them poll
    # `check_token` / read the `onscript://token-status` resource again, or
    # track sessions yourself via server middleware and call
    # `session.send_resource_updated(...)` per session.


# ── Token HTTP server ──
class _TokenRequestHandler(BaseHTTPRequestHandler):
    def _set_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _reply(self, status: int, body: str) -> None:
        self.send_response(status)
        self._set_cors()
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/token":
            self._reply(404, "not found")
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw_body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            log("Token server: bad JSON")
            self._reply(400, "Bad JSON")
            return

        access_token = payload.get("access_token")
        if not access_token:
            log("Token server: no access_token")
            self._reply(400, "No token")
            return

        save_token(access_token)
        self._reply(200, "ok")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        log(format % args)


def start_token_server() -> Optional[ThreadingHTTPServer]:
    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", TOKEN_PORT), _TokenRequestHandler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            log(f"Token port {TOKEN_PORT} in use")
        else:
            log("Token server error:", exc)
        return None
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


# ── Call backend ──
async def api(
    path: str,
    *,
    method: str = "GET",
    json_body: Optional[dict[str, Any]] = None,
) -> Any:
    if not _access_token:
        log("No access token — sign in to webapp")
        raise ToolError("No access token. Sign in to the webapp first.")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            method,
            f"{BACKEND_URL}{path}",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_access_token}",
            },
            json=json_body,
        )

    if resp.status_code >= 400:
        body_text = resp.text
        if resp.status_code == 401:
            raise ToolError("Token expired. Sign in again.")
        if resp.status_code == 402:
            raise ToolError("Plan limit reached.")
        raise ToolError(f"Backend error {resp.status_code}: {body_text}")

    return resp.json()


# ── Tools ──
@mcp.tool(description="View your OnScript profile")
async def get_profile() -> str:
    data = await api("/users/profile")
    return json.dumps(data, indent=2)


@mcp.tool(description="Create a post on OnScript. Detects connected accounts automatically.")
async def create_post(
    content: Annotated[str, Field(description="Post content text")],
    status: Annotated[
        Literal["DRAFT", "PUBLISHING", "SCHEDULED"],
        Field(
            description=(
                "DRAFT saves without posting, PUBLISHING posts immediately, "
                "SCHEDULED requires scheduled_at"
            )
        ),
    ],
    scheduled_at: Annotated[
        Optional[int],
        Field(description="Unix epoch in seconds. Required if status is SCHEDULED"),
    ] = None,
) -> str:
    accounts: list[dict[str, Any]] = await api("/integrations/connected-accounts")
    active = [a for a in accounts if a.get("is_active")]
    if not active:
        raise ToolError("No connected social accounts. Connect one in the webapp first.")
    primary = next((a for a in active if a.get("is_primary")), active[0])

    platform_map = {
        "twitter": "TWITTER",
        "x": "TWITTER",
        "linkedin": "LINKEDIN",
        "farcaster": "FARCASTER",
        "facebook": "FACEBOOK",
        "instagram": "INSTAGRAM",
        "youtube": "YOUTUBE",
        "tiktok": "TIKTOK",
    }
    platform_name = platform_map.get(str(primary["platform"]).lower(), str(primary["platform"]).upper())

    body: dict[str, Any] = {
        "status": status,
        "platforms": [
            {
                "platform": platform_name,
                "connected_account_id": primary["id"],
                "text": content,
                "media_ids": [],
            }
        ],
    }
    if status == "SCHEDULED":
        if not scheduled_at:
            raise ToolError("scheduled_at (unix seconds) is required for SCHEDULED posts")
        body["scheduled_at"] = scheduled_at

    result = await api("/posts", method="POST", json_body=body)
    return json.dumps(result, indent=2)


@mcp.tool(description="List your posts")
async def list_posts(
    limit: Annotated[Optional[int], Field(description="Number of posts")] = None,
    status: Annotated[Optional[str], Field(description="Filter by status")] = None,
) -> str:
    params: dict[str, str] = {}
    if limit is not None:
        params["limit"] = str(limit)
    if status is not None:
        params["status"] = status
    query = f"?{urlencode(params)}" if params else ""
    data = await api(f"/posts{query}")
    return json.dumps(data, indent=2)


@mcp.tool(description="Get a specific post")
async def get_post(post_id: Annotated[str, Field(description="Post ID")]) -> str:
    data = await api(f"/posts/{post_id}")
    return json.dumps(data, indent=2)


@mcp.tool(description="See connected social platforms")
async def get_connected_accounts() -> str:
    data = await api("/integrations/connected-accounts")
    return json.dumps(data, indent=2)


@mcp.tool(description="View posting analytics")
async def get_analytics(
    period: Annotated[Optional[str], Field(description="Time period (7d, 30d, 90d)")] = None,
) -> str:
    query = f"?period={period}" if period else ""
    data = await api(f"/users/profile/analytics{query}")
    return json.dumps(data, indent=2)


@mcp.tool(description="Check if authentication token is set")
def check_token() -> str:
    return json.dumps({"hasToken": bool(_access_token)}, indent=2)


# ── Token status resource (read it again after a refresh; see the note above
#    save_token for why this can't be pushed to clients the way the TS
#    version does) ──
@mcp.resource(
    uri="onscript://token-status",
    description="Current authentication token status",
    mime_type="application/json",
)
def token_status() -> str:
    return json.dumps(
        {
            "hasToken": bool(_access_token),
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
        }
    )


def main() -> None:
    if _access_token:
        log(f"Token loaded: {_access_token[:16]}...")
    else:
        log("No token — sign in to webapp to send one")

    start_token_server()
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
