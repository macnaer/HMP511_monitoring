#!/bin/bash
# check_snmp_temp_cisco.sh
# Перевіряє температуру Cisco комутатора через SNMP
# Використовує IETF ENTITY-SENSOR-MIB (1.3.6.1.2.1.99.1.1.1)
# Виклик: check_snmp_temp_cisco.sh <host> <community> <warn> <crit>

HOST=$1
COMMUNITY=$2
WARN=$3
CRIT=$4
TIMEOUT=${5:-30}

OID_ENTITY_SENSOR="1.3.6.1.2.1.99.1.1.1"

RAW_LINES=$(snmpwalk -v2c -c "$COMMUNITY" -On -t "$TIMEOUT" "$HOST" "$OID_ENTITY_SENSOR" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$RAW_LINES" ]; then
    echo "CRITICAL - SNMP query failed for ENTITY-SENSOR-MIB"
    exit 2
fi

SENSOR_CLASS_TEMPERATURE=9
SENSOR_TYPE_CELSIUS=8
SCALE_UNITS=9
SCALE_MILLI=10
SCALE_MICRO=11
INVALID_VALUE=-1000000000

declare -A SENSORS

while IFS= read -r line; do
    oid=$(echo "$line" | sed 's/ =.*//')
    val=$(echo "$line" | sed 's/.*= //' | sed 's/"//g' | tr -d ' ')
    if echo "$val" | grep -qiE "NoSuchInstance|NoSuchObject|NoSuchName"; then
        continue
    fi
    col=$(echo "$oid" | sed -n 's/.*\.1\.1\.1\.\([0-9]\+\).*/\1/p')
    idx=$(echo "$oid" | sed -n 's/.*\.\([0-9]\+\)$/\1/p')
    if [ -n "$col" ] && [ -n "$idx" ]; then
        SENSORS["${idx}_${col}"]=$val
    fi
done <<< "$RAW_LINES"

OVERALL_STATUS=0
OVERALL_OUTPUT=""

for idx in $(echo "${!SENSORS[@]}" | tr ' ' '\n' | sed 's/_.*//' | sort -nu); do
    sclass="${SENSORS[${idx}_1]}"
    stype="${SENSORS[${idx}_2]}"

    if [ "$sclass" != "$SENSOR_CLASS_TEMPERATURE" ] && [ "$stype" != "$SENSOR_TYPE_CELSIUS" ]; then
        continue
    fi

    svalue="${SENSORS[${idx}_4]}"
    sprecision="${SENSORS[${idx}_3]:-0}"
    sscale="${SENSORS[${idx}_5]:-$SCALE_UNITS}"
    soper="${SENSORS[${idx}_8]:-1}"

    if [ "$svalue" = "$INVALID_VALUE" ] || [ "$soper" != "1" ]; then
        continue
    fi

    divisor=1
    for ((i=0; i<sprecision; i++)); do
        divisor=$((divisor * 10))
    done

    scale_factor=1
    if [ "$sscale" = "$SCALE_MILLI" ]; then
        scale_factor=1000
    elif [ "$sscale" = "$SCALE_MICRO" ]; then
        scale_factor=1000000
    fi

    TEMP_C=$(echo "scale=2; $svalue / $divisor / $scale_factor" | bc -l 2>/dev/null || python3 -c "print(round($svalue / $divisor / $scale_factor, 1))" 2>/dev/null)

    STATUS=0
    if [ -n "$CRIT" ] && [ "$CRIT" != "none" ] && [ "$(echo "$TEMP_C >= $CRIT" | bc -l 2>/dev/null)" = "1" ]; then
        STATUS=2
    elif [ -n "$WARN" ] && [ "$WARN" != "none" ] && [ "$(echo "$TEMP_C >= $WARN" | bc -l 2>/dev/null)" = "1" ]; then
        STATUS=1
    fi

    STATUS_NAME="OK"
    if [ "$STATUS" -eq 2 ]; then STATUS_NAME="CRITICAL"
    elif [ "$STATUS" -eq 1 ]; then STATUS_NAME="WARNING"
    fi

    [ -n "$OVERALL_OUTPUT" ] && OVERALL_OUTPUT="$OVERALL_OUTPUT, "
    OVERALL_OUTPUT="${OVERALL_OUTPUT}Sensor ${idx} ${TEMP_C}°C (${STATUS_NAME})"

    if [ "$STATUS" -gt "$OVERALL_STATUS" ]; then
        OVERALL_STATUS=$STATUS
    fi
done

if [ -z "$OVERALL_OUTPUT" ]; then
    echo "CRITICAL - No temperature sensors found"
    exit 2
fi

echo "${OVERALL_OUTPUT}"
exit $OVERALL_STATUS
