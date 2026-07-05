---
name: nagios-snmp
description: SNMP-based Nagios monitoring checks for network devices. Use when creating or troubleshooting SNMP checks for switches, routers, cameras, or any SNMP-enabled device. Supports generic SNMP queries, Hikvision cameras, and Cisco devices.
compatibility: Requires Python 3.11+, pysnmp-lextudio library, and network access to SNMP-enabled devices.
metadata:
  author: nagios-monitoring
  version: "1.0"
---

## Nagios SNMP Monitoring Skill

Python-based SNMP checks for Nagios monitoring. All scripts follow standard Nagios plugin conventions (exit codes 0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN).

### Environment Variables

All scripts read credentials from environment variables:

```bash
export NAGIOS_SNMP_COMMUNITY="LibreNms"    # SNMP community string
export NAGIOS_SNMP_VERSION="2c"            # SNMP version (1, 2c, 3)
export NAGIOS_SNMP_TIMEOUT="30"            # Timeout in seconds
```

### Available Scripts

- **`scripts/check_snmp_generic.py`** — Generic SNMP check for any OID
- **`scripts/check_snmp_hikvision.py`** — Hikvision camera-specific checks
- **`scripts/check_snmp_cisco.py`** — Cisco switch/router health checks

### Usage

Run any script with `--help` for full options:

```bash
python3 scripts/check_snmp_generic.py --host 10.0.0.1 --oid 1.3.6.1.2.1.1.3.0
python3 scripts/check_snmp_hikvision.py --host 10.0.0.2 --check uptime
python3 scripts/check_snmp_cisco.py --host 10.0.0.3 --check temperature
python3 scripts/check_snmp_cisco.py --host 10.0.0.3 --check interface
python3 scripts/check_snmp_cisco.py --host 10.0.0.3 --check interface --interface GigabitEthernet0/1
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
    command_name    check_snmp_generic
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_snmp_generic.py --host $HOSTADDRESS$ --oid $ARG1$ --warn $ARG2$ --crit $ARG3$
}

define command {
    command_name    check_snmp_hikvision
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_snmp_hikvision.py --host $HOSTADDRESS$ --check $ARG1$ --warn $ARG2$ --crit $ARG3$
}

define command {
    command_name    check_snmp_cisco
    command_line    /usr/bin/python3 /opt/nagios/etc/scripts/check_snmp_cisco.py --host $HOSTADDRESS$ --check $ARG1$ --warn $ARG2$ --crit $ARG3$ --interface $ARG4$
}
```

### Service Templates

See [assets/service-templates.cfg](assets/service-templates.cfg) for ready-to-use Nagios service definitions.
