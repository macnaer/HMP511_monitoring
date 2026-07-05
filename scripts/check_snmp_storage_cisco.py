#!/usr/bin/env python3
"""Cisco storage usage check via SNMP.

Queries hrStorageSize and hrStorageUsed to calculate disk usage percentage.
Uses snmpget via subprocess (no pysnmp dependency).

Thresholds (used space):
  OK:       < warn%
  WARNING:  >= warn% and < crit%
  CRITICAL: >= crit%

Usage:
  check_snmp_storage_cisco.py --host 10.7.99.5 --community public --index 3 --warn 80 --crit 90
"""

import argparse
import subprocess
import sys

EXIT_OK = 0
EXIT_WARNING = 1
EXIT_CRITICAL = 2
EXIT_UNKNOWN = 3

HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"


def snmp_get(host, community, oid, timeout=30):
    """Perform an SNMP GET via snmpget and return the integer value, or None on failure."""
    try:
        result = subprocess.run(
            ["snmpget", "-v2c", "-c", community, "-Oqv", "-t", str(timeout), host, oid],
            capture_output=True, text=True, timeout=timeout + 5
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip().strip('"').strip()
        return int(value)
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return None


def format_bytes(kb):
    """Convert kilobytes to a human-readable string."""
    if kb >= 1048576:
        return "{:.1f}TB".format(kb / 1048576)
    if kb >= 1024:
        return "{:.1f}GB".format(kb / 1024)
    return "{}MB".format(kb)


def main():
    parser = argparse.ArgumentParser(description="Check Cisco storage usage via SNMP")
    parser.add_argument("--host", required=True, help="Target host IP or hostname")
    parser.add_argument("--community", default="public", help="SNMP community string")
    parser.add_argument("--index", type=int, default=3, help="Storage index (default: 3)")
    parser.add_argument("--warn", type=int, default=80, help="Warning threshold for used %% (default: 80)")
    parser.add_argument("--crit", type=int, default=90, help="Critical threshold for used %% (default: 90)")
    parser.add_argument("--timeout", type=int, default=30, help="SNMP timeout in seconds")
    args = parser.parse_args()

    oid_size = "{}.{}".format(HR_STORAGE_SIZE, args.index)
    oid_used = "{}.{}".format(HR_STORAGE_USED, args.index)

    total_kb = snmp_get(args.host, args.community, oid_size, args.timeout)
    if total_kb is None:
        print("CRITICAL - SNMP query failed for hrStorageSize")
        sys.exit(EXIT_CRITICAL)

    used_kb = snmp_get(args.host, args.community, oid_used, args.timeout)
    if used_kb is None:
        print("CRITICAL - SNMP query failed for hrStorageUsed")
        sys.exit(EXIT_CRITICAL)

    if total_kb == 0:
        print("UNKNOWN - Storage size reported as 0")
        sys.exit(EXIT_UNKNOWN)

    used_pct = (used_kb * 100) / total_kb
    total_str = format_bytes(total_kb)
    used_str = format_bytes(used_kb)
    free_str = format_bytes(total_kb - used_kb)

    perfdata = "used={}KB;{};{};0;{}".format(
        used_kb, total_kb * args.warn // 100, total_kb * args.crit // 100, total_kb
    )

    if used_pct >= args.crit:
        print("CRITICAL - Storage: {} / {} ({:.1f}% used, {} free) | {}".format(
            used_str, total_str, used_pct, free_str, perfdata
        ))
        sys.exit(EXIT_CRITICAL)
    elif used_pct >= args.warn:
        print("WARNING - Storage: {} / {} ({:.1f}% used, {} free) | {}".format(
            used_str, total_str, used_pct, free_str, perfdata
        ))
        sys.exit(EXIT_WARNING)
    else:
        print("OK - Storage: {} / {} ({:.1f}% used, {} free) | {}".format(
            used_str, total_str, used_pct, free_str, perfdata
        ))
        sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
