#!/bin/bash
# check_snmp_temp_cisco.sh
# Перевіряє температуру Cisco комутатора через SNMP
# Виклик: check_snmp_temp_cisco.sh <host> <community> <warn> <crit>

HOST=$1
COMMUNITY=$2
WARN=$3
CRIT=$4
TIMEOUT=${5:-30}

OID_TEMP_VALUE="1.3.6.1.4.1.9.5.1.2.11.0"
OID_TEMP_ALARM="1.3.6.1.4.1.9.5.1.2.13.0"

TEMP_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t "$TIMEOUT" "$HOST" "$OID_TEMP_VALUE" 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "CRITICAL - SNMP query failed for temperature value"
    exit 2
fi

TEMP_RAW=$(echo "$TEMP_RAW" | sed 's/"//g' | tr -d ' ')

# На Catalyst 2960G OID повертає °C напряму (напр. 42).
# Якщо значення > 1000 — це міліградуси, ділимо на 1000.
if [ "$TEMP_RAW" -gt 1000 ] 2>/dev/null; then
    TEMP_C=$(echo "scale=1; $TEMP_RAW / 1000" | bc 2>/dev/null || python3 -c "print(round($TEMP_RAW / 1000.0, 1))" 2>/dev/null)
else
    TEMP_C="$TEMP_RAW"
fi
if [ -z "$TEMP_C" ]; then
    echo "UNKNOWN - Cannot parse temperature value: $TEMP_RAW"
    exit 3
fi

ALARM_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t "$TIMEOUT" "$HOST" "$OID_TEMP_ALARM" 2>/dev/null)
if [ $? -eq 0 ]; then
    ALARM_VAL=$(echo "$ALARM_RAW" | sed 's/"//g' | tr -d ' ')
    if [ "$ALARM_VAL" -ge 3 ] 2>/dev/null; then
        echo "CRITICAL - Temperature alarm active (status: $ALARM_VAL), $TEMP_C°C"
        exit 2
    elif [ "$ALARM_VAL" -ge 2 ] 2>/dev/null; then
        echo "WARNING - Temperature warning (status: $ALARM_VAL), $TEMP_C°C"
        exit 1
    fi
fi

if [ -n "$CRIT" ] && [ "$CRIT" != "none" ]; then
    if [ "$(echo "$TEMP_C >= $CRIT" | bc -l 2>/dev/null)" = "1" ]; then
        echo "CRITICAL - Temperature $TEMP_C°C (>= ${CRIT}°C)"
        exit 2
    fi
fi

if [ -n "$WARN" ] && [ "$WARN" != "none" ]; then
    if [ "$(echo "$TEMP_C >= $WARN" | bc -l 2>/dev/null)" = "1" ]; then
        echo "WARNING - Temperature $TEMP_C°C (>= ${WARN}°C)"
        exit 1
    fi
fi

echo "OK - Temperature $TEMP_C°C"
exit 0
