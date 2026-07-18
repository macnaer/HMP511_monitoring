#!/bin/bash

OK=0
WARNING=1
CRITICAL=2
UNKNOWN=3

HOST=$1
WARN_THRESH=${2:-15}
CRIT_THRESH=${3:-25}
COMMUNITY=${NAGIOS_SNMP_COMMUNITY:-LibreNms}
TIMEOUT=${NAGIOS_SNMP_TIMEOUT:-30}

OID_ADMIN="1.3.6.1.2.1.2.2.1.7"
OID_OPER="1.3.6.1.2.1.2.2.1.8"
OID_DESCR="1.3.6.1.2.1.2.2.1.2"

ADMIN_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -Oqn -t "$TIMEOUT" "$HOST" "$OID_ADMIN" 2>/dev/null)
if [ -z "$ADMIN_RAW" ]; then
    echo "UNKNOWN - SNMP query failed for ifAdminStatus"
    exit $UNKNOWN
fi

OPER_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -Oqn -t "$TIMEOUT" "$HOST" "$OID_OPER" 2>/dev/null)
DESCR_RAW=$(snmpwalk -v2c -c "$COMMUNITY" -Oqn -t "$TIMEOUT" "$HOST" "$OID_DESCR" 2>/dev/null)

declare -A DESCR_MAP
while IFS= read -r line; do
    [ -z "$line" ] && continue
    idx=$(echo "$line" | sed 's/.*\.//' | awk '{print $1}')
    name=$(echo "$line" | sed 's/.*= //' | tr -d '" ')
    DESCR_MAP[$idx]=$name
done <<< "$DESCR_RAW"

DOWN_PORTS=()
TOTAL_ADMIN_UP=0

while IFS= read -r line; do
    [ -z "$line" ] && continue
    idx=$(echo "$line" | sed 's/.*\.//' | awk '{print $1}')
    status=$(echo "$line" | sed 's/.*= //')
    [ "$status" != "1" ] && continue
    TOTAL_ADMIN_UP=$((TOTAL_ADMIN_UP + 1))

    oper_line=$(echo "$OPER_RAW" | grep "\.${idx} ")
    oper=$(echo "$oper_line" | sed 's/.*= //')
    if [ "$oper" = "2" ]; then
        name="${DESCR_MAP[$idx]:-ifIndex.$idx}"
        DOWN_PORTS+=("$name")
    fi
done <<< "$ADMIN_RAW"

DOWN_COUNT=${#DOWN_PORTS[@]}

if [ "$DOWN_COUNT" -eq 0 ]; then
    echo "OK - All interfaces up ($TOTAL_ADMIN_UP ports)"
    exit $OK
fi

DOWN_LIST=$(IFS=', '; echo "${DOWN_PORTS[*]}")

if [ "$DOWN_COUNT" -ge "$CRIT_THRESH" ] 2>/dev/null; then
    echo "CRITICAL - Interface(s) down: $DOWN_LIST ($DOWN_COUNT/$TOTAL_ADMIN_UP ports down)"
    exit $CRITICAL
elif [ "$DOWN_COUNT" -ge "$WARN_THRESH" ] 2>/dev/null; then
    echo "WARNING - Interface(s) down: $DOWN_LIST ($DOWN_COUNT/$TOTAL_ADMIN_UP ports down)"
    exit $WARNING
else
    echo "OK - $DOWN_COUNT ports down (below thresholds)"
    exit $OK
fi
