#!/bin/bash
# check_snmp_temp_cisco.sh
# Multi-strategy Cisco temperature check via SNMP
# Виклик: check_snmp_temp_cisco.sh <host> <community> <warn> <crit>

HOST=$1
COMMUNITY=$2
WARN=$3
CRIT=$4
TIMEOUT=${5:-30}

STRATEGIES_USED=""
TEMP_RESULTS=()

snmp_get() {
    snmpget -v2c -c "$COMMUNITY" -Oqv -t "$TIMEOUT" "$HOST" "$1" 2>/dev/null
}

snmp_walk() {
    snmpwalk -v2c -c "$COMMUNITY" -On -t "$TIMEOUT" "$HOST" "$1" 2>/dev/null
}

is_numeric() {
    [[ "$1" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]
}

# ----------------------------------------------------------------
# Strategy 1: IETF ENTITY-SENSOR-MIB
# ----------------------------------------------------------------
strategy_entity_sensor() {
    STRATEGIES_USED="${STRATEGIES_USED}entity-sensor-mib "
    RAW=$(snmp_walk "1.3.6.1.2.1.99.1.1.1")
    [ -z "$RAW" ] && return 1

    declare -A SENSORS
    while IFS= read -r line; do
        oid=$(echo "$line" | sed 's/ =.*//')
        val=$(echo "$line" | sed 's/.*= //' | sed 's/"//g' | tr -d ' ')
        echo "$val" | grep -qiE "NoSuchInstance|NoSuchObject|NoSuchName" && continue
        col=$(echo "$oid" | sed -n 's/.*\.1\.1\.1\.\([0-9]\+\).*/\1/p')
        idx=$(echo "$oid" | sed -n 's/.*\.\([0-9]\+\)$/\1/p')
        [ -n "$col" ] && [ -n "$idx" ] && SENSORS["${idx}_${col}"]=$val
    done <<< "$RAW"

    FOUND=0
    for idx in $(echo "${!SENSORS[@]}" | tr ' ' '\n' | sed 's/_.*//' | sort -nu); do
        sclass="${SENSORS[${idx}_1]}"
        stype="${SENSORS[${idx}_2]}"
        [ "$sclass" != "9" ] && [ "$stype" != "8" ] && continue

        svalue="${SENSORS[${idx}_4]}"
        sprecision="${SENSORS[${idx}_3]:-0}"
        sscale="${SENSORS[${idx}_5]:-9}"
        soper="${SENSORS[${idx}_8]:-1}"

        [ "$svalue" = "-1000000000" ] || [ "$soper" != "1" ] && continue

        divisor=1
        for ((i=0; i<sprecision; i++)); do divisor=$((divisor * 10)); done
        case "$sscale" in
            10) sf=1000 ;;
            11) sf=1000000 ;;
            *)  sf=1 ;;
        esac

        tc=$(echo "scale=1; $svalue / $divisor / $sf" | bc -l 2>/dev/null || python3 -c "print(round($svalue / $divisor / $sf, 1))" 2>/dev/null)
        is_numeric "$tc" || continue
        TEMP_RESULTS+=("${tc}|Sensor ${idx}")
        FOUND=1
    done
    [ "$FOUND" -eq 1 ]
}

# ----------------------------------------------------------------
# Strategy 2: CISCO-PROCESS-MIB CPU Temperature (cpmCPUTemperature)
# ----------------------------------------------------------------
strategy_cpu_temp() {
    STRATEGIES_USED="${STRATEGIES_USED}cisco-process-mib "
    RAW=$(snmp_walk "1.3.6.1.4.1.9.9.109.1.1.1.1.7")
    [ -z "$RAW" ] && return 1

    FOUND=0
    while IFS= read -r line; do
        idx=$(echo "$line" | sed -n 's/.*\.\([0-9]\+\)$/\1/p')
        val=$(echo "$line" | sed 's/.*= //' | tr -d ' ')
        is_numeric "$val" || continue
        tc=$(echo "scale=1; $val / 1000" | bc -l 2>/dev/null || python3 -c "print(round($val / 1000.0, 1))" 2>/dev/null)
        is_numeric "$tc" || continue
        TEMP_RESULTS+=("${tc}|CPU Temp (core ${idx})")
        FOUND=1
    done <<< "$RAW"
    [ "$FOUND" -eq 1 ]
}

