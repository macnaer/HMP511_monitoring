#!/bin/bash
# MikroTik RouterOS storage usage check via SNMP
#
# Auto-discovers hrStorage entries, skips RAM (type 2/3).
# Returns OK/WARNING/CRITICAL based on used percentage.
#
# Output format: STATUS - X.X/YG used - Z%
#
# Usage: check_snmp_storage_mikrotik.sh <host> <warn> <crit> [community]
# Example: check_snmp_storage_mikrotik.sh 192.168.1.2 80 90 LibreNms

OK=0
WARNING=1
CRITICAL=2
UNKNOWN=3

HOST=$1
WARN=$2
CRIT=$3
COMMUNITY=${4:-${NAGIOS_SNMP_COMMUNITY:-public}}
TIMEOUT=${NAGIOS_SNMP_TIMEOUT:-30}

if [ -z "$CRIT" ]; then
    echo "UNKNOWN - Missing arguments. Usage: $0 <host> <warn> <crit> [community]"
    exit $UNKNOWN
fi

OID_TYPE="1.3.6.1.2.1.25.2.3.1.2"
OID_DESCR="1.3.6.1.2.1.25.2.3.1.3"
OID_ALLOC="1.3.6.1.2.1.25.2.3.1.4"
OID_SIZE="1.3.6.1.2.1.25.2.3.1.5"
OID_USED="1.3.6.1.2.1.25.2.3.1.6"

snmp_get_val() {
    local oid=$1
    local raw
    raw=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t "$TIMEOUT" "$HOST" "$oid" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$raw" ] && ! echo "$raw" | grep -qi "no such"; then
        echo "$raw" | tr -d '" '
        return 0
    fi
    return 1
}

snmp_walk_oids() {
    local oid=$1
    local raw
    raw=$(snmpwalk -v2c -c "$COMMUNITY" -Oqn -t "$TIMEOUT" "$HOST" "$oid" 2>/dev/null)
    if [ -n "$raw" ]; then
        echo "$raw"
        return 0
    fi
    return 1
}

format_bytes() {
    local bytes=$1
    if [ "$bytes" -ge 1073741824 ]; then
        echo "$(echo "scale=1; $bytes / 1073741824" | bc)G"
    elif [ "$bytes" -ge 1048576 ]; then
        echo "$(echo "scale=1; $bytes / 1048576" | bc)M"
    else
        echo "${bytes}B"
    fi
}

walk_output=$(snmp_walk_oids "$OID_TYPE")
if [ -z "$walk_output" ]; then
    echo "UNKNOWN - SNMP query failed for $HOST"
    exit $UNKNOWN
fi

STORAGE_SIZE=""
STORAGE_USED=""
STORAGE_DESCR=""

while IFS= read -r line; do
    [ -z "$line" ] && continue
    oid=$(echo "$line" | awk '{print $1}')
    type_val=$(echo "$line" | awk '{print $2}' | tr -d '"')
    idx="${oid##*.}"
    if [ "$type_val" = "2" ] || [ "$type_val" = "3" ]; then
        continue
    fi
    size_raw=$(snmp_get_val "${OID_SIZE}.${idx}")
    if [ -z "$size_raw" ] || [ "$size_raw" -le 0 ] 2>/dev/null; then
        continue
    fi
    used_raw=$(snmp_get_val "${OID_USED}.${idx}")
    alloc_raw=$(snmp_get_val "${OID_ALLOC}.${idx}")
    descr_raw=$(snmp_get_val "${OID_DESCR}.${idx}")
    if [ -z "$used_raw" ] || [ -z "$alloc_raw" ] || [ "$alloc_raw" -le 0 ] 2>/dev/null; then
        continue
    fi
    STORAGE_SIZE=$((size_raw * alloc_raw))
    STORAGE_USED=$((used_raw * alloc_raw))
    STORAGE_DESCR="$descr_raw"
    break
done <<< "$walk_output"

if [ -z "$STORAGE_SIZE" ] || [ -z "$STORAGE_USED" ]; then
    echo "UNKNOWN - No usable storage found on $HOST"
    exit $UNKNOWN
fi

if [ "$STORAGE_SIZE" -le 0 ]; then
    echo "UNKNOWN - Invalid storage size: $STORAGE_SIZE"
    exit $UNKNOWN
fi

USED_PCT=$(echo "scale=0; $STORAGE_USED * 100 / $STORAGE_SIZE" | bc 2>/dev/null)
if [ -z "$USED_PCT" ]; then
    USED_PCT=$((STORAGE_USED * 100 / STORAGE_SIZE))
fi

USED_STR=$(format_bytes $STORAGE_USED)
TOTAL_STR=$(format_bytes $STORAGE_SIZE)

if [ "$USED_PCT" -ge "$CRIT" ]; then
    echo "CRITICAL - ${USED_STR}/${TOTAL_STR} used - ${USED_PCT}%"
    exit $CRITICAL
elif [ "$USED_PCT" -ge "$WARN" ]; then
    echo "WARNING - ${USED_STR}/${TOTAL_STR} used - ${USED_PCT}%"
    exit $WARNING
else
    echo "OK - ${USED_STR}/${TOTAL_STR} used - ${USED_PCT}%"
    exit $OK
fi
