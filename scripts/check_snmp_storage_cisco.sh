#!/bin/bash
# check_snmp_storage_cisco.sh
# Cisco flash storage usage check via SNMP
#
# Strategy 1: OLD-CISCO-FLASH-MIB scalar OIDs (most Cisco IOS devices)
# Strategy 2: hrStorageTable auto-discovery (non-Cisco or newer IOS)
#
# Usage: check_snmp_storage_cisco.sh <community> <host> <index> <warn> <crit>
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

STORAGE_SIZE=""
STORAGE_USED=""
DESCR="flash"

# ============================================================
# STRATEGY 1: OLD-CISCO-FLASH-MIB (scalar OIDs)
#   1.3.6.1.4.1.9.2.10.0 = total flash size (bytes)
#   1.3.6.1.4.1.9.2.11.0 = available flash (bytes)
# ============================================================
if [ "$INDEX" = "auto" ] || [ -z "$INDEX" ]; then
    TOTAL_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqv -t 30 "$HOST" 1.3.6.1.4.1.9.2.10.0 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$TOTAL_RAW" ] && ! echo "$TOTAL_RAW" | grep -qi "no such"; then
        TOTAL_BYTES=$(echo "$TOTAL_RAW" | tr -d '" ' | head -n1)
        if [[ "$TOTAL_BYTES" =~ ^[0-9]+$ ]] && [ "$TOTAL_BYTES" -gt 0 ]; then
            AVAIL_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqv -t 30 "$HOST" 1.3.6.1.4.1.9.2.11.0 2>/dev/null)
            if [ $? -eq 0 ] && [ -n "$AVAIL_RAW" ] && ! echo "$AVAIL_RAW" | grep -qi "no such"; then
                AVAIL_BYTES=$(echo "$AVAIL_RAW" | tr -d '" ' | head -n1)
                if [[ "$AVAIL_BYTES" =~ ^[0-9]+$ ]]; then
                    # Values are in bytes, convert to KB for consistency
                    STORAGE_SIZE=$((TOTAL_BYTES / 1024))
                    STORAGE_USED=$(( (TOTAL_BYTES - AVAIL_BYTES) / 1024 ))
                    DESCR="flash"
                fi
            fi
        fi
    fi
fi

# ============================================================
# STRATEGY 2: hrStorageTable (auto-discover any non-memory type)
# ============================================================
if [ -z "$STORAGE_SIZE" ]; then
    OID_DESCR="1.3.6.1.2.1.25.2.3.1.3"
    OID_SIZE="1.3.6.1.2.1.25.2.3.1.5"
    OID_USED="1.3.6.1.2.1.25.2.3.1.6"
    OID_TYPE="1.3.6.1.2.1.25.2.3.1.2"

    if [ "$INDEX" = "auto" ] || [ -z "$INDEX" ]; then
        TYPE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqn -t 30 "$HOST" "$OID_TYPE" 2>/dev/null)
        SIZE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqn -t 30 "$HOST" "$OID_SIZE" 2>/dev/null)

        if [ -n "$TYPE_RAW" ] && [ -n "$SIZE_RAW" ]; then
            while IFS= read -r type_line; do
                OID_IDX=$(echo "$type_line" | awk '{print $1}' | awk -F. '{print $NF}')
                TYPE_VAL=$(echo "$type_line" | awk '{print $2}')

                SIZE_LINE=$(echo "$SIZE_RAW" | grep "\.${OID_IDX} ")
                if [ -n "$SIZE_LINE" ]; then
                    SIZE_VAL=$(echo "$SIZE_LINE" | awk '{print $2}')
                    # Skip memory types (2=ram, 3=virtualMemory)
                    if [ -n "$SIZE_VAL" ] && [ "$SIZE_VAL" -gt 0 ] 2>/dev/null && \
                       ! echo "$TYPE_VAL" | grep -qE "\.(2|3)$"; then
                        INDEX=$OID_IDX
                        break
                    fi
                fi
            done <<< "$TYPE_RAW"
        fi
    fi

    if [ -n "$INDEX" ]; then
        DESCR_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqv -t 30 "$HOST" "${OID_DESCR}.${INDEX}" 2>/dev/null)
        DESCR=$(echo "$DESCR_RAW" | tr -d '"' | head -n1)
        [ -z "$DESCR" ] && DESCR="storage"

        SNMP_SIZE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqv -t 30 "$HOST" "${OID_SIZE}.${INDEX}" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$SNMP_SIZE_RAW" ] && ! echo "$SNMP_SIZE_RAW" | grep -qi "no such"; then
            STORAGE_SIZE=$(echo "$SNMP_SIZE_RAW" | tr -d '" ' | head -n1)
            SNMP_USED_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -m "" -Oqv -t 30 "$HOST" "${OID_USED}.${INDEX}" 2>/dev/null)
            if [ $? -eq 0 ] && [ -n "$SNMP_USED_RAW" ] && ! echo "$SNMP_USED_RAW" | grep -qi "no such"; then
                STORAGE_USED=$(echo "$SNMP_USED_RAW" | tr -d '" ' | head -n1)
            fi
        fi
    fi
fi

# ============================================================
# Validate results
# ============================================================
if [ -z "$STORAGE_SIZE" ] || [ -z "$STORAGE_USED" ]; then
    echo "UNKNOWN - No storage found on ${HOST} (neither Cisco flash MIB nor hrStorage)"
    exit $UNKNOWN
fi

if ! [[ "$STORAGE_SIZE" =~ ^[0-9]+$ ]]; then
    echo "UNKNOWN - Invalid storage size: '${STORAGE_SIZE}'"
    exit $UNKNOWN
fi

if ! [[ "$STORAGE_USED" =~ ^[0-9]+$ ]]; then
    echo "UNKNOWN - Invalid storage used: '${STORAGE_USED}'"
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
