"""
auth.py
=======
Basic auth for testing.

For production, prefer OAuth client credentials.
"""

import base64
import config


def get_headers() -> dict:
    token = base64.b64encode(
        f"{config.ORACLE_USERNAME}:{config.ORACLE_PASSWORD}".encode("utf-8")
    ).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
