#!/bin/bash
# MikroTik RouterOS storage usage check via SSH
#
# SSHes into the MikroTik, runs "/system resource print",
# parses total-hdd-space and free-hdd-space (in MiB),
# and returns OK/WARNING/CRITICAL based on used percentage.
#
# Output format: STATUS - X.X/YG used - Z%
#
# Usage: check_snmp_storage_mikrotik.sh <host> <warn> <crit>
# Example: check_snmp_storage_mikrotik.sh 192.168.1.2 80 90

OK=0
WARNING=1
CRITICAL=2
UNKNOWN=3

HOST=$1
WARN=$2
CRIT=$3

SSH_USER="master"
SSH_PASS="111"

if [ -z "$CRIT" ]; then
    echo "UNKNOWN - Missing arguments. Usage: $0 <host> <warn> <crit>"
    exit $UNKNOWN
fi

format_bytes() {
    local bytes=$1
    if [ "$bytes" -ge 1073741824 ]; then
        echo "$(echo "scale=1; $bytes / 1073741824" | bc)G"
    elif [ "$bytes" -ge 1048576 ]; then
        echo "$(echo "scale=1; $bytes / 1048576" | bc)M"
    else
        echo "${bytes}B"
    fi
}

output=$(sshpass -p "$SSH_PASS" ssh \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=10 \
    -o UserKnownHostsFile=/dev/null \
    "$SSH_USER@$HOST" \
    "/system resource print" 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$output" ]; then
    echo "UNKNOWN - SSH connection failed to $HOST"
    exit $UNKNOWN
fi

total_raw=$(echo "$output" | grep "total-hdd-space:" | head -1 | sed 's/.*:[[:space:]]*//' | grep -oP '[\d.]+' | head -1)
free_raw=$(echo "$output" | grep "free-hdd-space:" | head -1 | sed 's/.*:[[:space:]]*//' | grep -oP '[\d.]+' | head -1)

if [ -z "$total_raw" ] || [ -z "$free_raw" ]; then
    echo "UNKNOWN - Could not parse storage data from $HOST"
    exit $UNKNOWN
fi

total_bytes=$(echo "$total_raw * 1048576" | bc 2>/dev/null)
free_bytes=$(echo "$free_raw * 1048576" | bc 2>/dev/null)

if [ -z "$total_bytes" ] || [ -z "$free_bytes" ] || [ "$(echo "$total_bytes <= 0" | bc)" -eq 1 ]; then
    echo "UNKNOWN - Invalid storage values: total=${total_raw}MiB free=${free_raw}MiB"
    exit $UNKNOWN
fi

used_bytes=$(echo "$total_bytes - $free_bytes" | bc)
used_pct=$(echo "scale=0; $used_bytes * 100 / $total_bytes" | bc)

used_str=$(format_bytes "$used_bytes")
total_str=$(format_bytes "$total_bytes")

if [ "$used_pct" -ge "$CRIT" ]; then
    echo "CRITICAL - ${used_str}/${total_str} used - ${used_pct}%"
    exit $CRITICAL
elif [ "$used_pct" -ge "$WARN" ]; then
    echo "WARNING - ${used_str}/${total_str} used - ${used_pct}%"
    exit $WARNING
else
    echo "OK - ${used_str}/${total_str} used - ${used_pct}%"
    exit $OK
fi
