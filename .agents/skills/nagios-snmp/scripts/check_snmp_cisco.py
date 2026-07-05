#!/usr/bin/env python3
"""
Cisco device SNMP check for Nagios.

Usage:
    check_snmp_cisco.py --host HOST --check CHECK [--warn WARN] [--crit CRIT]

Available checks:
    temperature  - System temperature
    fan          - Fan status
    psu          - Power supply status
    storage      - Flash/storage usage percentage
    cpu          - CPU utilization
    uptime       - Device uptime

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
    print("UNKNOWN - pysnmp import failed: %s" % e)
    sys.exit(3)


OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

CISCO_OIDS = {
    "temp_alarm": "1.3.6.1.4.1.9.5.1.2.13.0",
    "temp_value": "1.3.6.1.4.1.9.5.1.2.11.0",
    "fan_status": "1.3.6.1.4.1.9.9.13.1.4.1.3.1004",
    "psu_status": "1.3.6.1.4.1.9.9.13.1.5.1.3.1003",
    "storage_total": "1.3.6.1.2.1.25.2.3.1.5.3",
    "storage_used": "1.3.6.1.2.1.25.2.3.1.6.3",
    "cpu_5min": "1.3.6.1.4.1.9.9.109.1.1.1.1.8.1",
    "uptime": "1.3.6.1.2.1.1.3.0",
}

FAN_STATUS = {1: "normal", 2: "warning", 3: "critical", 4: "not functioning"}
PSU_STATUS = {1: "normal", 2: "warning", 3: "critical", 4: "not present", 5: "not functioning"}


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


def check_temperature(host, community, version, timeout, warn, crit):
    exit_code, value = snmp_get(host, CISCO_OIDS["temp_alarm"], community, version, timeout)
    if exit_code == OK:
        try:
            alarm = int(value)
            if alarm == 1:
                return CRITICAL, "Temperature alarm active"
        except (ValueError, TypeError):
            pass

    exit_code, value = snmp_get(host, CISCO_OIDS["temp_value"], community, version, timeout)
    if exit_code != OK:
        return UNKNOWN, "Cannot query temperature OID"

    try:
        temp = int(value)
        if warn is not None and crit is not None:
            if temp >= crit:
                return CRITICAL, "Temperature: %sC (>=%sC)" % (temp, crit)
            elif temp >= warn:
                return WARNING, "Temperature: %sC (>=%sC)" % (temp, warn)
        return OK, "Temperature: %sC" % temp
    except (ValueError, TypeError):
        return UNKNOWN, "Invalid temperature value: %s" % value


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


def main():
    parser = argparse.ArgumentParser(description="Cisco SNMP check for Nagios")
    parser.add_argument("--host", required=True, help="Target host IP or hostname")
    parser.add_argument("--check", required=True,
                        choices=["temperature", "fan", "psu", "storage", "cpu", "uptime"],
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
            "temperature": lambda: check_temperature(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
            "fan": lambda: check_fan(args.host, args.community, args.version, args.timeout),
            "psu": lambda: check_psu(args.host, args.community, args.version, args.timeout),
            "storage": lambda: check_storage(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
            "cpu": lambda: check_cpu(args.host, args.community, args.version, args.timeout, args.warn, args.crit),
            "uptime": lambda: check_uptime(args.host, args.community, args.version, args.timeout),
        }

        exit_code, message = checks[args.check]()
        print("%s - %s" % (["OK", "WARNING", "CRITICAL", "UNKNOWN"][exit_code], message))
        sys.exit(exit_code)

    except Exception as e:
        print("UNKNOWN - Script error: %s" % str(e))
        sys.exit(UNKNOWN)


if __name__ == "__main__":
    main()
