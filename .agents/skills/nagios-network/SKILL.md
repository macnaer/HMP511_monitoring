---
name: nagios-network
description: Network interface monitoring checks for Nagios. Use when creating or troubleshooting checks for bandwidth, errors, and interface status on Linux servers. Cloud-agnostic, works on any server with network interfaces.
compatibility: Requires Python 3.11+, psutil library. Works on Linux, Windows, macOS.
metadata:
  author: nagios-monitoring
  version: "1.0"
---

## Nagios Network Monitoring Skill

Python-based network interface checks for Nagios. All scripts follow standard Nagios plugin conventions (exit codes 0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN).

### Available Scripts

- **`scripts/check_bandwidth.py`** — Interface bandwidth usage
- **`scripts/check_errors.py`** — Interface errors and discards
- **`scripts/check_interface_status.py`** — Link up/down status

### Usage

Run any script with `--help` for full options:

```bash
python3 scripts/check_bandwidth.py --interface eth0 --warn 80 --crit 95
python3 scripts/check_errors.py --interface eth0 --warn 100 --crit 1000
python3 scripts/check_interface_status.py --interface eth0
```

### Output Convention

```
OK - <message>
WARNING - <message>
CRITICAL - <message>
UNKNOWN - <message>
```

Exit codes: `0` (OK), `1` (WARNING), `2` (CRITICAL), `3` (UNKNOWN)

### Nagios Command Definitions

Add to `commands.cfg`:

```
define command {
    command_name    check_bandwidth
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_bandwidth.py --interface $ARG1$ --warn $ARG2$ --crit $ARG3$
}

define command {
    command_name    check_errors
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_errors.py --interface $ARG1$ --warn $ARG2$ --crit $ARG3$
}

define command {
    command_name    check_interface_status
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_interface_status.py --interface $ARG1$
}
```

### Service Templates

See [assets/service-templates.cfg](assets/service-templates.cfg) for ready-to-use Nagios service definitions.
