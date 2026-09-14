import asyncio
import json
import os
from mcp.types import Icon

from dotenv import load_dotenv
from fastmcp import FastMCP
import requests


load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL")
MCP_URL= os.getenv("MCP_URL")

mcp = FastMCP(name="onscript-mcp",website_url="https://onscript.xyz",icons=[Icon(src="./onscript.png", mime_type="image/png")])

@mcp.tool
async def email_sign_up(email:str)->str:
    res=requests.post(f"{BACKEND_URL}/auth/sign-in/strategy/email",json={
        "email":email
    })
    if res.status_code != 200:
        return f"email auth sign up failed,please use a valid email address or try again later "

    return "email sign up successful please put in the otp code sent to your email"


@mcp.tool
async def email_otp_verification(email:str,otp:str)->str:
    res=requests.post(f"{BACKEND_URL}/auth/sign-in/strategy/email",json={
        "email":email,
        "otp":otp
    })

    if res.status_code != 200:
        return f"email auth otp verification failed,please check you actually have used the right email sent otp code"

    return "verification successful"

@mcp.tool
async def email_sign_in(email:str)->str:
    res=requests.post(f"{BACKEND_URL}/auth/sign-in/strategy/email",json={
        "email":email
    })

    if res.status_code != 200:
        return f"email auth sign in failed,please check you actually have an account"
    return "email sign in successful,please input the otp sent to your email"

@mcp.tool
async def isauthenticated_status(email:str)->str:
    return "Not authenticated"

if __name__ == "__main__":
    mcp.run()


