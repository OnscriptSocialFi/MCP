import asyncio
import json
import os
from typing import List
from mcp.types import Icon

from dotenv import load_dotenv
from fastmcp import FastMCP
import requests
import redis

from utils import sanitize_auth_payload

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL")
MCP_PORT = int(os.getenv("MCP_PORT"))
REDIS_PORT = os.getenv("REDIS_PORT")
# Base URL of the OnScript web app — used to build the OAuth connect link
# that gets returned to the caller (mirrors extendsSocialsConnect on the frontend).
FRONTEND_URL = os.getenv("FRONTEND_URL")

SUPPORTED_PLATFORMS = [
    "TWITTER", "LINKEDIN", "TIKTOK", "FARCASTER", "FACEBOOK", "INSTAGRAM", "YOUTUBE"
]

r = redis.Redis(host='localhost', port=REDIS_PORT, decode_responses=True)
mcp = FastMCP(name="onscript-mcp", website_url="https://onscript.xyz", icons=[Icon(src="./onscript.png", mime_type="image/png")])

# Helper function to get auth data from Redis
def get_user_auth(email: str):
    user_data_raw = r.get(email)
    if not user_data_raw:
        return None, f"User with email '{email}' is not authenticated. Please sign in."
    
    try:
        user_data = json.loads(user_data_raw)
        access_token = user_data.get("access_token")
        user_id = user_data.get("user", {}).get("id")
        
        if not access_token:
            return None, f"No access token found for '{email}'."
            
        return {"access_token": access_token, "user_id": user_id}, None
    except Exception as e:
        return None, f"Error parsing auth data: {str(e)}"


# --- Existing Auth Tools ---

@mcp.tool
async def email_sign_up(email: str) -> str:
    res = requests.post(f"{BACKEND_URL}/auth/sign-in/strategy/email", json={"email": email})
    if res.status_code != 200:
        return "email auth sign up failed, please use a valid email address or try again later"
    return "email sign up successful please put in the otp code sent to your email"

@mcp.tool
async def email_otp_verification(email: str, otp: str) -> str:
    res = requests.post(f"{BACKEND_URL}/auth/verification", json={"email": email, "otp": otp})
    if res.status_code != 200:
        return "email auth otp verification failed, please check you actually have used the right email sent otp code"
    res_ = res.json()
    r.set(email, json.dumps(res_))
    return "verification successful"

@mcp.tool
async def email_sign_in(email: str) -> str:
    res = requests.post(f"{BACKEND_URL}/auth/sign-in/strategy/email", json={"email": email})
    if res.status_code != 200:
        return "email auth sign in failed, please check you actually have an account"
    return "email sign in successful, please input the otp sent to your email"

@mcp.tool
async def isauthenticated_status(email: str) -> str:
    return "Not authenticated"

@mcp.tool
async def get_user_profile(email: str) -> str:
    res_ = sanitize_auth_payload(r.get(email))
    return f"Here is information on the user's profile {res_}"

@mcp.tool
async def get_stats(email: str) -> str:
    auth, err = get_user_auth(email)
    if err: return err
    try:
        res = requests.get(f"{BACKEND_URL}/users/profile/analytics", headers={"Authorization": f"Bearer {auth['access_token']}"})
        if res.status_code != 200: return f"Failed to retrieve stats. Status: {res.status_code}"
        return f"User Analytics Stats:\n{json.dumps(res.json(), indent=2)}"
    except Exception as e:
        return f"Error fetching stats: {str(e)}"


# --- Social Account Integration Tools ---

@mcp.tool
async def get_connected_accounts(email: str) -> str:
    """Fetches the list of social accounts currently connected for the user."""
    auth, err = get_user_auth(email)
    if err: return err

    try:
        res = requests.get(
            f"{BACKEND_URL}/integrations/connected-accounts",
            headers={"Authorization": f"Bearer {auth['access_token']}"}
        )
        if res.status_code != 200:
            return f"Failed to fetch connected accounts. Status: {res.status_code}."
        return f"Connected accounts:\n{json.dumps(res.json(), indent=2)}"
    except Exception as e:
        return f"An error occurred while fetching connected accounts: {str(e)}"


