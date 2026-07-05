#!/bin/bash
# MikroTik RouterOS storage usage check via SSH
#
# SSHes into the MikroTik, runs "/system resource print",
# parses total-hdd-space and free-hdd-space,
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

SSH_USER="test"
SSH_PASS="Qwerty-1"

if [ -z "$CRIT" ]; then
    echo "UNKNOWN - Missing arguments. Usage: $0 <host> <warn> <crit>"
    exit $UNKNOWN
fi

to_bytes() {
    local val=$1
    local unit=$2
    case "$unit" in
        *GiB|*GB)   echo "$val * 1073741824" | bc ;;
        *MiB|*MB)   echo "$val * 1048576" | bc ;;
        *KiB|*kB)   echo "$val * 1024" | bc ;;
        *B)         echo "$val" ;;
        *)          echo "$val * 1048576" | bc ;;
    esac
}

format_bytes() {
    local bytes=$1
    if [ "$(echo "$bytes >= 1073741824" | bc)" -eq 1 ]; then
        echo "$(echo "scale=1; $bytes / 1073741824" | bc)G"
    elif [ "$(echo "$bytes >= 1048576" | bc)" -eq 1 ]; then
        echo "$(echo "scale=1; $bytes / 1048576" | bc)M"
    else
        echo "$(echo "scale=1; $bytes / 1024" | bc)K"
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

total_line=$(echo "$output" | awk -F': ' '/total-hdd-space:/ {print $2}')
free_line=$(echo "$output" | awk -F': ' '/free-hdd-space:/ {print $2}')

total_val=$(echo "$total_line" | awk '{print $1}')
total_unit=$(echo "$total_line" | awk '{print $2}')
free_val=$(echo "$free_line" | awk '{print $1}')
free_unit=$(echo "$free_line" | awk '{print $2}')

if [ -z "$total_val" ] || [ -z "$free_val" ]; then
    echo "UNKNOWN - Could not parse storage data from $HOST"
    exit $UNKNOWN
fi

total_bytes=$(to_bytes "$total_val" "$total_unit")
free_bytes=$(to_bytes "$free_val" "$free_unit")

if [ "$(echo "$total_bytes <= 0" | bc)" -eq 1 ]; then
    echo "UNKNOWN - Invalid storage values: total=${total_val}${total_unit} free=${free_val}${free_unit}"
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
