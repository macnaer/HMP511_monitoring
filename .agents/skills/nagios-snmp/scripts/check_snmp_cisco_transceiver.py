#!/usr/bin/env python3
"""
Cisco transceiver SNMP check for Nagios.

Monitors SFP transceiver metrics: temperature, voltage, TX power, RX power.
Uses CISCO-ENTITY-SENSOR-MIB to query diagnostic data.

Usage:
    check_snmp_cisco_transceiver.py --host HOST --interface INTERFACE [--warn THRESH] [--crit THRESH]

Exit codes:
    0 = OK
    1 = WARNING
    2 = CRITICAL
    3 = UNKNOWN
"""

import argparse
import asyncio
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


OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

# ENTITY-MIB OIDs
ENT_PHYSICAL_CLASS = "1.3.6.1.2.1.47.1.1.1.1.5"
ENT_PHYSICAL_NAME = "1.3.6.1.2.1.47.1.1.1.1.7"

# CISCO-ENTITY-SENSOR-MIB OIDs
ENT_SENSOR_TYPE = "1.3.6.1.4.1.9.9.91.1.1.1.1.1"
ENT_SENSOR_SCALE = "1.3.6.1.4.1.9.9.91.1.1.1.1.2"
ENT_SENSOR_VALUE = "1.3.6.1.4.1.9.9.91.1.1.1.1.4"
ENT_SENSOR_STATUS = "1.3.6.1.4.1.9.9.91.1.1.1.1.5"
ENT_SENSOR_THRESH_TABLE = "1.3.6.1.4.1.9.9.91.1.2.1.1"

# Sensor types (CISCO-ENTITY-SENSOR-MIB::EntSensorType)
SENSOR_TYPES = {
    1: "voltage",
    3: "current",
    6: "temperature",
    8: "dBm",
}

# Sensor status
SENSOR_STATUS = {
    1: "ok",
    2: "unavailable",
    3: "nonoperational",
}

# Sensor scales (CISCO-ENTITY-SENSOR-MIB::EntSensorScale)
SENSOR_SCALES = {
    1: -24,  # yocto
    2: -21,  # zepto
    3: -18,  # atto
    4: -15,  # femto
    5: -12,  # pico
    6: -9,   # nano
    7: -6,   # micro
    8: -3,   # milli
    9: 0,    # units (base)
    10: 3,   # kilo
    11: 6,   # mega
    12: 9,   # giga
    13: 12,  # tera
    14: 15,  # peta
    15: 18,  # exa
    16: 21,  # zetta
    17: 24,  # yotta
}


async def snmp_get(host, oid, community, version, timeout):
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
            return OK, var_binds[0][1].prettyPrint()
        return UNKNOWN, "No value returned"
    except Exception as e:
        return UNKNOWN, "Exception: %s" % str(e)


async def snmp_walk(host, oid, community, version, timeout):
    results = []
    try:
        async for (error_indication, error_status, error_index, var_binds) in next_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1 if version == "1" else 2),
            await UdpTransportTarget.create((host, 161), timeout=timeout, retries=2),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=True,
        ):
            if error_indication:
                return CRITICAL, "SNMP error: %s" % error_indication, []
            if error_status:
                return CRITICAL, "SNMP error: %s" % error_status.prettyPrint(), []
            for var_bind in var_binds:
                oid_str = var_bind[0].prettyPrint()
                idx_str = oid_str.rsplit(".", 1)[-1]
                try:
                    idx = int(idx_str)
                except ValueError:
                    idx = idx_str
                results.append((idx, var_bind[1].prettyPrint()))
        return OK, "", results
    except Exception as e:
        return UNKNOWN, "Exception: %s" % str(e), []


def none_or_float(val):
    if val is None or isinstance(val, str) and val.lower() in ("none", ""):
        return None
    return float(val)


