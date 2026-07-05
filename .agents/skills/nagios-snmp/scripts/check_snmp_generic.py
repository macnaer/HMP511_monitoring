#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pysnmp>=6.0.0",
# ]
# ///
"""
Generic SNMP check for Nagios.

Usage:
    check_snmp_generic.py --host HOST --oid OID [--warn WARN] [--crit CRIT] [--community COMMUNITY] [--timeout TIMEOUT]

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
)


# Nagios exit codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


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


def main():
    parser = argparse.ArgumentParser(description="Generic SNMP check for Nagios")
    parser.add_argument("--host", required=True, help="Target host IP or hostname")
    parser.add_argument("--oid", required=True, help="OID to query")
    parser.add_argument("--warn", type=float, default=None, help="Warning threshold")
    parser.add_argument("--crit", type=float, default=None, help="Critical threshold")
    parser.add_argument("--community", default=os.environ.get("NAGIOS_SNMP_COMMUNITY", "public"), help="SNMP community string")
    parser.add_argument("--version", default=os.environ.get("NAGIOS_SNMP_VERSION", "2c"), help="SNMP version (1, 2c)")
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("NAGIOS_SNMP_TIMEOUT", "30")), help="Timeout in seconds")
    args = parser.parse_args()

    exit_code, value = snmp_get(args.host, args.oid, args.community, args.version, args.timeout)

    if exit_code != OK:
        print(f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {value}")
        sys.exit(exit_code)

    # Try numeric comparison if thresholds provided
    if args.warn is not None and args.crit is not None:
        try:
            numeric_value = float(value)
            if numeric_value >= args.crit:
                print(f"CRITICAL - {args.oid} = {value} (>= {args.crit})")
                sys.exit(CRITICAL)
            elif numeric_value >= args.warn:
                print(f"WARNING - {args.oid} = {value} (>= {args.warn})")
                sys.exit(WARNING)
            else:
                print(f"OK - {args.oid} = {value}")
                sys.exit(OK)
        except ValueError:
            print(f"OK - {args.oid} = {value}")
            sys.exit(OK)

    print(f"OK - {args.oid} = {value}")
    sys.exit(OK)


if __name__ == "__main__":
    main()
