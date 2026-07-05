#!/bin/bash
# check_snmp_storage_cisco.sh
# Cisco flash storage usage check via SNMP
#
# Strategy 1: OLD-CISCO-FLASH-MIB scalar OIDs (most Cisco IOS devices)
# Strategy 2: CISCO-FILE-SYSTEM-MIB (IOS 12.0+ file systems)
# Strategy 3: CISCO-FLASH-MIB partition table (dynamic index discovery)
# Strategy 4: hrStorageTable auto-discovery (non-Cisco or newer IOS)
# Strategy 5: hrStorage brute-force indexes 1-15
# Strategy 6: snmptable hrStorage dump (formatted table fallback)
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

DEBUG=${DEBUG:-0}

debug_log() {
    if [ "$DEBUG" = "1" ]; then
        echo "DEBUG: $*" >&2
    fi
}

debug_raw() {
    if [ "$DEBUG" = "1" ]; then
        echo "DEBUG[RAW]: $*" >&2
    fi
}

snmp_get_val() {
    local oid=$1
    local timeout=${2:-15}
    local raw
    raw=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t "$timeout" "$HOST" "$oid" 2>/dev/null)
    local rc=$?
    debug_raw "${oid} => exit=${rc} value=[${raw}]"
    if [ $rc -eq 0 ] && [ -n "$raw" ] && ! echo "$raw" | grep -qi "no such"; then
        echo "$raw" | tr -d '" ' | head -n1
        return 0
    fi
    return 1
}

snmp_walk_oids() {
    local oid=$1
    local timeout=${2:-15}
    local raw
    raw=$(snmpwalk -v2c -c "$COMMUNITY" -Oqn -t "$timeout" "$HOST" "$oid" 2>/dev/null)
    debug_raw "WALK ${oid} => [${raw}]"
    if [ -n "$raw" ]; then
        echo "$raw"
        return 0
    fi
    return 1
}

get_oid_index() {
    echo "$1" | awk '{print $1}' | awk -F. '{print $NF}'
}

get_oid_value() {
    echo "$1" | awk '{print $2}'
}

clean_val() {
    echo "$1" | tr -d '" ' | head -n1
}

is_numeric() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

STORAGE_SIZE=""
STORAGE_USED=""
DESCR="flash"

# ============================================================
# STRATEGY 1: OLD-CISCO-FLASH-MIB (scalar OIDs)
#   1.3.6.1.4.1.9.2.10.0 = total flash size (bytes)
#   1.3.6.1.4.1.9.2.11.0 = available flash (bytes)
# ============================================================
if [ -z "$STORAGE_SIZE" ] && { [ "$INDEX" = "auto" ] || [ -z "$INDEX" ]; }; then
    debug_log "Strategy 1: OLD-CISCO-FLASH-MIB scalars..."
    TOTAL_RAW=$(snmp_get_val "1.3.6.1.4.1.9.2.10.0" 10)
    if [ -n "$TOTAL_RAW" ] && is_numeric "$TOTAL_RAW" && [ "$TOTAL_RAW" -gt 0 ]; then
        AVAIL_RAW=$(snmp_get_val "1.3.6.1.4.1.9.2.11.0" 10)
        if [ -n "$AVAIL_RAW" ] && is_numeric "$AVAIL_RAW" ]; then
            STORAGE_SIZE=$((TOTAL_RAW / 1024))
            STORAGE_USED=$(( (TOTAL_RAW - AVAIL_RAW) / 1024 ))
            debug_log "Strategy 1 OK: total=${TOTAL_RAW}B avail=${AVAIL_RAW}B"
        fi
    fi
fi

