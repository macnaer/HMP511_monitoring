#!/bin/bash
# check_snmp_storage_cisco.sh
# Cisco storage usage check via SNMP with auto-discovery
#
# Usage: check_snmp_storage_cisco.sh <community> <host> <index> <warn> <crit>
# If index is "auto", discovers storage automatically (any non-memory type).
# Example: check_snmp_storage_cisco.sh LibreNms 10.7.99.5 auto 80 90

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
    echo "UNKNOWN - Missing arguments. Usage: $0 <community> <host> <index|auto> <warn> <crit>"
    exit $UNKNOWN
fi

# hrStorage OIDs
OID_DESCR="1.3.6.1.2.1.25.2.3.1.3"
OID_SIZE="1.3.6.1.2.1.25.2.3.1.5"
OID_USED="1.3.6.1.2.1.25.2.3.1.6"
OID_TYPE="1.3.6.1.2.1.25.2.3.1.2"

# Auto-discover storage index if "auto"
if [ "$INDEX" = "auto" ] || [ -z "$INDEX" ]; then
    # Walk hrStorageType and hrStorageSize to find valid entries
    TYPE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqn -t 30 "$HOST" "$OID_TYPE" 2>/dev/null)
    SIZE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqn -t 30 "$HOST" "$OID_SIZE" 2>/dev/null)

    if [ -z "$TYPE_RAW" ] || [ -z "$SIZE_RAW" ]; then
        echo "UNKNOWN - SNMP walk failed for hrStorage on ${HOST}"
        exit $UNKNOWN
    fi

    # Parse types and sizes, find first entry with size > 0
    INDEX=""
    IDX=1
    while IFS= read -r type_line; do
        # Get the OID suffix (index) from the type line
        OID_IDX=$(echo "$type_line" | awk '{print $1}' | awk -F. '{print $NF}')
        TYPE_VAL=$(echo "$type_line" | awk '{print $2}')

        # Get size for this index
        SIZE_LINE=$(echo "$SIZE_RAW" | grep "\.${OID_IDX} ")
        if [ -n "$SIZE_LINE" ]; then
            SIZE_VAL=$(echo "$SIZE_LINE" | awk '{print $2}')
            # Skip memory types (1=other, 2=ram, 3=virtualMemory)
            # Accept anything else with size > 0
            if [ -n "$SIZE_VAL" ] && [ "$SIZE_VAL" -gt 0 ] 2>/dev/null && \
               ! echo "$TYPE_VAL" | grep -qE "\.(2|3)$"; then
                INDEX=$OID_IDX
                break
            fi
        fi
        IDX=$((IDX + 1))
    done <<< "$TYPE_RAW"

    if [ -z "$INDEX" ]; then
        echo "UNKNOWN - No usable storage found on ${HOST}"
        exit $UNKNOWN
    fi
fi

# Query the discovered/specified index
OID_SIZE_IDX="${OID_SIZE}.${INDEX}"
OID_USED_IDX="${OID_USED}.${INDEX}"
OID_DESCR_IDX="${OID_DESCR}.${INDEX}"

# Get storage description (for display)
DESCR_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqv -t 30 "$HOST" "$OID_DESCR_IDX" 2>/dev/null)
DESCR=$(echo "$DESCR_RAW" | tr -d '"' | head -n1)
[ -z "$DESCR" ] && DESCR="storage"

# Get total storage size
SNMP_SIZE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqv -t 30 "$HOST" "$OID_SIZE_IDX" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$SNMP_SIZE_RAW" ] || echo "$SNMP_SIZE_RAW" | grep -qi "no such"; then
    echo "CRITICAL - SNMP query failed for hrStorageSize (index ${INDEX}): ${SNMP_SIZE_RAW}"
    exit $CRITICAL
fi
STORAGE_SIZE=$(echo "$SNMP_SIZE_RAW" | tr -d '" ' | head -n1)

# Get used storage
SNMP_USED_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqv -t 30 "$HOST" "$OID_USED_IDX" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$SNMP_USED_RAW" ] || echo "$SNMP_USED_RAW" | grep -qi "no such"; then
    echo "CRITICAL - SNMP query failed for hrStorageUsed (index ${INDEX}): ${SNMP_USED_RAW}"
    exit $CRITICAL
fi
STORAGE_USED=$(echo "$SNMP_USED_RAW" | tr -d '" ' | head -n1)

# Validate numeric values
if ! [[ "$STORAGE_SIZE" =~ ^[0-9]+$ ]]; then
    echo "UNKNOWN - Invalid storage size: '${STORAGE_SIZE}' (raw: ${SNMP_SIZE_RAW})"
    exit $UNKNOWN
fi

if ! [[ "$STORAGE_USED" =~ ^[0-9]+$ ]]; then
    echo "UNKNOWN - Invalid storage used: '${STORAGE_USED}' (raw: ${SNMP_USED_RAW})"
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

PERFDATA="used=${STORAGE_USED}KB;$((STORAGE_SIZE * WARN / 100));$((STORAGE_SIZE * CRIT / 100));0;${STORAGE_SIZE}"

if (( $(echo "$USED_PCT >= $CRIT" | bc -l) )); then
    echo "CRITICAL - Storage ${DESCR}: ${USED_STR} / ${TOTAL_STR} (${USED_PCT}% used, ${FREE_STR} free) | ${PERFDATA}"
    exit $CRITICAL
elif (( $(echo "$USED_PCT >= $WARN" | bc -l) )); then
    echo "WARNING - Storage ${DESCR}: ${USED_STR} / ${TOTAL_STR} (${USED_PCT}% used, ${FREE_STR} free) | ${PERFDATA}"
    exit $WARNING
else
    echo "OK - Storage ${DESCR}: ${USED_STR} / ${TOTAL_STR} (${USED_PCT}% used, ${FREE_STR} free) | ${PERFDATA}"
    exit $OK
fi
