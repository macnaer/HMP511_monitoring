#!/usr/bin/env python3
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

try:
    from pysnmp.hlapi.v3arch.asyncio import (
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        get_cmd,
        next_cmd,
    )
except ImportError as e:
    print("UNKNOWN - pysnmp import failed: %s" % e)
    sys.exit(3)


import asyncio


OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

CISCO_OIDS = {
    "temp_alarm": "1.3.6.1.4.1.9.5.1.2.13.0",
    "temp_value": "1.3.6.1.4.1.9.5.1.2.11.0",
    "temp_status": "1.3.6.1.4.1.9.5.1.2.11.0",
    "temp_status_table": "1.3.6.1.4.1.9.9.13.1.3.1.3",
    "temp_status_entity": "1.3.6.1.4.1.9.9.91.1.1.1.1.4",
    "fan_status": "1.3.6.1.4.1.9.9.13.1.4.1.3.1004",
    "psu_status": "1.3.6.1.4.1.9.9.13.1.5.1.3.1003",
    "storage_total": "1.3.6.1.2.1.25.2.3.1.5.3",
    "storage_used": "1.3.6.1.2.1.25.2.3.1.6.3",
    "cpu_5min": "1.3.6.1.4.1.9.9.109.1.1.1.1.8.1",
    "uptime": "1.3.6.1.2.1.1.3.0",

    # Interface MIB (IF-MIB)
    "if_descr": "1.3.6.1.2.1.2.2.1.2",
    "if_admin_status": "1.3.6.1.2.1.2.2.1.7",
    "if_oper_status": "1.3.6.1.2.1.2.2.1.8",
}

OPER_STATUS = {
    1: "UP",
    2: "DOWN",
    3: "testing",
    4: "unknown",
    5: "dormant",
    6: "notPresent",
    7: "lowerLayerDown",
}

ADMIN_STATUS = {
    1: "UP",
    2: "DOWN",
}

FAN_STATUS = {1: "normal", 2: "warning", 3: "critical", 4: "not functioning"}
PSU_STATUS = {1: "normal", 2: "warning", 3: "critical", 4: "not present", 5: "not functioning"}


def none_or_float(val):
    if val is None or isinstance(val, str) and val.lower() == "none":
        return None
    return float(val)


def snmp_get(host, oid, community, version, timeout):
    return asyncio.run(_snmp_get_async(host, oid, community, version, timeout))


async def _snmp_get_async(host, oid, community, version, timeout):
    try:
        error_indication, error_status, error_index, var_binds = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1 if version == "1" else 2),
            await UdpTransportTarget.create((host, 161), timeout=timeout, retries=2),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
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


def snmp_walk(host, oid, community, version, timeout):
    """SNMP walk a table OID, return (exit_code, list of (index, value))."""
    return asyncio.run(_snmp_walk_async(host, oid, community, version, timeout))


async def _snmp_walk_async(host, oid, community, version, timeout):
    """SNMP walk a table OID, return (exit_code, list of (index, value))."""
    results = []
    try:
        results_data = await next_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1 if version == "1" else 2),
            await UdpTransportTarget.create((host, 161), timeout=timeout, retries=2),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=True,
        )
        for (error_indication, error_status, error_index, var_binds) in results_data:
            if error_indication:
                return CRITICAL, "SNMP error: %s" % error_indication
            if error_status:
                return CRITICAL, "SNMP error: %s" % error_status.prettyPrint()

            for var_bind in var_binds:
                oid_full, value = var_bind
                oid_str = oid_full.prettyPrint()
                idx_str = oid_str.rsplit(".", 1)[-1]
                try:
                    idx = int(idx_str)
                except ValueError:
                    idx = idx_str
                results.append((idx, value.prettyPrint()))

        return OK, results
    except Exception as e:
        return UNKNOWN, "Exception: %s" % str(e)