# ============================================================
# STRATEGY 2: CISCO-FILE-SYSTEM-MIB
#   1.3.6.1.4.1.9.9.288.1.1.3.1.2.X = cfsFileSpaceTotal (in units)
#   1.3.6.1.4.1.9.9.288.1.1.3.1.3.X = cfsFileSpaceFree (in units)
#   1.3.6.1.4.1.9.9.288.1.1.3.1.8.X = cfsFileSpaceUnit (bytes/unit)
# ============================================================
if [ -z "$STORAGE_SIZE" ]; then
    debug_log "Strategy 2: CISCO-FILE-SYSTEM-MIB..."
    CISCO_FS_TOTAL_OID="1.3.6.1.4.1.9.9.288.1.1.3.1.2"
    CISCO_FS_FREE_OID="1.3.6.1.4.1.9.9.288.1.1.3.1.3"
    CISCO_FS_UNIT_OID="1.3.6.1.4.1.9.9.288.1.1.3.1.8"

    FS_WALK=$(snmp_walk_oids "$CISCO_FS_TOTAL_OID" 15)
    if [ -n "$FS_WALK" ]; then
        while IFS= read -r fs_line; do
            [ -z "$fs_line" ] && continue
            FS_IDX=$(get_oid_index "$fs_line")
            FS_TOTAL=$(get_oid_value "$fs_line")
            debug_log "  FS index ${FS_IDX}: total=${FS_TOTAL}"
            if is_numeric "$FS_TOTAL" && [ "$FS_TOTAL" -gt 0 ]; then
                FS_FREE=$(snmp_get_val "${CISCO_FS_FREE_OID}.${FS_IDX}" 10)
                FS_UNIT=$(snmp_get_val "${CISCO_FS_UNIT_OID}.${FS_IDX}" 10)
                debug_log "  FS index ${FS_IDX}: free=${FS_FREE} unit=${FS_UNIT}"
                if is_numeric "$FS_FREE" && is_numeric "$FS_UNIT" && [ "$FS_UNIT" -gt 0 ]; then
                    TOTAL_BYTES=$((FS_TOTAL * FS_UNIT))
                    FREE_BYTES=$((FS_FREE * FS_UNIT))
                    if [ "$TOTAL_BYTES" -gt 0 ]; then
                        STORAGE_SIZE=$((TOTAL_BYTES / 1024))
                        STORAGE_USED=$(( (TOTAL_BYTES - FREE_BYTES) / 1024 ))
                        DESCR="flash"
                        debug_log "Strategy 2 OK via FS index ${FS_IDX}: total=${TOTAL_BYTES}B free=${FREE_BYTES}B"
                        break
                    fi
                fi
            fi
        done <<< "$FS_WALK"
    fi

    # Brute-force fallback for CISCO-FILE-SYSTEM-MIB indexes 1-5
    if [ -z "$STORAGE_SIZE" ]; then
        debug_log "Strategy 2 fallback: brute-force FS indexes 1-5..."
        for TRY_FS in 1 2 3 4 5; do
            FS_TOTAL=$(snmp_get_val "${CISCO_FS_TOTAL_OID}.${TRY_FS}" 10)
            if is_numeric "$FS_TOTAL" && [ "$FS_TOTAL" -gt 0 ]; then
                FS_FREE=$(snmp_get_val "${CISCO_FS_FREE_OID}.${TRY_FS}" 10)
                FS_UNIT=$(snmp_get_val "${CISCO_FS_UNIT_OID}.${TRY_FS}" 10)
                if is_numeric "$FS_FREE" && is_numeric "$FS_UNIT" && [ "$FS_UNIT" -gt 0 ]; then
                    TOTAL_BYTES=$((FS_TOTAL * FS_UNIT))
                    FREE_BYTES=$((FS_FREE * FS_UNIT))
                    if [ "$TOTAL_BYTES" -gt 0 ]; then
                        STORAGE_SIZE=$((TOTAL_BYTES / 1024))
                        STORAGE_USED=$(( (TOTAL_BYTES - FREE_BYTES) / 1024 ))
                        DESCR="flash"
                        debug_log "Strategy 2 fallback OK via FS index ${TRY_FS}"
                        break
                    fi
                fi
            fi
        done
    fi
fi

