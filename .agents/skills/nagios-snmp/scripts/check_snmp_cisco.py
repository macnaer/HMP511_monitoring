#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pysnmp>=6.0.0",
# ]
# ///
"""
Cisco device SNMP check for Nagios.

Usage:
    check_snmp_cisco.py --host HOST --check CHECK [--warn WARN] [--crit CRIT] [--interface INTERFACE]

Available checks:
    temperature  - System temperature
    fan          - Fan status
    psu          - Power supply status
    storage      - Flash/storage usage percentage
    cpu          - CPU utilization
    uptime       - Device uptime
    interface    - Interface status (use --interface for specific port, or check all admin-up ports)

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

# Cisco specific OIDs
CISCO_OIDS = {
    # Temperature
    "temp_alarm": "1.3.6.1.4.1.9.5.1.2.13.0",
    "temp_value": "1.3.6.1.4.1.9.5.1.2.11.0",

    # Fan status
    "fan_status": "1.3.6.1.4.1.9.9.13.1.4.1.3.1004",

    # PSU status
    "psu_status": "1.3.6.1.4.1.9.9.13.1.5.1.3.1003",

    # Storage (hrStorage MIB)
    "storage_total": "1.3.6.1.2.1.25.2.3.1.5.3",
    "storage_used": "1.3.6.1.2.1.25.2.3.1.6.3",

    # CPU (CISCO-PROCESS-MIB)
    "cpu_5min": "1.3.6.1.4.1.9.9.109.1.1.1.1.8.1",

    # Uptime
    "uptime": "1.3.6.1.2.1.1.3.0",

    # Interface MIB (IF-MIB)
    "if_descr": "1.3.6.1.2.1.2.2.1.2",
    "if_admin_status": "1.3.6.1.2.1.2.2.1.7",
    "if_oper_status": "1.3.6.1.2.1.2.2.1.8",
}

# ifOperStatus values
OPER_STATUS = {
    1: "UP",
    2: "DOWN",
    3: "testing",
    4: "unknown",
    5: "dormant",
    6: "notPresent",
    7: "lowerLayerDown",
}

# ifAdminStatus values
ADMIN_STATUS = {
    1: "UP",
    2: "DOWN",
}

# Fan/PSU status mappings
FAN_STATUS = {
    1: "normal",
    2: "warning",
    3: "critical",
    4: "not functioning",
}

PSU_STATUS = {
    1: "normal",
    2: "warning",
    3: "critical",
    4: "not present",
    5: "not functioning",
}


def none_or_float(val):
    if val is None or isinstance(val, str) and val.lower() == "none":
        return None
    return float(val)


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


def snmp_walk(host: str, oid: str, community: str, version: str, timeout: int) -> tuple[int, list]:
    """SNMP walk a table OID, return (exit_code, list of (index, value))."""
    results = []
    try:
        for error_indication, error_status, error_index, var_binds in nextCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1 if version == "1" else 2),
            UdpTransportTarget((host, 161), timeout=timeout, retries=2),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=True,
        ):
            if error_indication:
                return CRITICAL, f"SNMP error: {error_indication}"
            if error_status:
                return CRITICAL, f"SNMP error: {error_status.prettyPrint()}"

            for var_bind in var_binds:
                oid_full, value = var_bind
                # Extract the last sub-OID as the index
                oid_str = oid_full.prettyPrint()
                idx_str = oid_str.rsplit(".", 1)[-1]
                try:
                    idx = int(idx_str)
                except ValueError:
                    idx = idx_str
                results.append((idx, value.prettyPrint()))

        return OK, results
    except Exception as e:
        return UNKNOWN, f"Exception: {e}"


def check_temperature(host: str, community: str, version: str, timeout: int,
                      warn: float, crit: float) -> tuple[int, str]:
    """Check Cisco system temperature."""
    # Check alarm status first (1=normal, 2=warning, 3=critical)
    exit_code, value = snmp_get(host, CISCO_OIDS["temp_alarm"], community, version, timeout)
    if exit_code == OK:
        try:
            alarm = int(value)
            if alarm >= 2:
                return CRITICAL, f"Temperature alarm active (status: {alarm})"
        except (ValueError, TypeError):
            pass

    # Get temperature value
    exit_code, value = snmp_get(host, CISCO_OIDS["temp_value"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query temperature OID"

    try:
        temp_milli = int(value)
        temp_c = temp_milli / 1000.0
        if warn is not None and crit is not None:
            if temp_c >= crit:
                return CRITICAL, f"Temperature: {temp_c:.1f}C (>={crit}C)"
            elif temp_c >= warn:
                return WARNING, f"Temperature: {temp_c:.1f}C (>={warn}C)"
        return OK, f"Temperature: {temp_c:.1f}C"
    except (ValueError, TypeError):
        return UNKNOWN, f"Invalid temperature value: {value}"


def check_fan(host: str, community: str, version: str, timeout: int) -> tuple[int, str]:
    """Check Cisco fan status."""
    exit_code, value = snmp_get(host, CISCO_OIDS["fan_status"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query fan status OID"

    try:
        status = int(value)
        status_text = FAN_STATUS.get(status, f"unknown ({status})")
        if status >= 3:
            return CRITICAL, f"Fan status: {status_text}"
        elif status == 2:
            return WARNING, f"Fan status: {status_text}"
        return OK, f"Fan status: {status_text}"
    except (ValueError, TypeError):
        return UNKNOWN, f"Invalid fan status: {value}"


def check_psu(host: str, community: str, version: str, timeout: int) -> tuple[int, str]:
    """Check Cisco power supply status."""
    exit_code, value = snmp_get(host, CISCO_OIDS["psu_status"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query PSU status OID"

    try:
        status = int(value)
        status_text = PSU_STATUS.get(status, f"unknown ({status})")
        if status >= 3:
            return CRITICAL, f"PSU status: {status_text}"
        elif status == 2:
            return WARNING, f"PSU status: {status_text}"
        return OK, f"PSU status: {status_text}"
    except (ValueError, TypeError):
        return UNKNOWN, f"Invalid PSU status: {value}"


def check_storage(host: str, community: str, version: str, timeout: int,
                  warn: float, crit: float) -> tuple[int, str]:
    """Check flash/storage usage percentage."""
    exit_code_total, value_total = snmp_get(host, CISCO_OIDS["storage_total"], community, version, timeout)
    exit_code_used, value_used = snmp_get(host, CISCO_OIDS["storage_used"], community, version, timeout)

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
                return CRITICAL, f"Storage: {percent:.1f}% used ({used}/{total})"
            elif percent >= warn:
                return WARNING, f"Storage: {percent:.1f}% used ({used}/{total})"
        return OK, f"Storage: {percent:.1f}% used ({used}/{total})"
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid storage data"


def check_cpu(host: str, community: str, version: str, timeout: int,
              warn: float, crit: float) -> tuple[int, str]:
    """Check CPU utilization (5-minute average)."""
    exit_code, value = snmp_get(host, CISCO_OIDS["cpu_5min"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query CPU utilization OID"

    try:
        cpu = int(value)
        if warn is not None and crit is not None:
            if cpu >= crit:
                return CRITICAL, f"CPU: {cpu}% (>={crit}%)"
            elif cpu >= warn:
                return WARNING, f"CPU: {cpu}% (>={warn}%)"
        return OK, f"CPU: {cpu}%"
    except (ValueError, TypeError):
        return UNKNOWN, f"Invalid CPU value: {value}"


def check_uptime(host: str, community: str, version: str, timeout: int) -> tuple[int, str]:
    """Check device uptime."""
    exit_code, value = snmp_get(host, CISCO_OIDS["uptime"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query uptime OID"

    try:
        uptime_ticks = int(value)
        uptime_seconds = uptime_ticks // 100
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        return OK, f"Uptime: {days}d {hours}h {minutes}m"
    except (ValueError, TypeError):
        return OK, f"Uptime: {value}"


def check_interface(host: str, community: str, version: str, timeout: int,
                    interface: str) -> tuple[int, str]:
    """Check interface(s) status.

    If interface is specified, check that single port by name.
    If interface is None/empty, check all admin-up interfaces.
    """
    # Walk ifDescr table to get all interface names and indices
    exit_code, descrs = snmp_walk(host, CISCO_OIDS["if_descr"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, f"Cannot walk ifDescr: {descrs}"

    if not descrs:
        return UNKNOWN, "No interfaces found on device"

    if interface and interface.lower() not in ("none", ""):
        # Check a specific interface
        if_index = None
        for idx, name in descrs:
            if name == interface:
                if_index = idx
                break

        if if_index is None:
            available = ", ".join(name for _, name in descrs)
            return UNKNOWN, f"Interface '{interface}' not found (available: {available})"

        # Query ifOperStatus for this specific interface
        oid = f"{CISCO_OIDS['if_oper_status']}.{if_index}"
        exit_code, value = snmp_get(host, oid, community, version, timeout)
        if exit_code != OK:
            return UNKNOWN, f"Cannot query oper status for {interface}: {value}"

        try:
            oper = int(value)
            status_text = OPER_STATUS.get(oper, f"unknown ({oper})")
            if oper == 1:
                return OK, f"Interface {interface} is UP"
            elif oper == 2:
                return CRITICAL, f"Interface {interface} is DOWN"
            else:
                return WARNING, f"Interface {interface} is {status_text}"
        except (ValueError, TypeError):
            return UNKNOWN, f"Invalid oper status value: {value}"
    else:
        # Walk ifAdminStatus to find all admin-up interfaces
        exit_code, admin_statuses = snmp_walk(
            host, CISCO_OIDS["if_admin_status"], community, version, timeout
        )
        if exit_code != OK:
            return UNKNOWN, f"Cannot walk ifAdminStatus: {admin_statuses}"

        admin_up_indices = set()
        for idx, value in admin_statuses:
            try:
                if int(value) == 1:  # 1 = admin UP
                    admin_up_indices.add(idx)
            except ValueError:
                pass

        if not admin_up_indices:
            return OK, "No admin-up interfaces found"

        # Walk ifOperStatus for all interfaces
        exit_code, oper_statuses = snmp_walk(
            host, CISCO_OIDS["if_oper_status"], community, version, timeout
        )
        if exit_code != OK:
            return UNKNOWN, f"Cannot walk ifOperStatus: {oper_statuses}"

        # Build name lookup
        name_map = {idx: name for idx, name in descrs}

        down_ports = []
        for idx, value in oper_statuses:
            if idx not in admin_up_indices:
                continue
            try:
                oper = int(value)
                if oper == 2:  # DOWN
                    port_name = name_map.get(idx, f"ifIndex.{idx}")
                    down_ports.append(port_name)
            except ValueError:
                pass

        total_admin_up = len(admin_up_indices)

        if not down_ports:
            return OK, f"All interfaces up ({total_admin_up} ports)"
        else:
            down_list = ", ".join(down_ports)
            return CRITICAL, f"Interface(s) down: {down_list} ({len(down_ports)}/{total_admin_up} ports down)"


def main():
    parser = argparse.ArgumentParser(description="Cisco SNMP check for Nagios")
    parser.add_argument("--host", required=True, help="Target host IP or hostname")
    parser.add_argument("--check", required=True,
                        choices=["temperature", "fan", "psu", "storage", "cpu", "uptime", "interface"],
                        help="Check type to perform")
    parser.add_argument("--warn", type=none_or_float, default=None, help="Warning threshold")
    parser.add_argument("--crit", type=none_or_float, default=None, help="Critical threshold")
    parser.add_argument("--interface", default=None, help="Interface name to check (e.g., GigabitEthernet0/1)")
    parser.add_argument("--community", default=os.environ.get("NAGIOS_SNMP_COMMUNITY", "public"),
                        help="SNMP community string")
    parser.add_argument("--version", default=os.environ.get("NAGIOS_SNMP_VERSION", "2c"),
                        help="SNMP version (1, 2c)")
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("NAGIOS_SNMP_TIMEOUT", "30")),
                        help="Timeout in seconds")
    args = parser.parse_args()

    checks = {
        "temperature": lambda: check_temperature(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
        "fan": lambda: check_fan(args.host, args.community, args.version, args.timeout),
        "psu": lambda: check_psu(args.host, args.community, args.version, args.timeout),
        "storage": lambda: check_storage(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
        "cpu": lambda: check_cpu(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
        "uptime": lambda: check_uptime(args.host, args.community, args.version, args.timeout),
        "interface": lambda: check_interface(args.host, args.community, args.version, args.timeout, args.interface),
    }

    exit_code, message = checks[args.check]()
    print(f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