async def check_transceiver(host, interface, community, version, timeout, warn_temp, crit_temp,
                            warn_volt, crit_volt, warn_tx, crit_tx, warn_rx, crit_rx):
    # Step 1: Walk entPhysicalName to find entity index for the target interface
    code, msg, phys_names = await snmp_walk(host, ENT_PHYSICAL_NAME, community, version, timeout)
    if code != OK:
        return UNKNOWN, "Cannot walk entPhysicalName: %s" % msg

    # Find entity indices matching the interface name
    target_entities = set()
    for idx, name in phys_names:
        if interface.lower() in name.lower():
            target_entities.add(idx)

    if not target_entities:
        available = [name for _, name in phys_names[:20]]
        return UNKNOWN, "Interface '%s' not found in entity table (found: %s)" % (interface, ", ".join(available))

    # Step 2: Walk entPhysicalClass to understand entity hierarchy
    code, msg, phys_classes = await snmp_walk(host, ENT_PHYSICAL_CLASS, community, version, timeout)
    # entityPhysicalClass: 3=chassis, 5=container, 9=module, 10=port, 11=stack

    # Build entity -> class mapping
    entity_class = {idx: int(cls_val) for idx, cls_val in phys_classes if cls_val.isdigit()}

    # Find the port entity index (class=10 for port)
    port_entity = None
    for idx in target_entities:
        if entity_class.get(idx) == 10:
            port_entity = idx
            break

    if port_entity is None:
        port_entity = min(target_entities)

    # Step 3: Walk entSensorType to find all sensors
    code, msg, sensor_types = await snmp_walk(host, ENT_SENSOR_TYPE, community, version, timeout)
    if code != OK:
        return UNKNOWN, "Cannot walk entSensorType: %s" % msg

    # Step 4: Walk entSensorValue
    code, msg, sensor_values = await snmp_walk(host, ENT_SENSOR_VALUE, community, version, timeout)
    if code != OK:
        return UNKNOWN, "Cannot walk entSensorValue: %s" % msg

    # Step 5: Walk entSensorScale
    code, msg, sensor_scales = await snmp_walk(host, ENT_SENSOR_SCALE, community, version, timeout)
    # Build scale map
    scale_map = {}
    if code == OK:
        for idx, val in sensor_scales:
            try:
                scale_map[idx] = int(val)
            except ValueError:
                pass

    # Step 6: Walk entSensorStatus
    code, msg, sensor_statuses = await snmp_walk(host, ENT_SENSOR_STATUS, community, version, timeout)
    status_map = {}
    if code == OK:
        for idx, val in sensor_statuses:
            try:
                status_map[idx] = int(val)
            except ValueError:
                pass

    # Build sensor type map
    type_map = {}
    for idx, val in sensor_types:
        try:
            type_map[idx] = int(val)
        except ValueError:
            pass

    # Build value map
    value_map = {}
    for idx, val in sensor_values:
        try:
            value_map[idx] = float(val)
        except ValueError:
            pass

    # Find sensors near the port entity (within +/- 10 indices)
    # On Cisco, sensors for a port are typically at nearby entity indices
    SENSORS_FOUND = {}

    for sensor_idx in type_map:
        sensor_type = type_map[sensor_idx]
        if sensor_type not in SENSOR_TYPES:
            continue
        if sensor_idx not in value_map:
            continue

        # Check if this sensor is near our port entity
        # On Cisco, transceiver sensors are typically at indices close to the port
        if abs(sensor_idx - port_entity) > 20:
            # Also check if any of the target entities are close
            near = any(abs(sensor_idx - e) <= 20 for e in target_entities)
            if not near:
                continue

        type_name = SENSOR_TYPES[sensor_type]
        value = value_map[sensor_idx]

        # Apply scale
        scale_exp = SENSOR_SCALES.get(scale_map.get(sensor_idx, 9), 0)
        real_value = value * (10 ** scale_exp)

        # Skip if sensor status is not OK
        if status_map.get(sensor_idx) == 3:
            continue

        if type_name not in SENSORS_FOUND:
            SENSORS_FOUND[type_name] = real_value

    if not SENSORS_FOUND:
        return UNKNOWN, "No transceiver sensors found near entity %d for interface %s" % (port_entity, interface)

    # Evaluate results
    overall = OK
    parts = []
    perfdata = []

    # Temperature check
    if "temperature" in SENSORS_FOUND:
        temp = SENSORS_FOUND["temperature"]
        parts.append("Temp: %.1fC" % temp)
        perfdata.append("temp=%.1f" % temp)
        if crit_temp is not None and temp >= crit_temp:
            overall = max(overall, CRITICAL)
        elif warn_temp is not None and temp >= warn_temp:
            overall = max(overall, WARNING)

    # Voltage check
    if "voltage" in SENSORS_FOUND:
        volt = SENSORS_FOUND["voltage"]
        parts.append("Volt: %.2fV" % volt)
        perfdata.append("volt=%.2f" % volt)
        if crit_volt is not None and (volt >= crit_volt or volt <= -crit_volt):
            overall = max(overall, CRITICAL)
        elif warn_volt is not None and (volt >= warn_volt or volt <= -warn_volt):
            overall = max(overall, WARNING)

    # TX Power check
    if "dBm" in SENSORS_FOUND:
        tx = SENSORS_FOUND["dBm"]
        parts.append("TX: %.1fdBm" % tx)
        perfdata.append("tx=%.1f" % tx)
        if crit_tx is not None and tx >= crit_tx:
            overall = max(overall, CRITICAL)
        elif warn_tx is not None and tx >= warn_tx:
            overall = max(overall, WARNING)

    if not parts:
        return UNKNOWN, "No readable sensor values for %s" % interface

    message = ", ".join(parts)
    perf = " | " + " ".join(perfdata)

    labels = {0: "OK", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}
    return overall, "%s %s %s%s" % (labels[overall], interface, message, perf)


