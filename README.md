# Nagios Monitoring DemoProject

Dockerized Nagios 4.x with Python-based checks. Jenkins CI/CD pipeline.

## Quick Start

Build and run locally:

```bash
docker build -t nagios .
docker run -d -p 81:80 nagios
```

Access web UI: http://localhost:81/nagios

## Monitored Devices

| Device | Network | Checks |
|--------|---------|--------|
| Hikvision cameras | 10.7.50.x | SNMP (uptime, storage, temp) |
| Cisco Catalyst 2960G | 10.7.99.x | SNMP (fan, PSU, CPU, temp) |

## Agent Skills

| Skill | Scripts | Purpose |
|-------|---------|---------|
| nagios-snmp | check_snmp_generic.py, check_snmp_hikvision.py, check_snmp_cisco.py | SNMP device checks |
| nagios-system | check_cpu.py, check_memory.py, check_disk.py, check_load.py | Server health |
| nagios-network | check_bandwidth.py, check_errors.py, check_interface_status.py | Network interfaces |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| NAGIOS_SNMP_COMMUNITY | SNMP community string | public |
| NAGIOS_SNMP_VERSION | SNMP version (1, 2c) | 2c |
| NAGIOS_SNMP_TIMEOUT | Timeout in seconds | 30 |
| TELEGRAM_BOT_TOKEN | Telegram bot token | - |
| TELEGRAM_CHAT_ID | Telegram chat ID | - |

## Notifications

Alerts sent to Telegram via `notify_r2d2.sh`.
