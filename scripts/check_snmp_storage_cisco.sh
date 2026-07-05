#!/bin/bash
# check_snmp_storage_cisco.sh
# Cisco storage usage check via SNMP
#
# Usage: check_snmp_storage_cisco.sh <community> <host> <index> <warn> <crit>
# Example: check_snmp_storage_cisco.sh LibreNms 10.7.99.5 3 80 90

OK=0
WARNING=1
CRITICAL=2
UNKNOWN=3

COMMUNITY=$1
HOST=$2
INDEX=$3
WARN=$4
CRIT=$5

if [ -z "$CRIT" ]; then
    echo "UNKNOWN - Missing arguments. Usage: $0 <community> <host> <index> <warn> <crit>"
    exit $UNKNOWN
fi

OID_SIZE="1.3.6.1.2.1.25.2.3.1.5.${INDEX}"
OID_USED="1.3.6.1.2.1.25.2.3.1.6.${INDEX}"

# Get total storage size
SNMP_SIZE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -Oqv -t 30 "$HOST" "$OID_SIZE" 2>&1)
if [ $? -ne 0 ] || [ -z "$SNMP_SIZE_RAW" ] || echo "$SNMP_SIZE_RAW" | grep -qi "no such"; then
    echo "CRITICAL - SNMP query failed for hrStorageSize (index ${INDEX}): ${SNMP_SIZE_RAW}"
    exit $CRITICAL
fi

STORAGE_SIZE=$(echo "$SNMP_SIZE_RAW" | tr -d '" ' | head -n1)

# Get used storage
SNMP_USED_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -Oqv -t 30 "$HOST" "$OID_USED" 2>&1)
if [ $? -ne 0 ] || [ -z "$SNMP_USED_RAW" ] || echo "$SNMP_USED_RAW" | grep -qi "no such"; then
    echo "CRITICAL - SNMP query failed for hrStorageUsed (index ${INDEX}): ${SNMP_USED_RAW}"
    exit $CRITICAL
fi

STORAGE_USED=$(echo "$SNMP_USED_RAW" | tr -d '" ' | head -n1)

# Validate numeric values
if ! [[ "$STORAGE_SIZE" =~ ^[0-9]+$ ]]; then
    echo "UNKNOWN - Invalid storage size value: '${STORAGE_SIZE}' (raw: ${SNMP_SIZE_RAW})"
    exit $UNKNOWN
fi

if ! [[ "$STORAGE_USED" =~ ^[0-9]+$ ]]; then
    echo "UNKNOWN - Invalid storage used value: '${STORAGE_USED}' (raw: ${SNMP_USED_RAW})"
    exit $UNKNOWN
fi

if [ "$STORAGE_SIZE" -eq 0 ]; then
    echo "UNKNOWN - Storage size is 0"
    exit $UNKNOWN
fi

# Calculate used percentage
USED_PCT=$(echo "scale=1; $STORAGE_USED * 100 / $STORAGE_SIZE" | bc)

# Convert KB to human-readable
format_kb() {
    local kb=$1
    if [ "$kb" -ge 1048576 ]; then
        echo "$(echo "scale=1; $kb / 1048576" | bc)TB"
    elif [ "$kb" -ge 1024 ]; then
        echo "$(echo "scale=1; $kb / 1024" | bc)GB"
    else
        echo "${kb}MB"
    fi
}

TOTAL_STR=$(format_kb $STORAGE_SIZE)
USED_STR=$(format_kb $STORAGE_USED)
FREE_KB=$((STORAGE_SIZE - STORAGE_USED))
FREE_STR=$(format_kb $FREE_KB)

# Warning/critical thresholds are for USED percentage
# warn=80 means WARNING when used >= 80% (free <= 20%)
# crit=90 means CRITICAL when used >= 90% (free <= 10%)
PERFDATA="used=${STORAGE_USED}KB;$((STORAGE_SIZE * WARN / 100));$((STORAGE_SIZE * CRIT / 100));0;${STORAGE_SIZE}"

if (( $(echo "$USED_PCT >= $CRIT" | bc -l) )); then
    echo "CRITICAL - Storage: ${USED_STR} / ${TOTAL_STR} (${USED_PCT}% used, ${FREE_STR} free) | ${PERFDATA}"
    exit $CRITICAL
elif (( $(echo "$USED_PCT >= $WARN" | bc -l) )); then
    echo "WARNING - Storage: ${USED_STR} / ${TOTAL_STR} (${USED_PCT}% used, ${FREE_STR} free) | ${PERFDATA}"
    exit $WARNING
else
    echo "OK - Storage: ${USED_STR} / ${TOTAL_STR} (${USED_PCT}% used, ${FREE_STR} free) | ${PERFDATA}"
    exit $OK
fi
