import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-Admin-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Token fijo para administración inicial (sobrescribible por variable de entorno)
ADMIN_TOKEN = os.getenv("VANGUARDOPS_ADMIN_TOKEN", "super-secret-admin-token")

def get_admin_token(api_key_header: str = Security(api_key_header)) -> str:
    if api_key_header != ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate admin credentials",
        )
    return api_key_header
