---
name: nagios-system
description: System health monitoring checks for Nagios. Use when creating or troubleshooting checks for CPU, memory, disk, and load on Linux/Windows servers. Cloud-agnostic, works on any server.
compatibility: Requires Python 3.11+, psutil library. Works on Linux, Windows, macOS.
metadata:
  author: nagios-monitoring
  version: "1.0"
---

## Nagios System Monitoring Skill

Python-based system health checks for Nagios. All scripts follow standard Nagios plugin conventions (exit codes 0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN).

### Available Scripts

- **`scripts/check_cpu.py`** — CPU usage percentage
- **`scripts/check_memory.py`** — RAM and swap usage
- **`scripts/check_disk.py`** — Disk usage percentage
- **`scripts/check_load.py`** — System load average

### Usage

Run any script with `--help` for full options:

```bash
python3 scripts/check_cpu.py --warn 80 --crit 95
python3 scripts/check_memory.py --warn 80 --crit 95
python3 scripts/check_disk.py --path / --warn 80 --crit 90
python3 scripts/check_load.py --warn 4.0 --crit 8.0
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
    command_name    check_cpu
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_cpu.py --warn $ARG1$ --crit $ARG2$
}

define command {
    command_name    check_memory
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_memory.py --warn $ARG1$ --crit $ARG2$
}

define command {
    command_name    check_disk
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_disk.py --path $ARG1$ --warn $ARG2$ --crit $ARG3$
}

define command {
    command_name    check_load
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_load.py --warn $ARG1$ --crit $ARG2$
}
```

### Service Templates

See [assets/service-templates.cfg](assets/service-templates.cfg) for ready-to-use Nagios service definitions.
