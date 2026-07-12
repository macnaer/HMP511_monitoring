# AGENTS.md - Project Agent Notes

This file documents agent skills, conventions, and security rules for the Nagios monitoring project.

## Skills

The following skills are available in `.agents/skills/`:

| Skill | Purpose | When to use |
|-------|---------|-------------|
| **nagios-snmp** | SNMP checks (generic, Cisco, Hikvision) | Periodic monitoring via Nagios |
| **nagios-system** | System health (CPU, RAM, disk, load) | Linux server monitoring |
| **nagios-network** | Network interface checks (bandwidth, errors, status) | Switch/router port monitoring |
| **cisco-ssh** | SSH-based Cisco IOS commands | On-demand diagnostics, troubleshooting |

## cisco-ssh skill

For ad-hoc Cisco device diagnostics via SSH. Examples:

```bash
# Run a single show command
python .agents/skills/cisco-ssh/scripts/cisco_ssh.py --command "show version"

# Run multiple commands
python .agents/skills/cisco-ssh/scripts/cisco_ssh.py --command "show ip interface brief; show vlan brief"

# Override host/credentials
python .agents/skills/cisco-ssh/scripts/cisco_ssh.py --host 10.7.99.5 --user demo --password XXX --command "show interfaces status"
```

The script reads credentials from `.env` in the project root by default.

## Security rules (CRITICAL)

1. **NEVER hardcode credentials** in scripts, configs, or skill files.
2. **NEVER print credentials** in logs, error messages, or output.
3. **NEVER commit `.env`** - it is in `.gitignore`.
4. **NEVER include credentials** in commit messages, PR descriptions, or chat responses.
5. **NEVER write credentials** to output files (e.g., temp files, reports).
6. When working with credentials, only reference them by their purpose (e.g., "the .env file") and let the script load them at runtime.
7. If a user pastes credentials in chat, acknowledge briefly and remind them to use `.env` instead.

## Credential locations

| File | Purpose | In git? |
|------|---------|---------|
| `.env` | SSH/SNMP credentials, IPs, ports | NO (gitignored) |
| `.env.example` | Template showing structure | YES |
| `*.cfg` (Nagios) | May contain SNMP community strings | YES (use public/LibreNms defaults) |

## Project conventions

- Python 3.12+ in Docker container (use `pysnmp>=5.0` with `v3arch.asyncio` API)
- Nagios 4.x on `jasonrivers/nagios:latest` base image
- All Python check scripts use Nagios exit codes: 0=OK, 1=WARN, 2=CRIT, 3=UNKNOWN
- Telegram notifications via `scripts/notify_r2d2.sh` (read token from env at runtime)
- Jenkins pipeline: build → push to DockerHub → deploy to remote server