# ----------------------------------------------------------------
# Strategy 3: CISCO-ENVMON-MIB temperature table
# ----------------------------------------------------------------
strategy_envmon() {
    STRATEGIES_USED="${STRATEGIES_USED}cisco-envmon-mib "
    VALUES=$(snmp_walk "1.3.6.1.4.1.9.9.13.1.3.1.3")
    DESCRS=$(snmp_walk "1.3.6.1.4.1.9.9.13.1.3.1.2")
    [ -z "$VALUES" ] && return 1

    declare -A VMAP DMAP
    while IFS= read -r line; do
        idx=$(echo "$line" | sed -n 's/.*\.\([0-9]\+\) =.*/\1/p')
        val=$(echo "$line" | sed 's/.*= //' | sed 's/"//g' | tr -d ' ')
        echo "$val" | grep -qiE "NoSuchInstance|NoSuchObject|NoSuchName" && continue
        is_numeric "$val" && VMAP[$idx]=$val
    done <<< "$VALUES"

    while IFS= read -r line; do
        idx=$(echo "$line" | sed -n 's/.*\.\([0-9]\+\) =.*/\1/p')
        desc=$(echo "$line" | sed 's/.*= //' | sed 's/"//g')
        [ -n "$idx" ] && DMAP[$idx]=$desc
    done <<< "$DESCRS"

    FOUND=0
    for idx in $(echo "${!VMAP[@]}" | tr ' ' '\n' | sort -n); do
        [ -z "${DMAP[$idx]}" ] && continue
        raw="${VMAP[$idx]}"
        tc="$raw"
        if [ "$raw" -gt 1000 ] 2>/dev/null; then
            tc=$(echo "scale=1; $raw / 1000" | bc -l 2>/dev/null || python3 -c "print(round($raw / 1000.0, 1))" 2>/dev/null)
        fi
        is_numeric "$tc" || continue
        TEMP_RESULTS+=("${tc}|${DMAP[$idx]}")
        FOUND=1
    done
    [ "$FOUND" -eq 1 ]
}

# ----------------------------------------------------------------
# Strategy 4: CISCO-ENTITY-SENSOR-MIB (entSensorValue)
# Cisco private sensor MIB: 1.3.6.1.4.1.9.9.91
# ----------------------------------------------------------------
strategy_cisco_entity_sensor() {
    STRATEGIES_USED="${STRATEGIES_USED}cisco-entity-sensor-mib "
    RAW=$(snmp_walk "1.3.6.1.4.1.9.9.91.1.1.1.1")
    [ -z "$RAW" ] && return 1

    declare -A DATA
    while IFS= read -r line; do
        oid=$(echo "$line" | sed 's/ =.*//')
        val=$(echo "$line" | sed 's/.*= //' | sed 's/"//g' | tr -d ' ')
        echo "$val" | grep -qiE "NoSuchInstance|NoSuchObject|NoSuchName" && continue
        col=$(echo "$oid" | sed -n 's/.*\.1\.1\.1\.\([0-9]\+\).*/\1/p')
        idx=$(echo "$oid" | sed -n 's/.*\.\([0-9]\+\)$/\1/p')
        [ -n "$col" ] && [ -n "$idx" ] && DATA["${idx}_${col}"]=$val
    done <<< "$RAW"

    FOUND=0
    for idx in $(echo "${!DATA[@]}" | tr ' ' '\n' | sed 's/_.*//' | sort -nu); do
        stype="${DATA[${idx}_2]}"
        [ "$stype" != "8" ] && continue
        svalue="${DATA[${idx}_4]}"
        sprecision="${DATA[${idx}_3]:-0}"
        sscale="${DATA[${idx}_5]:-9}"
        soper="${DATA[${idx}_8]:-1}"
        [ "$svalue" = "-1000000000" ] || [ "$soper" != "1" ] && continue

        divisor=1
        for ((i=0; i<sprecision; i++)); do divisor=$((divisor * 10)); done
        case "$sscale" in
            10) sf=1000 ;;
            11) sf=1000000 ;;
            *)  sf=1 ;;
        esac

        tc=$(echo "scale=1; $svalue / $divisor / $sf" | bc -l 2>/dev/null || python3 -c "print(round($svalue / $divisor / $sf, 1))" 2>/dev/null)
        is_numeric "$tc" || continue
        TEMP_RESULTS+=("${tc}|Sensor ${idx}")
        FOUND=1
    done
    [ "$FOUND" -eq 1 ]
}

