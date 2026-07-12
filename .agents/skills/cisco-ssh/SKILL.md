---
name: cisco-ssh
description: SSH-based monitoring and management of Cisco switches/routers. Use when user needs to run Cisco IOS commands (show, configure, debug), check interfaces, transceivers, VLANs, routing tables, or troubleshoot connectivity issues on Cisco Catalyst/ISR devices. Supports interactive shell sessions and one-shot commands. Reads credentials from .env (never hardcoded).
---

# Cisco SSH Skill

Connect to Cisco switches/routers via SSH and execute IOS commands. Used for on-demand diagnostics, configuration checks, and network troubleshooting.

## When to use this skill

- User asks to run a `show` command on a Cisco device
- User wants to check interface status, transceivers, errors, VLANs
- User needs to verify configuration (running-config, startup-config)
- User wants to check routing table, ARP, MAC table, CDP/LLDP neighbors
- User asks "what's on port X", "check SFP on Gi0/45", etc.

## When NOT to use this skill

- SNMP-based checks (use `nagios-snmp` skill instead for periodic monitoring)
- Non-Cisco devices (Mikrotik, Hikvision, etc.)
- Bulk automation across many devices

## Credentials (security)

**NEVER hardcode credentials in scripts.** Credentials are read from the project's `.env` file at runtime:

```
INTERNAL_IP=<switch IP>
EXTERNAL_IP=<public IP>
INTERNAL_PORT=22
EXTERNAL_PORT=8759
USERNAME=<ssh user>
PASSWORD=<ssh password>
```

The skill scripts load `.env` automatically using `python-dotenv` or a simple parser. If `.env` is missing, the script exits with a clear error message.

**Security rules:**
- Never commit `.env` to git (already in `.gitignore`)
- Never print credentials in logs or error messages
- Never include credentials in skill files, prompts, or responses
- Never write credentials to output files

## Available scripts

### `scripts/cisco_ssh.py`
Python wrapper for SSH connections to Cisco devices. Supports:
- One-shot commands (`--command`)
- Interactive sessions (no `--command` flag, returns to `enable` mode)
- Multiple commands piped (`--command "show ip; show version"`)

Usage:
```bash
python scripts/cisco_ssh.py --host <ip> --command "show version"
python scripts/cisco_ssh.py --host <ip> --command "show interfaces gigabitEthernet 0/45 transceiver detail"
python scripts/cisco_ssh.py --host <ip>           # interactive mode
```

### `scripts/read_env.py`
Helper to load `.env` and return credentials as a dict. Used internally by `cisco_ssh.py`.

## Usage examples

**Run a single command:**
```bash
python .agents/skills/cisco-ssh/scripts/cisco_ssh.py --host 10.7.99.5 --command "show interfaces status"
```

**Run multiple commands:**
```bash
python .agents/skills/cisco-ssh/scripts/cisco_ssh.py --host 10.7.99.5 --command "show version; show ip interface brief; show vlan brief"
```

**From the opencode session:**
The agent can invoke the script directly via the `bash` tool. The script will:
1. Load `.env` from the project root
2. Connect via SSH using paramiko
3. Disable pagination (`terminal length 0`)
4. Execute the command(s)
5. Return output and close the session

## Notes on Cisco IOS

- The switch's `demo` user is in user EXEC mode (not privileged). Some `show` commands require `enable` mode.
- If `enable` password is not set, the script will try to enter `enable` mode and gracefully report if it fails.
- Pagination is disabled with `terminal length 0` to get full output.
- Use `terminal width 511` for wide output (e.g., `show running-config`).
- Old Cisco IOS may use weak SSH algorithms (DH group1, 3DES, hmac-sha1). The script enables legacy algorithms via paramiko 2.12+.

## Limitations

- Script does not support configuration mode (`configure terminal`) — read-only by design.
- For config changes, use the Nagios/Jenkins deployment pipeline or manual SSH.
- Single device per script invocation (no multi-device batching).