# ============================================================
# STRATEGY 3: CISCO-FLASH-MIB (partition table, dynamic discovery)
#   1.3.6.1.4.1.9.9.10.1.1.4.1.1.4.X = partition size (bytes)
#   1.3.6.1.4.1.9.9.10.1.1.4.1.1.5.X = free space (bytes)
# ============================================================
if [ -z "$STORAGE_SIZE" ]; then
    debug_log "Strategy 3: CISCO-FLASH-MIB partition table (dynamic)..."
    FLASH_PART_SIZE_OID="1.3.6.1.4.1.9.9.10.1.1.4.1.1.4"
    FLASH_PART_FREE_OID="1.3.6.1.4.1.9.9.10.1.1.4.1.1.5"

    PART_WALK=$(snmp_walk_oids "$FLASH_PART_SIZE_OID" 15)
    if [ -n "$PART_WALK" ]; then
        while IFS= read -r part_line; do
            [ -z "$part_line" ] && continue
            PART_IDX=$(get_oid_index "$part_line")
            PART_SIZE_VAL=$(get_oid_value "$part_line")
            debug_log "  Partition index ${PART_IDX}: size_raw=${PART_SIZE_VAL}"
            if is_numeric "$PART_SIZE_VAL" && [ "$PART_SIZE_VAL" -gt 0 ]; then
                PART_FREE_VAL=$(snmp_get_val "${FLASH_PART_FREE_OID}.${PART_IDX}" 10)
                debug_log "  Partition index ${PART_IDX}: free_raw=${PART_FREE_VAL}"
                if is_numeric "$PART_FREE_VAL"; then
                    STORAGE_SIZE=$((PART_SIZE_VAL / 1024))
                    STORAGE_USED=$(( (PART_SIZE_VAL - PART_FREE_VAL) / 1024 ))
                    DESCR="flash"
                    debug_log "Strategy 3 OK via partition ${PART_IDX}: size=${PART_SIZE_VAL}B free=${PART_FREE_VAL}B"
                    break
                fi
            fi
        done <<< "$PART_WALK"
    fi

    # Brute-force fallback indexes 1-15
    if [ -z "$STORAGE_SIZE" ]; then
        debug_log "Strategy 3 fallback: brute-force partition indexes 1-15..."
        for TRY_PART in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
            PART_SIZE_VAL=$(snmp_get_val "${FLASH_PART_SIZE_OID}.${TRY_PART}" 10)
            if is_numeric "$PART_SIZE_VAL" && [ "$PART_SIZE_VAL" -gt 0 ]; then
                PART_FREE_VAL=$(snmp_get_val "${FLASH_PART_FREE_OID}.${TRY_PART}" 10)
                if is_numeric "$PART_FREE_VAL"; then
                    STORAGE_SIZE=$((PART_SIZE_VAL / 1024))
                    STORAGE_USED=$(( (PART_SIZE_VAL - PART_FREE_VAL) / 1024 ))
                    DESCR="flash"
                    debug_log "Strategy 3 fallback OK via partition ${TRY_PART}"
                    break
                fi
            fi
        done
    fi
fi

# ============================================================
# STRATEGY 4: hrStorageTable (auto-discover any non-memory type)
# ============================================================
if [ -z "$STORAGE_SIZE" ]; then
    debug_log "Strategy 4: hrStorageTable..."
    OID_DESCR="1.3.6.1.2.1.25.2.3.1.3"
    OID_SIZE="1.3.6.1.2.1.25.2.3.1.5"
    OID_USED="1.3.6.1.2.1.25.2.3.1.6"
    OID_TYPE="1.3.6.1.2.1.25.2.3.1.2"

    if [ "$INDEX" = "auto" ] || [ -z "$INDEX" ]; then
        TYPE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -Oqn -t 30 "$HOST" "$OID_TYPE" 2>/dev/null)
        SIZE_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -Oqn -t 30 "$HOST" "$OID_SIZE" 2>/dev/null)

        if [ -n "$TYPE_RAW" ] && [ -n "$SIZE_RAW" ]; then
            while IFS= read -r type_line; do
                OID_IDX=$(get_oid_index "$type_line")
                TYPE_VAL=$(get_oid_value "$type_line")

                SIZE_LINE=$(echo "$SIZE_RAW" | grep "\.${OID_IDX} ")
                if [ -n "$SIZE_LINE" ]; then
                    SIZE_VAL=$(get_oid_value "$SIZE_LINE")
                    if [ -n "$SIZE_VAL" ] && [ "$SIZE_VAL" -gt 0 ] 2>/dev/null && \
                       ! echo "$TYPE_VAL" | grep -qE "\.(2|3)$"; then
                        INDEX=$OID_IDX
                        break
                    fi
                fi
            done <<< "$TYPE_RAW"
        fi
    fi

    if [ "$INDEX" = "auto" ]; then
        INDEX=""
    fi

    if [ -n "$INDEX" ]; then
        DESCR_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t 30 "$HOST" "${OID_DESCR}.${INDEX}" 2>/dev/null)
        DESCR=$(echo "$DESCR_RAW" | tr -d '"' | head -n1)
        [ -z "$DESCR" ] && DESCR="storage"

        SNMP_SIZE_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t 30 "$HOST" "${OID_SIZE}.${INDEX}" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$SNMP_SIZE_RAW" ] && ! echo "$SNMP_SIZE_RAW" | grep -qi "no such"; then
            STORAGE_SIZE=$(echo "$SNMP_SIZE_RAW" | tr -d '" ' | head -n1)
            SNMP_USED_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t 30 "$HOST" "${OID_USED}.${INDEX}" 2>/dev/null)
            if [ $? -eq 0 ] && [ -n "$SNMP_USED_RAW" ] && ! echo "$SNMP_USED_RAW" | grep -qi "no such"; then
                STORAGE_USED=$(echo "$SNMP_USED_RAW" | tr -d '" ' | head -n1)
            fi
        fi
    fi

    # ============================================================
    # STRATEGY 5: brute-force common hrStorage indexes
    # ============================================================
    if [ -z "$STORAGE_SIZE" ]; then
        debug_log "Strategy 5: hrStorage brute-force indexes 1-15..."
        for TRY_IDX in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
            SNMP_SIZE_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t 10 "$HOST" "${OID_SIZE}.${TRY_IDX}" 2>/dev/null)
            if [ $? -eq 0 ] && [ -n "$SNMP_SIZE_RAW" ] && ! echo "$SNMP_SIZE_RAW" | grep -qi "no such"; then
                SIZE_VAL=$(echo "$SNMP_SIZE_RAW" | tr -d '" ' | head -n1)
                if is_numeric "$SIZE_VAL" && [ "$SIZE_VAL" -gt 0 ]; then
                    INDEX=$TRY_IDX
                    DESCR_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t 10 "$HOST" "${OID_DESCR}.${INDEX}" 2>/dev/null)
                    DESCR=$(echo "$DESCR_RAW" | tr -d '"' | head -n1)
                    [ -z "$DESCR" ] && DESCR="storage"
                    STORAGE_SIZE=$SIZE_VAL
                    SNMP_USED_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t 10 "$HOST" "${OID_USED}.${INDEX}" 2>/dev/null)
                    if [ $? -eq 0 ] && [ -n "$SNMP_USED_RAW" ] && ! echo "$SNMP_USED_RAW" | grep -qi "no such"; then
                        STORAGE_USED=$(echo "$SNMP_USED_RAW" | tr -d '" ' | head -n1)
                    fi
                    debug_log "Strategy 5 hrStorage index ${INDEX}: size=${STORAGE_SIZE}, used=${STORAGE_USED}, descr=${DESCR}"
                    break
                fi
            fi
        done
    fi
