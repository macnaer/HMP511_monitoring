#!/bin/bash
# check_snmp_hikvision.sh
# Виклик: check_snmp_hikvision.sh <host> <community> <OID> <warn> <crit> <unit> <timeout>

HOST=$1
COMMUNITY=$2
OID=$3
WARN=$4
CRIT=$5
UNIT=$6
TIMEOUT=${7:-30}

# Отримуємо значення через snmpget
VALUE_RAW=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t "$TIMEOUT" "$HOST" "$OID")
if [ $? -ne 0 ]; then
    echo "CRITICAL - SNMP query failed"
    exit 2
fi

# Видаляємо лапки, пробіли
VALUE=$(echo "$VALUE_RAW" | sed 's/"//g' | sed 's/ //g')

# Перевірка, чи значення числове (відсотки або абсолютне)
if [[ "$VALUE" =~ ^[0-9]+$ ]] || [[ "$VALUE" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    # Числове, перевіряємо пороги
    if [[ "$WARN" != "none" && "$CRIT" != "none" ]]; then
        if (( VALUE >= CRIT )); then
            echo "CRITICAL - $VALUE$UNIT (>$CRIT)"
            exit 2
        elif (( VALUE >= WARN )); then
            echo "WARNING - $VALUE$UNIT (>$WARN)"
            exit 1
        else
            echo "OK - $VALUE$UNIT"
            exit 0
        fi
    else
        echo "OK - $VALUE$UNIT"
        exit 0
    fi
else
    # Строкове значення, просто показуємо
    echo "OK - $VALUE"
    exit 0
fi