@mcp.tool
async def connect_social_account(email: str, platform: str) -> str:
    """
    Generates an OAuth connect link for the given platform.
    platform should be one of: TWITTER, LINKEDIN, TIKTOK, FARCASTER, FACEBOOK, INSTAGRAM, YOUTUBE.
    Open the returned URL in a browser (signed in as the same user) to authorize and link the account.
    """
    auth, err = get_user_auth(email)
    if err: return err

    platform = platform.upper()
    if platform not in SUPPORTED_PLATFORMS:
        return f"Unsupported platform '{platform}'. Choose from: {', '.join(SUPPORTED_PLATFORMS)}"

    if not FRONTEND_URL:
        return "FRONTEND_URL is not configured on the MCP server, so I can't build a connect link."

    connect_url = f"{FRONTEND_URL}/integrations/{platform.lower()}/oauth/callback?token={auth['access_token']}"
    return f"Open this link in your browser to connect {platform}:\n{connect_url}"


@mcp.tool
async def disconnect_social_account(email: str, account_id: str) -> str:
    """Disconnects a previously connected social account by its connected-account id."""
    auth, err = get_user_auth(email)
    if err: return err

    try:
        res = requests.post(
            f"{BACKEND_URL}/integrations/disconnect",
            json={"account_id": account_id},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth['access_token']}"
            }
        )
        if res.status_code not in [200, 204]:
            return f"Failed to disconnect account '{account_id}'. Status: {res.status_code}."
        return f"Successfully disconnected account '{account_id}'."
    except Exception as e:
        return f"An error occurred while disconnecting the account: {str(e)}"


# --- New Cross-Posting Tools ---

@mcp.tool
async def get_posts(email: str, page: int = 1, per_page: int = 10) -> str:
    """Fetches a paginated list of posts created by the user."""
    auth, err = get_user_auth(email)
    if err: return err

    try:
        url = f"{BACKEND_URL}/posts?page={page}&per_page={per_page}&from_user={auth['user_id']}"
        res = requests.get(url, headers={"Authorization": f"Bearer {auth['access_token']}"})
        
        if res.status_code != 200:
            return f"Failed to fetch posts. Backend returned status {res.status_code}."
            
        return f"Posts retrieved successfully:\n{json.dumps(res.json(), indent=2)}"
    except Exception as e:
        return f"An error occurred while fetching posts: {str(e)}"


@mcp.tool
async def delete_post(email: str, post_id: str) -> str:
    """Deletes a specific post by its ID."""
    auth, err = get_user_auth(email)
    if err: return err

    try:
        res = requests.delete(
            f"{BACKEND_URL}/posts/{post_id}",
            headers={"Authorization": f"Bearer {auth['access_token']}"}
        )
        
        if res.status_code not in [200, 204]:
            return f"Failed to delete post '{post_id}'. Status: {res.status_code}."
            
        return f"Successfully deleted post '{post_id}'."
    except Exception as e:
        return f"An error occurred while deleting the post: {str(e)}"


@mcp.tool
async def retry_post(email: str, post_id: str) -> str:
    """Retries a failed cross-post publishing attempt."""
    auth, err = get_user_auth(email)
    if err: return err

    try:
        res = requests.post(
            f"{BACKEND_URL}/posts/{post_id}/retry",
            headers={"Authorization": f"Bearer {auth['access_token']}"}
        )
        
        if res.status_code != 200 and res.status_code != 201:
            return f"Failed to retry post '{post_id}'. Status: {res.status_code}."
            
        return f"Successfully initiated retry for post '{post_id}':\n{json.dumps(res.json(), indent=2)}"
    except Exception as e:
        return f"An error occurred while retrying the post: {str(e)}"


