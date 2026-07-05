#!/usr/bin/env python3
"""Cisco storage usage check via SNMP.

Queries hrStorageSize and hrStorageUsed to calculate disk usage percentage.
Returns OK/WARNING/CRITICAL based on thresholds.

Thresholds (used space):
  OK:       < warn%
  WARNING:  >= warn% and < crit%
  CRITICAL: >= crit%

Usage:
  check_snmp_storage_cisco.py --host 10.7.99.5 --community public --index 3 --warn 80 --crit 90
"""

import argparse
import sys

from pysnmp.hlapi import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
)

EXIT_OK = 0
EXIT_WARNING = 1
EXIT_CRITICAL = 2
EXIT_UNKNOWN = 3

HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"
HR_STORAGE_DESCR = "1.3.6.1.2.1.25.2.3.1.3"


def snmp_get(host: str, community: str, oid: str, timeout: int = 30) -> int | None:
    """Perform an SNMP GET and return the integer value, or None on failure."""
    error_indication, error_status, error_index, var_binds = next(
        get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((host, 161), timeout=timeout),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
    )
    if error_indication or error_status:
        return None
    for var_bind in var_binds:
        try:
            return int(var_bind[1])
        except (ValueError, TypeError):
            return None
    return None


def format_bytes(kb: int) -> str:
    """Convert kilobytes to a human-readable string."""
    if kb >= 1048576:
        return f"{kb / 1048576:.1f}TB"
    if kb >= 1024:
        return f"{kb / 1024:.1f}GB"
    return f"{kb}MB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Cisco storage usage via SNMP")
    parser.add_argument("--host", required=True, help="Target host IP or hostname")
    parser.add_argument("--community", default="public", help="SNMP community string")
    parser.add_argument("--index", type=int, default=3, help="Storage index (default: 3)")
    parser.add_argument("--warn", type=int, default=80, help="Warning threshold for used %% (default: 80)")
    parser.add_argument("--crit", type=int, default=90, help="Critical threshold for used %% (default: 90)")
    parser.add_argument("--timeout", type=int, default=30, help="SNMP timeout in seconds")
    args = parser.parse_args()

    oid_size = f"{HR_STORAGE_SIZE}.{args.index}"
    oid_used = f"{HR_STORAGE_USED}.{args.index}"

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
    free_pct = 100.0 - used_pct
    total_str = format_bytes(total_kb)
    used_str = format_bytes(used_kb)
    free_str = format_bytes(total_kb - used_kb)

    perfdata = f"used={used_kb}KB;{total_kb * args.warn // 100};{total_kb * args.crit // 100};0;{total_kb}"

    if used_pct >= args.crit:
        print(
            f"CRITICAL - Storage: {used_str} / {total_str} ({used_pct:.1f}% used, {free_str} free) | {perfdata}"
        )
        sys.exit(EXIT_CRITICAL)
    elif used_pct >= args.warn:
        print(
            f"WARNING - Storage: {used_str} / {total_str} ({used_pct:.1f}% used, {free_str} free) | {perfdata}"
        )
        sys.exit(EXIT_WARNING)
    else:
        print(
            f"OK - Storage: {used_str} / {total_str} ({used_pct:.1f}% used, {free_str} free) | {perfdata}"
        )
        sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
