import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
MCP_URL = "http://127.0.0.1:5000" # Adjust to your actual MCP server port
EMAIL = "test@example.com"

def test_all_tools():
    print("--- Starting MCP Tool Tests ---")
    
    # 1. Test Auth (Assuming user is already verified in Redis)
    print("Testing get_user_profile...")
    print(requests.post(f"{MCP_URL}/get_user_profile", json={"email": EMAIL}).json())

    # 2. Test Social Accounts
    print("\nTesting get_connected_accounts...")
    print(requests.post(f"{MCP_URL}/get_connected_accounts", json={"email": EMAIL}).json())

    # 3. Test Media Upload (Requires a local file 'test.jpg')
    if os.path.exists("test.jpg"):
        print("\nTesting upload_media...")
        upload_res = requests.post(f"{MCP_URL}/upload_media", json={
            "email": EMAIL,
            "file_path": "test.jpg"
        }).json()
        print(upload_res)
        
        # Extract file_id if successful
        if "file_id" in str(upload_res):
            file_id = upload_res.split("file_id=")[1].split(",")[0]
            print(f"\nTesting check_upload_status for {file_id}...")
            print(requests.post(f"{MCP_URL}/check_upload_status", json={"email": EMAIL, "file_id": file_id}).json())
    else:
        print("\nSkipping media upload test: test.jpg not found.")

    # 4. Test Post Management
    print("\nTesting get_posts...")
    print(requests.post(f"{MCP_URL}/get_posts", json={"email": EMAIL}).json())

    print("\n--- Tests Complete ---")

if __name__ == "__main__":
    test_all_tools()