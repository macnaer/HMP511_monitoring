#!/bin/bash
# MikroTik RouterOS storage usage check via SNMP
#
# Uses MikroTik proprietary MIB (1.3.6.1.4.1.14988.1.1.7)
# to query flash/disk storage entries. Skips memory (type 2).
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

OID_MT_NAME="1.3.6.1.4.1.14988.1.1.7.1.1.1"
OID_MT_TYPE="1.3.6.1.4.1.14988.1.1.7.1.1.2"
OID_MT_SIZE="1.3.6.1.4.1.14988.1.1.7.1.1.3"
OID_MT_USED="1.3.6.1.4.1.14988.1.1.7.1.1.4"

snmp_get_val() {
    local oid=$1
    local raw
    raw=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t "$TIMEOUT" "$HOST" "$oid" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$raw" ] && ! echo "$raw" | grep -qi "no such"; then
        echo "$raw" | tr -d '"'
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

STORAGE_SIZE=""
STORAGE_USED=""
STORAGE_NAME=""

for TRY_IDX in 1 2 3 4 5 6 7 8 9 10; do
    TYPE_RAW=$(snmp_get_val "${OID_MT_TYPE}.${TRY_IDX}")
    [ -z "$TYPE_RAW" ] && continue
    if [ "$TYPE_RAW" = "2" ]; then
        continue
    fi
    SIZE_RAW=$(snmp_get_val "${OID_MT_SIZE}.${TRY_IDX}")
    if [ -z "$SIZE_RAW" ] || [ "$SIZE_RAW" -le 0 ] 2>/dev/null; then
        continue
    fi
    USED_RAW=$(snmp_get_val "${OID_MT_USED}.${TRY_IDX}")
    if [ -z "$USED_RAW" ]; then
        continue
    fi
    NAME_RAW=$(snmp_get_val "${OID_MT_NAME}.${TRY_IDX}")
    STORAGE_SIZE=$SIZE_RAW
    STORAGE_USED=$USED_RAW
    STORAGE_NAME="${NAME_RAW:-storage}"
    break
done

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