def check_temperature(host, community, version, timeout, warn, crit):
    exit_code, value = snmp_get(host, CISCO_OIDS["temp_alarm"], community, version, timeout)
    if exit_code == OK:
        try:
            alarm = int(value)
            if alarm >= 2:
                return CRITICAL, "Temperature alarm active (status: %s)" % alarm
        except (ValueError, TypeError):
            pass

    exit_code, value = snmp_get(host, CISCO_OIDS["temp_value"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query temperature OID"

    try:
        temp_milli = int(value)
        temp_c = temp_milli / 1000.0
        if warn is not None and crit is not None:
            if temp_c >= crit:
                return CRITICAL, "Temperature: %.1fC (>=%sC)" % (temp_c, crit)
            elif temp_c >= warn:
                return WARNING, "Temperature: %.1fC (>=%sC)" % (temp_c, warn)
        return OK, "Temperature: %.1fC" % temp_c
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid temperature value: %s" % value


def check_temperature_status(host, community, version, timeout):
    """Check temperature via status code with fallback OIDs and multi-sensor support.

    Status codes: 1=OK (normal), 2=WARNING (slightly heated), 3=CRITICAL (overheated)
    """
    sensors = []

    # Strategy 1: Scalar OID (returns 1/2/3 directly)
    exit_code, value = snmp_get(host, CISCO_OIDS["temp_status"], community, version, timeout)
    if exit_code == OK:
        try:
            status = int(value)
            if status in (1, 2, 3):
                sensors.append(("System Temp", status))
        except (ValueError, TypeError):
            pass

    # Strategy 2: CISCO-ENVMON-MIB table (may have multiple sensors)
    if not sensors:
        exit_code, results = snmp_walk(host, CISCO_OIDS["temp_status_table"], community, version, timeout)
        if exit_code == OK and results:
            for idx, value in results:
                try:
                    status = int(value)
                    if status in (1, 2, 3):
                        sensors.append(("Sensor %s" % idx, status))
                except (ValueError, TypeError):
                    continue

    # Strategy 3: CISCO-ENTITY-SENSOR-MIB table
    if not sensors:
        exit_code, results = snmp_walk(host, CISCO_OIDS["temp_status_entity"], community, version, timeout)
        if exit_code == OK and results:
            for idx, value in results:
                try:
                    status = int(value)
                    if status in (1, 2, 3):
                        sensors.append(("Entity Sensor %s" % idx, status))
                except (ValueError, TypeError):
                    continue

    if not sensors:
        return UNKNOWN, "Cannot determine temperature status from any OID"

    STATUS_MAP = {
        1: (OK, "Normal"),
        2: (WARNING, "Warning"),
        3: (CRITICAL, "Critical"),
    }

    overall_status = OK
    parts = []
    perfdata_parts = []

    for name, status in sensors:
        exit_code, label = STATUS_MAP.get(status, (UNKNOWN, "Unknown(%s)" % status))
        parts.append("%s: %s" % (name, label))
        perfdata_parts.append("%s=%d;1;3" % (name.lower().replace(" ", "_"), status))
        if exit_code > overall_status:
            overall_status = exit_code

    message = ", ".join(parts)
    perfdata = " | " + " ".join(perfdata_parts)

    STATUS_LABELS = {0: "OK", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}
    return overall_status, "%s - %s%s" % (STATUS_LABELS[overall_status], message, perfdata)


def check_fan(host, community, version, timeout):
    exit_code, value = snmp_get(host, CISCO_OIDS["fan_status"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query fan status OID"

    try:
        status = int(value)
        status_text = FAN_STATUS.get(status, "unknown (%s)" % status)
        if status >= 3:
            return CRITICAL, "Fan status: %s" % status_text
        elif status == 2:
            return WARNING, "Fan status: %s" % status_text
        return OK, "Fan status: %s" % status_text
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid fan status: %s" % value


def check_psu(host, community, version, timeout):
    exit_code, value = snmp_get(host, CISCO_OIDS["psu_status"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query PSU status OID"

    try:
        status = int(value)
        status_text = PSU_STATUS.get(status, "unknown (%s)" % status)
        if status >= 3:
            return CRITICAL, "PSU status: %s" % status_text
        elif status == 2:
            return WARNING, "PSU status: %s" % status_text
        return OK, "PSU status: %s" % status_text
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid PSU status: %s" % value


def check_storage(host, community, version, timeout, warn, crit):
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
                return CRITICAL, "Storage: %.1f%% used (%d/%d)" % (percent, used, total)
            elif percent >= warn:
                return WARNING, "Storage: %.1f%% used (%d/%d)" % (percent, used, total)
        return OK, "Storage: %.1f%% used (%d/%d)" % (percent, used, total)
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid storage data"


def check_cpu(host, community, version, timeout, warn, crit):
    exit_code, value = snmp_get(host, CISCO_OIDS["cpu_5min"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query CPU utilization OID"

    try:
        cpu = int(value)
        if warn is not None and crit is not None:
            if cpu >= crit:
                return CRITICAL, "CPU: %s%% (>=%s%%)" % (cpu, crit)
            elif cpu >= warn:
                return WARNING, "CPU: %s%% (>=%s%%)" % (cpu, warn)
        return OK, "CPU: %s%%" % cpu
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid CPU value: %s" % value


def check_uptime(host, community, version, timeout):
    exit_code, value = snmp_get(host, CISCO_OIDS["uptime"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query uptime OID"

    try:
        uptime_ticks = int(value)
        uptime_seconds = uptime_ticks // 100
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        return OK, "Uptime: %dd %dh %dm" % (days, hours, minutes)
    except (ValueError, TypeError):
        return OK, "Uptime: %s" % value


def check_interface(host, community, version, timeout, interface):
    """Check interface(s) status.

    If interface is specified, check that single port by name.
    If interface is None/empty, check all admin-up interfaces.
    """
    exit_code, descrs = snmp_walk(host, CISCO_OIDS["if_descr"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot walk ifDescr: %s" % (descrs,)

    if not descrs:
        return UNKNOWN, "No interfaces found on device"

    if interface and interface.lower() not in ("none", ""):
        if_index = None
        for idx, name in descrs:
            if name == interface:
                if_index = idx
                break

        if if_index is None:
            available = ", ".join(name for _, name in descrs)
            return UNKNOWN, "Interface '%s' not found (available: %s)" % (interface, available)

        oid = "%s.%s" % (CISCO_OIDS["if_oper_status"], if_index)
        exit_code, value = snmp_get(host, oid, community, version, timeout)
        if exit_code != OK:
            return UNKNOWN, "Cannot query oper status for %s: %s" % (interface, value)

        try:
            oper = int(value)
            status_text = OPER_STATUS.get(oper, "unknown (%s)" % oper)
            if oper == 1:
                return OK, "Interface %s is UP" % interface
            elif oper == 2:
                return CRITICAL, "Interface %s is DOWN" % interface
            else:
                return WARNING, "Interface %s is %s" % (interface, status_text)
        except (ValueError, TypeError):
            return UNKNOWN, "Invalid oper status value: %s" % value

    exit_code, admin_statuses = snmp_walk(
        host, CISCO_OIDS["if_admin_status"], community, version, timeout
    )
    if exit_code != OK:
        return UNKNOWN, "Cannot walk ifAdminStatus: %s" % (admin_statuses,)

    admin_up_indices = set()
    for idx, value in admin_statuses:
        try:
            if int(value) == 1:
                admin_up_indices.add(idx)
        except ValueError:
            pass

    if not admin_up_indices:
        return OK, "No admin-up interfaces found"

    exit_code, oper_statuses = snmp_walk(
        host, CISCO_OIDS["if_oper_status"], community, version, timeout
    )
    if exit_code != OK:
        return UNKNOWN, "Cannot walk ifOperStatus: %s" % (oper_statuses,)

    name_map = {idx: name for idx, name in descrs}

    down_ports = []
    for idx, value in oper_statuses:
        if idx not in admin_up_indices:
            continue
        try:
            oper = int(value)
            if oper == 2:
                port_name = name_map.get(idx, "ifIndex.%s" % idx)
                down_ports.append(port_name)
        except ValueError:
            pass

    total_admin_up = len(admin_up_indices)

    if not down_ports:
        return OK, "All interfaces up (%d ports)" % total_admin_up
    else:
        down_list = ", ".join(down_ports)
        return CRITICAL, "Interface(s) down: %s (%d/%d ports down)" % (down_list, len(down_ports), total_admin_up)


def main():
    parser = argparse.ArgumentParser(description="Cisco SNMP check for Nagios")
    parser.add_argument("--host", required=True, help="Target host IP or hostname")
    parser.add_argument("--check", required=True,
                        choices=["temperature", "temperature_status", "fan", "psu", "storage", "cpu", "uptime", "interface"],
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

    try:
        checks = {
            "temperature": lambda: check_temperature(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
            "temperature_status": lambda: check_temperature_status(args.host, args.community, args.version, args.timeout),
            "fan": lambda: check_fan(args.host, args.community, args.version, args.timeout),
            "psu": lambda: check_psu(args.host, args.community, args.version, args.timeout),
            "storage": lambda: check_storage(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
            "cpu": lambda: check_cpu(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
            "uptime": lambda: check_uptime(args.host, args.community, args.version, args.timeout),
            "interface": lambda: check_interface(args.host, args.community, args.version, args.timeout, args.interface),
        }

        exit_code, message = checks[args.check]()
        print("%s - %s" % (["OK", "WARNING", "CRITICAL", "UNKNOWN"][exit_code], message))
        sys.exit(exit_code)

    except Exception as e:
        print("UNKNOWN - Script error: %s" % str(e))
        sys.exit(UNKNOWN)


if __name__ == "__main__":
    main()
