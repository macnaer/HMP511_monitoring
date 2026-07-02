#!/bin/bash

OK=0
WARNING=1
CRITICAL=2
UNKNOWN=3

COMMUNITY=$1   # SNMP community string
HOST=$2        # IP пристрою
OID_1=$3       # OID для hrStorageSize
OID_2=$4       # OID для hrStorageUsed
EDGE_1=$5      # Порог WARNING
EDGE_2=$6      # Порог CRITICAL

if [ -z "$EDGE_2" ]; then
    echo "UNKNOWN - Missing arguments. Usage: $0 <community> <host> <OID_size> <OID_used> <warning> <critical>"
    exit $UNKNOWN
fi

# Отримуємо значення через snmpget (зберігаємо stderr, щоб бачити помилки таймауту)
STORAGE_SIZE_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t 10 "$HOST" "$OID_1" 2>&1)
STATUS_SIZE=$?

STORAGE_USED_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t 10 "$HOST" "$OID_2" 2>&1)
STATUS_USED=$?

# Перевіряємо, чи самі SNMP-запити пройшли успішно
if [ $STATUS_SIZE -ne 0 ]; then
    echo "CRITICAL - SNMP Size query failed: $STORAGE_SIZE_RAW"
    exit $CRITICAL
fi

if [ $STATUS_USED -ne 0 ]; then
    echo "CRITICAL - SNMP Used query failed: $STORAGE_USED_RAW"
    exit $CRITICAL
fi

# Очищаємо пробіли або випадкові лапки
STORAGE_SIZE=$(echo "$STORAGE_SIZE_RAW" | tr -d '" ')
STORAGE_USED=$(echo "$STORAGE_USED_RAW" | tr -d '" ')

# Перевіряємо, чи є отримані дані чистими числами
if ! [[ "$STORAGE_SIZE" =~ ^[0-9]+$ && "$STORAGE_USED" =~ ^[0-9]+$ ]]; then
    echo "UNKNOWN - Raw data is not numeric. Size: '$STORAGE_SIZE', Used: '$STORAGE_USED'"
    exit $UNKNOWN
fi

if [ "$STORAGE_SIZE" -eq 0 ]; then
    echo "UNKNOWN - Storage size is 0"
    exit $UNKNOWN
fi

# Розрахунок відсотків
STORAGE_USED_PERCENT=$(echo "scale=2; $STORAGE_USED * 100 / $STORAGE_SIZE" | bc)
STORAGE_USED_DISPLAY=$(echo "$STORAGE_USED_PERCENT" | sed 's/\./,/')

# Логіка порогів
if (( $(echo "$STORAGE_USED_PERCENT > $EDGE_2" | bc -l) )); then
    echo "CRITICAL - Storage usage is ${STORAGE_USED_DISPLAY}%"
    exit $CRITICAL
elif (( $(echo "$STORAGE_USED_PERCENT > $EDGE_1" | bc -l) )); then
    echo "WARNING - Storage usage is ${STORAGE_USED_DISPLAY}%"
    exit $WARNING
else
    echo "OK - Storage usage is ${${STORAGE_USED_DISPLAY}}%"
    exit $OK
fi