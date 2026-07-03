#!/bin/bash

# Скрипт для перевірки відсотка ЗАЙНЯТОГО місця на диску через SNMP (Універсальний: MikroTik, Cisco тощо)
# Призначення: моніторинг використання дискового простору на віддаленому хості
#
# Використання:
#   ./check_used_space.sh <community> <host> <OID_size> <OID_used> <warning_%> <critical_%>
#
# Приклад для Cisco (де індекс флешу, наприклад, 3):
#   ./check_used_space.sh public 192.168.1.10 1.3.6.1.2.1.25.2.3.1.5.3 1.3.6.1.2.1.25.2.3.1.6.3 80 90

# --- Коди виходу для систем моніторингу (Nagios-сумісні) ---
OK=0
WARNING=1
CRITICAL=2
UNKNOWN=3

# --- Вхідні параметри ---
COMMUNITY=$1   # SNMP community string
HOST=$2        # IP або хостнейм пристрою
OID_1=$3       # OID для загального обсягу сховища (hrStorageSize)
OID_2=$4       # OID для використаного місця (hrStorageUsed)
EDGE_1=$5      # Поріг WARNING (наприклад, 80)
EDGE_2=$6      # Поріг CRITICAL (наприклад, 90)

# Перевірка наявності всіх аргументів
if [ -z "$EDGE_2" ]; then
    echo "UNKNOWN - Missing arguments. Usage: $0 <community> <host> <OID_size> <OID_used> <warning> <critical>"
    exit $UNKNOWN
fi

# --- Отримуємо загальний обсяг сховища ---
SNMP_SIZE=$(/usr/bin/snmpwalk -v2c -m "" -c "$COMMUNITY" "$HOST" "$OID_1" | head -n1)
if [ $? -ne 0 ] || [ -z "$SNMP_SIZE" ]; then
    echo "CRITICAL - SNMP query failed for total size"
    exit $CRITICAL
fi

# --- Отримуємо використане місце ---
SNMP_USED=$(/usr/bin/snmpwalk -v2c -m "" -c "$COMMUNITY" "$HOST" "$OID_2" | head -n1)
if [ $? -ne 0 ] || [ -z "$SNMP_USED" ]; then
    echo "CRITICAL - SNMP query failed for used space"
    exit $CRITICAL
fi

# --- Витягуємо тільки числові значення ---
STORAGE_SIZE=$(echo "$SNMP_SIZE" | sed -E 's/.*: *([0-9]+)$/\1/')
STORAGE_USED=$(echo "$SNMP_USED" | sed -E 's/.*: *([0-9]+)$/\1/')

# Перевіряємо коректність значень
if ! [[ "$STORAGE_SIZE" =~ ^[0-9]+$ && "$STORAGE_USED" =~ ^[0-9]+$ ]]; then
    echo "UNKNOWN - Invalid SNMP data format"
    exit $UNKNOWN
fi

# Захист від ділення на нуль
if [ "$STORAGE_SIZE" -eq 0 ]; then
    echo "UNKNOWN - Storage size is 0"
    exit $UNKNOWN
fi

# --- Розрахунок зайнятого місця у відсотках (з двома десятковими) ---
STORAGE_USED_PERCENT=$(echo "scale=2; $STORAGE_USED * 100 / $STORAGE_SIZE" | bc)

# --- Форматуємо відображення (кома замість крапки) ---
STORAGE_USED_DISPLAY=$(echo "$STORAGE_USED_PERCENT" | sed 's/\./,/')

# --- Логіка перевірки thresholds ---
if (( $(echo "$STORAGE_USED_PERCENT > $EDGE_2" | bc -l) )); then
    echo "CRITICAL - Storage usage is ${STORAGE_USED_DISPLAY}%"
    exit $CRITICAL
elif (( $(echo "$STORAGE_USED_PERCENT > $EDGE_1" | bc -l) )); then
    echo "WARNING - Storage usage is ${STORAGE_USED_DISPLAY}%"
    exit $WARNING
else
    echo "OK - Storage usage is ${STORAGE_USED_DISPLAY}%"
    exit $OK
fi