@mcp.tool
async def publish_post(email: str, post_id: str, scheduled_at: int = None) -> str:
    """
    Publishes a drafted post, pushing it live to its target platform(s).
    Pass scheduled_at as a unix timestamp to schedule it for later, or omit it
    (defaults to None) to publish immediately — matches the frontend's createPost flow.
    """
    auth, err = get_user_auth(email)
    if err: return err

    try:
        res = requests.post(
            f"{BACKEND_URL}/posts/{post_id}/publish",
            json={"scheduled_at": scheduled_at},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth['access_token']}"
            }
        )

        if res.status_code not in [200, 201, 202]:
            return f"Failed to publish post '{post_id}'. Status: {res.status_code}. Response: {res.text}"

        return f"Successfully published post '{post_id}':\n{json.dumps(res.json(), indent=2)}"
    except Exception as e:
        return f"An error occurred while publishing the post: {str(e)}"


@mcp.tool
async def check_upload_status(email: str, file_id: str) -> str:
    """Checks the processing status (e.g., PENDING, READY, FAILED) of an uploaded media file."""
    auth, err = get_user_auth(email)
    if err: return err

    try:
        res = requests.get(
            f"{BACKEND_URL}/storage/files/{file_id}",
            headers={"Authorization": f"Bearer {auth['access_token']}"}
        )
        
        if res.status_code != 200:
            return f"Failed to check status for file '{file_id}'. Status: {res.status_code}."
            
        return f"File upload status:\n{json.dumps(res.json(), indent=2)}"
    except Exception as e:
        return f"An error occurred while checking file status: {str(e)}"


@mcp.tool
async def create_draft(email: str, text: str, platforms: List[str], media_ids: List[str] = None) -> str:
    """
    Creates a drafted post for the specified platforms.
    platforms should be a list like ["TWITTER", "LINKEDIN"].
    Each platform must already have a connected account — use connect_social_account first if not.
    """
    auth, err = get_user_auth(email)
    if err: return err
    
    if media_ids is None:
        media_ids = []

    try:
        # Resolve a connected_account_id for each requested platform — the backend
        # rejects drafts that omit it (this was the original 400 we were hitting).
        accounts_res = requests.get(
            f"{BACKEND_URL}/integrations/connected-accounts",
            headers={"Authorization": f"Bearer {auth['access_token']}"}
        )
        if accounts_res.status_code != 200:
            return f"Failed to look up connected accounts. Status: {accounts_res.status_code}."

        connected_accounts = accounts_res.json().get("data", [])
        account_by_platform = {}
        for acc in connected_accounts:
            if not acc.get("is_active"):
                continue
            plat = (acc.get("platform") or "").upper()
            # Prefer the primary account if a platform has more than one connected.
            if plat not in account_by_platform or acc.get("is_primary"):
                account_by_platform[plat] = acc.get("id")

        missing = [p for p in platforms if p.upper() not in account_by_platform]
        if missing:
            return (
                f"Can't create draft — no connected account for: {', '.join(missing)}. "
                f"Use connect_social_account to link {'them' if len(missing) > 1 else 'it'} first."
            )

        payload = {
            "status": "DRAFT",
            "platforms": [
                {
                    "platform": p.upper(),
                    "connected_account_id": account_by_platform[p.upper()],
                    "text": text,
                    "media_ids": media_ids,
                } for p in platforms
            ]
        }

        res = requests.post(
            f"{BACKEND_URL}/posts",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth['access_token']}"
            }
        )
        
        if res.status_code not in [200, 201, 202]:
            return f"Failed to create draft. Status: {res.status_code}. Response: {res.text}"
            
        return f"Draft created successfully:\n{json.dumps(res.json(), indent=2)}"
    except Exception as e:
        return f"An error occurred while creating the draft: {str(e)}"
if __name__ == "__main__":
    mcp.run(transport="http",
        host="127.0.0.1",
        port=MCP_PORT,       # whatever port your reverse proxy forwards to
        path="/")
