#!/bin/bash
# check_snmp_temp_cisco.sh
# Перевіряє температуру Cisco комутатора через SNMP
# Використовує ciscoEnvMonTemperatureStatusTable (1.3.6.1.4.1.9.9.13.1.3.1)
# Виклик: check_snmp_temp_cisco.sh <host> <community> <warn> <crit>

HOST=$1
COMMUNITY=$2
WARN=$3
CRIT=$4
TIMEOUT=${5:-30}

OID_TEMP_DESCR="1.3.6.1.4.1.9.9.13.1.3.1.2"
OID_TEMP_VALUE="1.3.6.1.4.1.9.9.13.1.3.1.3"
OID_TEMP_ALARM="1.3.6.1.4.1.9.9.13.1.3.1.4"

VALUE_LINES=$(snmpwalk -v2c -c "$COMMUNITY" -On -t "$TIMEOUT" "$HOST" "$OID_TEMP_VALUE" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$VALUE_LINES" ]; then
    echo "CRITICAL - SNMP query failed for temperature table"
    exit 2
fi

DESCR_LINES=$(snmpwalk -v2c -c "$COMMUNITY" -On -t "$TIMEOUT" "$HOST" "$OID_TEMP_DESCR" 2>/dev/null)
ALARM_LINES=$(snmpwalk -v2c -c "$COMMUNITY" -On -t "$TIMEOUT" "$HOST" "$OID_TEMP_ALARM" 2>/dev/null)

declare -A VALUES DESCRS ALARMS

while IFS= read -r line; do
    index=$(echo "$line" | sed -n 's/.*\.\([0-9]\+\) =.*/\1/p')
    val=$(echo "$line" | sed 's/.*= //' | sed 's/"//g' | tr -d ' ')
    [ -n "$index" ] && VALUES[$index]=$val
done <<< "$VALUE_LINES"

while IFS= read -r line; do
    index=$(echo "$line" | sed -n 's/.*\.\([0-9]\+\) =.*/\1/p')
    descr=$(echo "$line" | sed 's/.*= //' | sed 's/"//g')
    [ -n "$index" ] && DESCRS[$index]=$descr
done <<< "$DESCR_LINES"

while IFS= read -r line; do
    index=$(echo "$line" | sed -n 's/.*\.\([0-9]\+\) =.*/\1/p')
    alarm=$(echo "$line" | sed 's/.*= //' | tr -d ' ')
    [ -n "$index" ] && ALARMS[$index]=$alarm
done <<< "$ALARM_LINES"

OVERALL_STATUS=0
OVERALL_OUTPUT=""

for idx in $(echo "${!VALUES[@]}" | tr ' ' '\n' | sort -n); do
    TEMP_RAW="${VALUES[$idx]}"
    DESCR="${DESCRS[$idx]:-Sensor $idx}"
    ALARM="${ALARMS[$idx]:-1}"

    TEMP_RAW=$(echo "$TEMP_RAW" | sed 's/"//g' | tr -d ' ')

    if [ "$TEMP_RAW" -gt 1000 ] 2>/dev/null; then
        TEMP_C=$(echo "scale=1; $TEMP_RAW / 1000" | bc 2>/dev/null || python3 -c "print(round($TEMP_RAW / 1000.0, 1))" 2>/dev/null)
    else
        TEMP_C="$TEMP_RAW"
    fi

    if [ -z "$TEMP_C" ]; then
        continue
    fi

    STATUS=0
    if [ -n "$ALARM" ] && [ "$ALARM" -ge 3 ] 2>/dev/null; then
        STATUS=2
    elif [ -n "$ALARM" ] && [ "$ALARM" -ge 2 ] 2>/dev/null; then
        STATUS=1
    elif [ -n "$CRIT" ] && [ "$CRIT" != "none" ] && [ "$(echo "$TEMP_C >= $CRIT" | bc -l 2>/dev/null)" = "1" ]; then
        STATUS=2
    elif [ -n "$WARN" ] && [ "$WARN" != "none" ] && [ "$(echo "$TEMP_C >= $WARN" | bc -l 2>/dev/null)" = "1" ]; then
        STATUS=1
    fi

    STATUS_NAME="OK"
    if [ "$STATUS" -eq 2 ]; then STATUS_NAME="CRITICAL"
    elif [ "$STATUS" -eq 1 ]; then STATUS_NAME="WARNING"
    fi

    [ -n "$OVERALL_OUTPUT" ] && OVERALL_OUTPUT="$OVERALL_OUTPUT, "
    OVERALL_OUTPUT="${OVERALL_OUTPUT}${DESCR} ${TEMP_C}°C (${STATUS_NAME})"

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
