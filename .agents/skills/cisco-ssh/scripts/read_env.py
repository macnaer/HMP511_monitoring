#!/usr/bin/env python3
"""
Load credentials from .env file in the project root.

Returns a dict with keys: host, port, username, password, internal_ip, external_ip.
NEVER prints or logs credentials.
"""

import os
import sys
from pathlib import Path


def load_env(env_path=None):
    """Load .env file and return credentials as a dict.

    Args:
        env_path: Optional explicit path to .env file. If None, searches
                  for .env in the project root (4 levels up from this script).

    Returns:
        dict with keys: internal_ip, external_ip, internal_port, external_port,
                        username, password
    """
    if env_path is None:
        # Project root is 4 levels up: scripts/ -> cisco-ssh/ -> skills/ -> .agents/ -> root
        project_root = Path(__file__).resolve().parents[4]
        env_path = project_root / ".env"

    env_path = Path(env_path)
    if not env_path.exists():
        print(f"ERROR: .env file not found at {env_path}", file=sys.stderr)
        sys.exit(1)

    env = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()

    required = ["INTERNAL_IP", "PASSWORD"]
    missing = [k for k in required if k not in env]
    if missing:
        print(f"ERROR: Missing keys in .env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # Accept USERNAME or common typo USRERNAME
    username = env.get("USERNAME") or env.get("USRERNAME")
    if not username:
        print("ERROR: Missing USERNAME (or USRERNAME) in .env", file=sys.stderr)
        sys.exit(1)

    return {
        "internal_ip": env.get("INTERNAL_IP"),
        "external_ip": env.get("EXTERNAL_IP"),
        "internal_port": int(env.get("INTERNAL_PORT", "22")),
        "external_port": int(env.get("EXTERNAL_PORT", "22")),
        "username": username,
        "password": env.get("PASSWORD"),
    }


if __name__ == "__main__":
    import json
    creds = load_env()
    # Print keys only, not values
    print(f"Loaded credentials for user '{creds['username']}' at host {creds['internal_ip']}:{creds['internal_port']}")
