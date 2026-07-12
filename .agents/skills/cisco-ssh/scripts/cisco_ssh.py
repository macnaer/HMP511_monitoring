#!/usr/bin/env python3
"""
Cisco SSH command runner for Nagios monitoring project.

Connects to a Cisco switch/router via SSH and executes IOS commands.
Credentials are loaded from .env file - never hardcoded.

Usage:
    cisco_ssh.py --host IP --command "show version"
    cisco_ssh.py --host IP --command "show ip; show vlan"
    cisco_ssh.py --host IP                  # interactive (not supported in non-tty mode)
    cisco_ssh.py --env-path /path/to/.env  # custom .env location
    cisco_ssh.py --user demo --host 10.7.99.5 --command "show version"  # override creds

Exit codes:
    0 = success
    1 = SSH connection error
    2 = authentication failure
    3 = command execution error
"""

import argparse
import os
import sys
import time
import warnings

# Suppress paramiko/cryptography deprecation warnings
warnings.filterwarnings("ignore")

# Ensure we can import read_env from same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from read_env import load_env


def enable_legacy_kex():
    """Enable legacy SSH key exchange algorithms for old Cisco IOS."""
    try:
        import paramiko
        available = set(paramiko.Transport._preferred_kex)
        legacy = {"diffie-hellman-group14-sha1", "diffie-hellman-group-exchange-sha1",
                  "diffie-hellman-group1-sha1", "ecdh-sha2-nistp256",
                  "diffie-hellman-group14-sha256", "diffie-hellman-group-exchange-sha256",
                  "diffie-hellman-group16-sha512"}
        merged = list(dict.fromkeys([k for k in (list(legacy & available) + list(available))]))
        paramiko.Transport._preferred_kex = tuple(merged)
    except (ImportError, AttributeError):
        pass


def run_command(host, port, username, password, command, timeout=15):
    """Connect to Cisco device and run a command.

    Returns:
        tuple: (exit_code, output_text)
            exit_code: 0 = OK, 1 = connection error, 2 = auth error, 3 = exec error
    """
    import paramiko

    enable_legacy_kex()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            host,
            port,
            username,
            password,
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False,
        )
    except paramiko.AuthenticationException:
        return 2, "Authentication failed"
    except paramiko.SSHException as e:
        return 1, f"SSH error: {e}"
    except Exception as e:
        return 1, f"Connection error: {type(e).__name__}: {e}"

    try:
        shell = client.invoke_shell()
        time.sleep(2)

        # Read initial prompt
        if shell.recv_ready():
            shell.recv(65535)

        # Disable pagination
        shell.send("terminal length 0\n")
        time.sleep(1)
        if shell.recv_ready():
            shell.recv(65535)

        # Execute command(s) - split on ; for multiple
        commands = [c.strip() for c in command.split(";") if c.strip()]
        all_output = []

        for cmd in commands:
            shell.send(cmd + "\n")
            time.sleep(2)

            # Read all available output
            output = b""
            end_time = time.time() + timeout
            while time.time() < end_time:
                if shell.recv_ready():
                    output += shell.recv(65535)
                else:
                    # Check if we got back to prompt (ends with > or #)
                    if output and (b"> " in output[-50:] or b"# " in output[-50:]):
                        break
                    time.sleep(0.3)

            all_output.append(f"=== {cmd} ===")
            all_output.append(output.decode("utf-8", errors="ignore").strip())

        shell.close()
        client.close()
        return 0, "\n".join(all_output)

    except Exception as e:
        try:
            client.close()
        except Exception:
            pass
        return 3, f"Execution error: {type(e).__name__}: {e}"


def main():
    parser = argparse.ArgumentParser(description="Run IOS commands on Cisco device via SSH")
    parser.add_argument("--host", help="Device IP address (overrides .env INTERNAL_IP)")
    parser.add_argument("--port", type=int, default=22, help="SSH port (default 22)")
    parser.add_argument("--user", help="SSH username (overrides .env USERNAME)")
    parser.add_argument("--password", help="SSH password (overrides .env PASSWORD)")
    parser.add_argument("--command", help="IOS command to execute (semicolon-separated for multiple)")
    parser.add_argument("--env-path", help="Path to .env file (default: project root)")
    parser.add_argument("--timeout", type=int, default=15, help="Connection/command timeout in seconds")
    args = parser.parse_args()

    # Load credentials from .env, then apply CLI overrides
    creds = load_env(args.env_path)
    host = args.host or creds["internal_ip"]
    port = args.port or creds["internal_port"]
    username = args.user or creds["username"]
    password = args.password or creds["password"]

    if not args.command:
        parser.error("--command is required")

    exit_code, output = run_command(host, port, username, password, args.command, args.timeout)
    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
