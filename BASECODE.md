# Onscript MCP Server README

## Overview
The Onscript MCP (Model Context Protocol) server enables AI agents—such as Claude Desktop, Cursor, VS Code, Windsurf, and Claude Code—to interact with Onscript user accounts. It facilitates natural language management of social media presence, including post creation, analytics retrieval, and platform connectivity.

- Repository: OnscriptSocialFi/MCP
- Production URL: https://mcp.onscript.xyz/mcp
- Get Started: https://onscript.xyz/mcp-get-started

## Architecture
The system operates through a multi-tier communication flow:
- AI Agent: The client interface (Claude Desktop, Cursor, etc.).
- MCP Server: The intermediary (mcp.onscript.xyz/mcp) running on fastMCP + zod.
- Onscript Backend API: The core service (localhost:5000) managing social platform interactions (Twitter, LinkedIn, Farcaster, etc.).

## Authentication and Token Flow
The server utilizes an OAuth 2.1 flow to authorize access. Tokens are managed via a dedicated Token Server (port 3099) and synchronized through three primary mechanisms:

- Immediate Send: Tokens are pushed to the MCP server upon successful OTP verification.
- Retry on Failure: If the server is unreachable, the client retries every 5 minutes for 50 minutes across ports 3099-3103.
- Periodic Sync: The frontend pushes the token every 20 minutes to ensure the MCP server maintains an active session.

### Key Auth Components
- Frontend (src/hooks/useAuth.ts):
  - sendTokenToMCPServer(token): Attempts to push tokens to ports 3099-3103.
  - startTokenRetry(token): Manages the 50-minute retry window.
  - startPeriodicTokenSync(token): Maintains session persistence.
  - clearTokenRetry(): Terminates sync processes upon sign-out.
- MCP Server (server.ts):
  - saveToken(token): Persists tokens to .env, updates memory, and triggers resource updates.
  - tokenServer: HTTP listener on port 3099 for incoming token POST requests.

## Tools
The server provides the following tools for agent interaction:

- get_profile
  - Description: View OnScript profile information.
  - Endpoint: /users/profile
  - Method: GET
- create_post
  - Description: Create draft, published, or scheduled posts.
  - Endpoint: /integrations/connected-accounts + /posts
  - Method: GET + POST
- list_posts
  - Description: List posts with filtering capabilities.
  - Endpoint: /posts
  - Method: GET
- get_post
  - Description: Retrieve details for a specific post.
  - Endpoint: /posts/{id}
  - Method: GET
- get_connected_accounts
  - Description: View connected social platforms.
  - Endpoint: /integrations/connected-accounts
  - Method: GET
- get_analytics
  - Description: View posting analytics.
  - Endpoint: /users/profile/analytics
  - Method: GET
- check_token
  - Description: Verify if an authentication token is currently set.
  - Endpoint: N/A
  - Method: N/A

## Python Implementation (server.py)
The Python-based server utilizes Redis for session management and provides additional functionality:

- email_sign_up
  - Description: Initiates email-based account creation.
- email_otp_verification
  - Description: Verifies OTP and stores session data in Redis.
- email_sign_in
  - Description: Initiates the sign-in process via email.
- get_user_profile
  - Description: Fetches profile data from the authenticated session.
- get_stats
  - Description: Retrieves user analytics.
- get_connected_accounts
  - Description: Lists connected social platforms.
- connect_social_account
  - Description: Generates an OAuth link for platform integration.
- disconnect_social_account
  - Description: Removes a connected social account.
- get_posts
  - Description: Fetches paginated user posts.
- delete_post
  - Description: Removes a post by ID.
- retry_post
  - Description: Re-attempts a failed cross-post publishing action.
- publish_post
  - Description: Publishes a draft to target platforms.
- upload_media
  - Description: Handles file uploads via signed Cloudinary signatures.
- check_upload_status
  - Description: Polls the processing status of uploaded media.
- create_draft
  - Description: Creates a draft post for specified platforms.

## Local Development
- Prerequisites: Node.js 18+, Python 3.x, Redis.
- Setup:
  - Install dependencies: npm install
  - Configure .env: Set BACKEND_URL, ACCESS_TOKEN, TOKEN_PORT, and MCP_SERVER_PORT.
- Execution:
  - HTTP Mode: npx tsx start-http.ts
  - Stdio Mode: npx tsx start-stdio.ts
  - Python Server: python server.py

## OAuth 2.1 Flow Details
The system follows a standard authorization code flow with PKCE (S256):
- Authorization Endpoint: /auth/mcp/authorize
- Token Endpoint: /auth/mcp/token
- Refresh Endpoint: /auth/mcp/refresh
- Revocation Endpoint: /auth/mcp/revoke

Metadata is exposed via:
- /.well-known/oauth-protected-resource
- /.well-known/oauth-authorization-server

## Known Issues
- Token Refresh: MCP clients may require a manual disconnect/reconnect to recognize token updates in memory.
- Post Creation: Requires at least one connected social account; otherwise, the tool will return an error.
- Deployment: The production URL (mcp.onscript.xyz) is currently pending backend configuration.