# ----------------------------------------------------------------
# Strategy 5: CISCO-ENVMON-MIB brute-force common indices
# (some switches report temp at specific scalar indices)
# ----------------------------------------------------------------
strategy_envmon_bruteforce() {
    STRATEGIES_USED="${STRATEGIES_USED}envmon-bruteforce "
    FOUND=0
    for idx in 1 2 3 4 5 6 7 8 9 10 1000 1004 1005 1006 1007 1008 1009 1010 1011 1012 1013 1014 1015 1020 2000 2004 2005 3000 3004 3005 4000 4004 5000; do
        desc=$(snmp_get "1.3.6.1.4.1.9.9.13.1.3.1.2.$idx" 2>/dev/null | sed 's/"//g')
        val=$(snmp_get "1.3.6.1.4.1.9.9.13.1.3.1.3.$idx" 2>/dev/null | tr -d ' ')
        [ -z "$val" ] && continue
        echo "$val" | grep -qiE "NoSuchInstance|NoSuchObject|NoSuchName" && continue
        is_numeric "$val" || continue
        [ -z "$desc" ] && desc="Sensor ${idx}"
        tc="$val"
        if [ "$val" -gt 1000 ] 2>/dev/null; then
            tc=$(echo "scale=1; $val / 1000" | bc -l 2>/dev/null || python3 -c "print(round($val / 1000.0, 1))" 2>/dev/null)
        fi
        is_numeric "$tc" || continue
        TEMP_RESULTS+=("${tc}|${desc}")
        FOUND=1
    done
    [ "$FOUND" -eq 1 ]
}

# ----------------------------------------------------------------
# Strategy 6: OLD-CISCO-ENVMON-MIB scalar status code
# Returns 1=Normal, 2=Warning, 3=Critical (NOT actual temperature)
# ----------------------------------------------------------------
strategy_old_envmon() {
    STRATEGIES_USED="${STRATEGIES_USED}old-cisco-envmon-mib "
    RAW=$(snmp_get "1.3.6.1.4.1.9.5.1.2.11.0")
    [ -z "$RAW" ] && return 1
    RAW=$(echo "$RAW" | sed 's/"//g' | tr -d ' ')
    is_numeric "$RAW" || return 1

    case $RAW in
        1) TEMP_RESULTS+=("ok:0|System Temp") ;;
        2) TEMP_RESULTS+=("warn:0|System Temp") ;;
        3) TEMP_RESULTS+=("crit:0|System Temp") ;;
        *) TEMP_RESULTS+=("ok:0|System Temp") ;;
    esac
}

# ================================================================
# MAIN: try strategies in order
# ================================================================
strategy_entity_sensor || strategy_cpu_temp || strategy_envmon || strategy_cisco_entity_sensor || strategy_envmon_bruteforce || strategy_old_envmon

if [ ${#TEMP_RESULTS[@]} -eq 0 ]; then
    echo "CRITICAL - No temperature sensors found (tried: ${STRATEGIES_USED:-none})"
    exit 2
fi

OVERALL_STATUS=0
OVERALL_OUTPUT=""

for entry in "${TEMP_RESULTS[@]}"; do
    tc="${entry%%|*}"
    label="${entry##*|}"

    case "$tc" in
        ok:*)
            STATUS=0
            result="OK"
            ;;
        warn:*)
            STATUS=1
            result="WARNING"
            ;;
        crit:*)
            STATUS=2
            result="CRITICAL"
            ;;
        *)
            STATUS=0
            if [ -n "$CRIT" ] && [ "$CRIT" != "none" ] && [ "$(echo "$tc >= $CRIT" | bc -l 2>/dev/null)" = "1" ]; then
                STATUS=2
            elif [ -n "$WARN" ] && [ "$WARN" != "none" ] && [ "$(echo "$tc >= $WARN" | bc -l 2>/dev/null)" = "1" ]; then
                STATUS=1
            fi
            sname="OK"
            [ "$STATUS" -eq 2 ] && sname="CRITICAL"
            [ "$STATUS" -eq 1 ] && sname="WARNING"
            result="${tc}°C (${sname})"
            ;;
    esac

    [ -n "$OVERALL_OUTPUT" ] && OVERALL_OUTPUT="$OVERALL_OUTPUT, "
    OVERALL_OUTPUT="${OVERALL_OUTPUT}${label} ${result}"

    [ "$STATUS" -gt "$OVERALL_STATUS" ] && OVERALL_STATUS=$STATUS
done

echo "${OVERALL_OUTPUT}"
exit $OVERALL_STATUS