fi

# ============================================================
# STRATEGY 6: snmptable hrStorage (formatted table dump)
# ============================================================
if [ -z "$STORAGE_SIZE" ]; then
    debug_log "Strategy 6: snmptable hrStorage..."
    if command -v snmptable &>/dev/null; then
        TABLE_OUT=$(snmptable -v2c -c "$COMMUNITY" -CH -Cb -t 15 "$HOST" hrStorageTable 2>/dev/null)
        debug_raw "snmptable hrStorage => [${TABLE_OUT}]"
        if [ -n "$TABLE_OUT" ]; then
            while IFS= read -r tbl_line; do
                [ -z "$tbl_line" ] && continue
                TBL_IDX=$(echo "$tbl_line" | awk '{print $1}')
                TBL_TYPE=$(echo "$tbl_line" | awk '{print $2}')
                TBL_DESCR=$(echo "$tbl_line" | awk '{print $3}' | tr -d '"')
                TBL_SIZE=$(echo "$tbl_line" | awk '{print $5}')
                TBL_USED=$(echo "$tbl_line" | awk '{print $6}')
                if is_numeric "$TBL_SIZE" && [ "$TBL_SIZE" -gt 0 ] && \
                   is_numeric "$TBL_USED" && ! echo "$TBL_TYPE" | grep -qE "\.(2|3)$"; then
                    STORAGE_SIZE=$TBL_SIZE
                    STORAGE_USED=$TBL_USED
                    DESCR="$TBL_DESCR"
                    debug_log "Strategy 6 OK via index ${TBL_IDX}: size=${STORAGE_SIZE} used=${STORAGE_USED} descr=${DESCR}"
                    break
                fi
            done <<< "$TABLE_OUT"
        fi
    else
        debug_log "snmptable not available, skipping Strategy 6"
    fi
fi

# ============================================================
# Validate results
# ============================================================
if [ -z "$STORAGE_SIZE" ] || [ -z "$STORAGE_USED" ]; then
    echo "UNKNOWN - No storage found on ${HOST} (tried all 6 strategies)"
    exit $UNKNOWN
fi

if ! is_numeric "$STORAGE_SIZE"; then
    echo "UNKNOWN - Invalid storage size: '${STORAGE_SIZE}'"
    exit $UNKNOWN
fi

if ! is_numeric "$STORAGE_USED"; then
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