def main():
    parser = argparse.ArgumentParser(description="Cisco transceiver SNMP check for Nagios")
    parser.add_argument("--host", required=True, help="Target host IP or hostname")
    parser.add_argument("--interface", required=True, help="Interface name (e.g., GigabitEthernet0/45)")
    parser.add_argument("--community", default=os.environ.get("NAGIOS_SNMP_COMMUNITY", "public"),
                        help="SNMP community string")
    parser.add_argument("--version", default=os.environ.get("NAGIOS_SNMP_VERSION", "2c"),
                        help="SNMP version (1, 2c)")
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("NAGIOS_SNMP_TIMEOUT", "30")),
                        help="Timeout in seconds")
    parser.add_argument("--warn-temp", type=none_or_float, default=None, help="Temperature warning threshold")
    parser.add_argument("--crit-temp", type=none_or_float, default=None, help="Temperature critical threshold")
    parser.add_argument("--warn-volt", type=none_or_float, default=None, help="Voltage warning threshold")
    parser.add_argument("--crit-volt", type=none_or_float, default=None, help="Voltage critical threshold")
    parser.add_argument("--warn-tx", type=none_or_float, default=None, help="TX power warning threshold (dBm)")
    parser.add_argument("--crit-tx", type=none_or_float, default=None, help="TX power critical threshold (dBm)")
    parser.add_argument("--warn-rx", type=none_or_float, default=None, help="RX power warning threshold (dBm)")
    parser.add_argument("--crit-rx", type=none_or_float, default=None, help="RX power critical threshold (dBm)")
    args = parser.parse_args()

    try:
        exit_code, message = asyncio.run(check_transceiver(
            args.host, args.interface, args.community, args.version, args.timeout,
            args.warn_temp, args.crit_temp,
            args.warn_volt, args.crit_volt,
            args.warn_tx, args.crit_tx,
            args.warn_rx, args.crit_rx,
        ))
        labels = {0: "OK", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}
        print("%s - %s" % (labels[exit_code], message))
        sys.exit(exit_code)
    except Exception as e:
        print("UNKNOWN - Script error: %s" % str(e))
        sys.exit(UNKNOWN)


if __name__ == "__main__":
    main()
