#!/usr/bin/env python3
"""Cisco storage usage check via SNMP.

Queries hrStorageSize and hrStorageUsed to calculate disk usage percentage.
Uses snmpwalk via subprocess (no pysnmp dependency).

Thresholds (used space):
  OK:       < warn%
  WARNING:  >= warn% and < crit%
  CRITICAL: >= crit%

Usage:
  check_snmp_storage_cisco.py --host 10.7.99.5 --community public --index 3 --warn 80 --crit 90
"""

import argparse
import re
import subprocess
import sys

EXIT_OK = 0
EXIT_WARNING = 1
EXIT_CRITICAL = 2
EXIT_UNKNOWN = 3

HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"


def snmp_walk_get(community, host, oid, index, timeout=30):
    """Walk an SNMP OID and return the value for a specific index, or None on failure."""
    try:
        full_oid = "{}.{}".format(oid, index)
        result = subprocess.run(
            ["snmpwalk", "-v2c", "-c", community, "-Oqv", "-t", str(timeout), host, full_oid],
            capture_output=True, text=True, timeout=timeout + 5
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip().strip('"').strip()
        if not value or value == "No Such Object available on this agent at this OID":
            return None
        return int(value)
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return None


def snmp_walk_table(community, host, oid, timeout=30):
    """Walk an SNMP OID table and return a dict of {index: value}."""
    results = {}
    try:
        result = subprocess.run(
            ["snmpwalk", "-v2c", "-c", community, "-Oqv", "-t", str(timeout), host, oid],
            capture_output=True, text=True, timeout=timeout + 5
        )
        if result.returncode != 0:
            return results
        for line in result.stdout.strip().splitlines():
            line = line.strip().strip('"').strip()
            if not line or "No Such Object" in line:
                continue
            try:
                results[len(results) + 1] = int(line)
            except ValueError:
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return results


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

    # Try direct index first
    total_kb = snmp_walk_get(args.community, args.host, HR_STORAGE_SIZE, args.index, args.timeout)

    # If direct index fails, walk the table and try to find a valid entry
    if total_kb is None:
        size_table = snmp_walk_table(args.community, args.host, HR_STORAGE_SIZE, args.timeout)
        used_table = snmp_walk_table(args.community, args.host, HR_STORAGE_USED, args.timeout)

        if args.index in size_table and args.index in used_table:
            total_kb = size_table[args.index]
            used_kb = used_table[args.index]
        elif size_table and used_table:
            # Use the first index that has both size and used values
            for idx in size_table:
                if idx in used_table and size_table[idx] > 0:
                    total_kb = size_table[idx]
                    used_kb = used_table[idx]
                    break
        else:
            total_kb = None
            used_kb = None
    else:
        used_kb = snmp_walk_get(args.community, args.host, HR_STORAGE_USED, args.index, args.timeout)

    if total_kb is None or used_kb is None:
        print("CRITICAL - SNMP query failed for hrStorageSize/hrStorageUsed")
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
