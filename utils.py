import json

def sanitize_auth_payload(payload_str: str, redact: bool = True) -> str:
    """
    Parses an incoming auth JSON string, hides or strips the access_token,
    and returns the sanitized JSON string.
    """
    # 1. Parse JSON string into a Python dict
    data = json.loads(payload_str)
    
    # 2. Hide or remove the access_token key if present
    if "access_token" in data:
        if redact:
            data["access_token"] = "[REDACTED]"
        else:
            del data["access_token"]
            
    return json.dumps(data, ensure_ascii=False, indent=2)
