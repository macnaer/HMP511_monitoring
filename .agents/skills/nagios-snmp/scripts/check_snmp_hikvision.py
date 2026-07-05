#!/usr/bin/env python3
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
import traceback

try:
    from pysnmp.hlapi import (
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        getCmd,
    )
except ImportError as e:
    print(f"UNKNOWN - pysnmp import failed: {e}")
    sys.exit(3)


# Nagios exit codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

# Hikvision specific OIDs
HIKVISION_OIDS = {
    "uptime": "1.3.6.1.2.1.1.3.0",
    "time": "1.3.6.1.4.1.39165.1.19.0",
    "storage_total": "1.3.6.1.2.1.25.2.3.1.5.1",
    "storage_used": "1.3.6.1.2.1.25.2.3.1.6.1",
}


def snmp_get(host, oid, community, version, timeout):
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
            return CRITICAL, "SNMP error: %s" % error_indication
        if error_status:
            return CRITICAL, "SNMP error: %s" % error_status.prettyPrint()
        if var_binds:
            value = var_binds[0][1].prettyPrint()
            return OK, value
        return UNKNOWN, "No value returned"

    except Exception as e:
        return UNKNOWN, "Exception: %s" % str(e)


def check_uptime(host, community, version, timeout):
    exit_code, value = snmp_get(host, HIKVISION_OIDS["uptime"], community, version, timeout)
    if exit_code != OK:
        return exit_code, "Cannot get uptime: %s" % value

    try:
        uptime_ticks = int(value)
        uptime_seconds = uptime_ticks // 100
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        return OK, "Uptime: %dd %dh %dm" % (days, hours, minutes)
    except (ValueError, TypeError):
        return OK, "Uptime: %s" % value


def check_temperature(host, community, version, timeout, warn, crit):
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
                        return CRITICAL, "Temperature: %sC (>=%sC)" % (temp, crit)
                    elif temp >= warn:
                        return WARNING, "Temperature: %sC (>=%sC)" % (temp, warn)
                return OK, "Temperature: %sC" % temp
            except (ValueError, TypeError):
                continue

    return UNKNOWN, "Temperature OID not available on this device"


def check_storage(host, community, version, timeout, warn, crit):
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
        if warn is not None and crit is not None:
            if percent >= crit:
                return CRITICAL, "Storage: %.1f%% used (%d/%d)" % (percent, used, total)
            elif percent >= warn:
                return WARNING, "Storage: %.1f%% used (%d/%d)" % (percent, used, total)
        return OK, "Storage: %.1f%% used (%d/%d)" % (percent, used, total)
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid storage data"


def check_time(host, community, version, timeout):
    exit_code, value = snmp_get(host, HIKVISION_OIDS["time"], community, version, timeout)
    if exit_code != OK:
        return exit_code, "Cannot get time: %s" % value
    return OK, "Time: %s" % value


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

    try:
        checks = {
            "uptime": lambda: check_uptime(args.host, args.community, args.version, args.timeout),
            "temperature": lambda: check_temperature(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
            "storage": lambda: check_storage(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
            "time": lambda: check_time(args.host, args.community, args.version, args.timeout),
        }

        exit_code, message = checks[args.check]()
        print("%s - %s" % (["OK", "WARNING", "CRITICAL", "UNKNOWN"][exit_code], message))
        sys.exit(exit_code)

    except Exception as e:
        print("UNKNOWN - Script error: %s" % str(e))
        sys.exit(UNKNOWN)


if __name__ == "__main__":
    main()
