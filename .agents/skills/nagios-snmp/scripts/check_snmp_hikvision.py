#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pysnmp>=6.0.0",
# ]
# ///
"""
Hikvision camera SNMP check for Nagios.

Usage:
    check_snmp_hikvision.py --host HOST --check CHECK [--warn WARN] [--crit CRIT]

Available checks:
    uptime      - Device uptime
    temperature - Device temperature (if available)
    storage     - Storage usage percentage
    time        - System time sync status

Exit codes:
    0 = OK
    1 = WARNING
    2 = CRITICAL
    3 = UNKNOWN
"""

import argparse
import os
import sys
from pysnmp.hlapi import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    getCmd,
    nextCmd,
)


# Nagios exit codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

# Hikvision specific OIDs
HIKVISION_OIDS = {
    "uptime": "1.3.6.1.2.1.1.3.0",           # sysUpTime
    "time": "1.3.6.1.4.1.39165.1.19.0",       # System time
    "storage_total": "1.3.6.1.2.1.25.2.3.1.5.1",  # hrStorageSize
    "storage_used": "1.3.6.1.2.1.25.2.3.1.6.1",   # hrStorageUsed
}


def snmp_get(host: str, oid: str, community: str, version: str, timeout: int) -> tuple[int, str]:
    """Perform SNMP GET and return (exit_code, value_string)."""
    try:
        error_indication, error_status, error_index, var_binds = next(
            getCmd(
                SnmpEngine(),
                CommunityData(community, mpModel=1 if version == "1" else 2),
                UdpTransportTarget((host, 161), timeout=timeout, retries=2),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
        )

        if error_indication:
            return CRITICAL, f"SNMP error: {error_indication}"
        if error_status:
            return CRITICAL, f"SNMP error: {error_status.prettyPrint()}"
        if var_binds:
            value = var_binds[0][1].prettyPrint()
            return OK, value
        return UNKNOWN, "No value returned"

    except Exception as e:
        return UNKNOWN, f"Exception: {e}"


def check_uptime(host: str, community: str, version: str, timeout: int) -> tuple[int, str]:
    """Check device uptime."""
    exit_code, value = snmp_get(host, HIKVISION_OIDS["uptime"], community, version, timeout)
    if exit_code != OK:
        return exit_code, f"Cannot get uptime: {value}"

    try:
        # sysUpTime is in hundredths of seconds
        uptime_ticks = int(value)
        uptime_seconds = uptime_ticks // 100
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        return OK, f"Uptime: {days}d {hours}h {minutes}m"
    except (ValueError, TypeError):
        return OK, f"Uptime: {value}"


def check_temperature(host: str, community: str, version: str, timeout: int,
                      warn: float, crit: float) -> tuple[int, str]:
    """Check device temperature."""
    # Try common Hikvision temperature OIDs
    temp_oids = [
        "1.3.6.1.4.1.39165.1.10.1.0",
        "1.3.6.1.4.1.39165.1.10.2.0",
    ]

    for oid in temp_oids:
        exit_code, value = snmp_get(host, oid, community, version, timeout)
        if exit_code == OK:
            try:
                temp = float(value)
                if warn is not None and crit is not None:
                    if temp >= crit:
                        return CRITICAL, f"Temperature: {temp}C (>={crit}C)"
                    elif temp >= warn:
                        return WARNING, f"Temperature: {temp}C (>={warn}C)"
                return OK, f"Temperature: {temp}C"
            except (ValueError, TypeError):
                continue

    return UNKNOWN, "Temperature OID not available on this device"


def check_storage(host: str, community: str, version: str, timeout: int,
                  warn: float, crit: float) -> tuple[int, str]:
    """Check storage usage percentage."""
    exit_code_total, value_total = snmp_get(host, HIKVISION_OIDS["storage_total"], community, version, timeout)
    exit_code_used, value_used = snmp_get(host, HIKVISION_OIDS["storage_used"], community, version, timeout)

    if exit_code_total != OK or exit_code_used != OK:
        return UNKNOWN, "Cannot query storage OIDs"

    try:
        total = int(value_total)
        used = int(value_used)
        if total == 0:
            return UNKNOWN, "Storage size is 0"

        percent = (used * 100) / total
        if percent >= crit:
            return CRITICAL, f"Storage: {percent:.1f}% used ({used}/{total})"
        elif percent >= warn:
            return WARNING, f"Storage: {percent:.1f}% used ({used}/{total})"
        return OK, f"Storage: {percent:.1f}% used ({used}/{total})"
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid storage data"


def check_time(host: str, community: str, version: str, timeout: int) -> tuple[int, str]:
    """Check system time (just verify we can read it)."""
    exit_code, value = snmp_get(host, HIKVISION_OIDS["time"], community, version, timeout)
    if exit_code != OK:
        return exit_code, f"Cannot get time: {value}"
    return OK, f"Time: {value}"


def main():
    parser = argparse.ArgumentParser(description="Hikvision camera SNMP check for Nagios")
    parser.add_argument("--host", required=True, help="Target host IP or hostname")
    parser.add_argument("--check", required=True, choices=["uptime", "temperature", "storage", "time"],
                        help="Check type to perform")
    parser.add_argument("--warn", type=float, default=None, help="Warning threshold")
    parser.add_argument("--crit", type=float, default=None, help="Critical threshold")
    parser.add_argument("--community", default=os.environ.get("NAGIOS_SNMP_COMMUNITY", "public"),
                        help="SNMP community string")
    parser.add_argument("--version", default=os.environ.get("NAGIOS_SNMP_VERSION", "2c"),
                        help="SNMP version (1, 2c)")
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("NAGIOS_SNMP_TIMEOUT", "30")),
                        help="Timeout in seconds")
    args = parser.parse_args()

    checks = {
        "uptime": lambda: check_uptime(args.host, args.community, args.version, args.timeout),
        "temperature": lambda: check_temperature(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
        "storage": lambda: check_storage(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
        "time": lambda: check_time(args.host, args.community, args.version, args.timeout),
    }

    exit_code, message = checks[args.check]()
    print(f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
