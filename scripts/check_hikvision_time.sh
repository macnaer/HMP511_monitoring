#!/bin/bash

HOST=$1
COMMUNITY=${NAGIOS_SNMP_COMMUNITY:-LibreNms}
TIMEOUT=${NAGIOS_SNMP_TIMEOUT:-30}
OID="1.3.6.1.4.1.39165.1.19.0"

VALUE=$(snmpget -v2c -c "$COMMUNITY" -Oqv -t "$TIMEOUT" "$HOST" "$OID" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$VALUE" ]; then
    echo "CRITICAL - SNMP query failed for system time"
    exit 2
fi

VALUE=$(echo "$VALUE" | tr -d '" ')
echo "OK - Time: $VALUE"
exit 0
