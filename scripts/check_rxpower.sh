#!/bin/bash
# check_rxpower.sh - Check SFP Rx power via SSH using built-in DOM thresholds
#
# Connects via SSH, runs 'show interfaces <port> transceiver detail', 
# parses the Receive Power value and the SFP's own alarm/warning thresholds.
#
# Exit codes: 0=OK, 1=WARN, 2=CRIT, 3=UNKNOWN
#
# Usage:
#   check_rxpower.sh <host> <port> [--user USER] [--password PASS]
#
# Credentials loaded from (in order of precedence):
#   1. --user / --password CLI flags
#   2. USERNAME (or USRERNAME) / PASSWORD environment variables
#   3. .env file in the project root

OK=0
WARNING=1
CRITICAL=2
UNKNOWN=3

HOST="$1"
PORT="$2"
ARG_USER=""
ARG_PASS=""
SSH_PORT=22

# Snapshot env vars before local vars shadow them
ENV_USER=$(env | grep '^USERNAME=' | head -1 | cut -d= -f2-)
ENV_USER2=$(env | grep '^USRERNAME=' | head -1 | cut -d= -f2-)
[ -z "$ENV_USER" ] && ENV_USER="$ENV_USER2"
ENV_PASS=$(env | grep '^PASSWORD=' | head -1 | cut -d= -f2-)
ENV_PORT=$(env | grep '^INTERNAL_PORT=' | head -1 | cut -d= -f2-)
[ -n "$ENV_PORT" ] && SSH_PORT="$ENV_PORT"

# Parse optional --user and --password flags
shift 2 2>/dev/null || true
while [ $# -gt 0 ]; do
    case "$1" in
        --user)     ARG_USER="$2"; shift 2 ;;
        --password) ARG_PASS="$2"; shift 2 ;;
        *)          shift ;;
    esac
done

# Load credentials with precedence: CLI args > env vars > .env file
SSH_USER="$ARG_USER"
SSH_PASS="$ARG_PASS"

if [ -z "$SSH_USER" ]; then
    SSH_USER="$ENV_USER"
fi
if [ -z "$SSH_PASS" ]; then
    SSH_PASS="$ENV_PASS"
fi

if [ -z "$SSH_USER" ] || [ -z "$SSH_PASS" ]; then
    local env_file=""
    if [ -f ".env" ]; then
        env_file=".env"
    elif [ -f "../.env" ]; then
        env_file="../.env"
    elif [ -f "../../.env" ]; then
        env_file="../../.env"
    elif [ -f "/.env" ]; then
        env_file="/.env"
    fi
    if [ -n "$env_file" ]; then
        while IFS='=' read -r key value || [ -n "$key" ]; do
            key=$(echo "$key" | tr -d '[:space:]')
            value=$(echo "$value" | tr -d '"' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            case "$key" in
                USERNAME|USRERNAME) [ -z "$SSH_USER" ] && SSH_USER="$value" ;;
                PASSWORD)          [ -z "$SSH_PASS" ] && SSH_PASS="$value" ;;
                INTERNAL_PORT)     SSH_PORT="$value" ;;
            esac
        done < "$env_file"
    fi
fi

if [ -z "$SSH_USER" ] || [ -z "$SSH_PASS" ]; then
    echo "UNKNOWN - SSH credentials not found. Set USERNAME/PASSWORD env vars or --user/--password flags."
    exit $UNKNOWN
fi

if [ -z "$HOST" ] || [ -z "$PORT" ]; then
    echo "UNKNOWN - Usage: check_rxpower.sh <host> <port> [--user USER] [--password PASS]"
    exit $UNKNOWN
fi

# Expand Cisco shorthand interface names (Gi → GigabitEthernet, etc.)
case "$PORT" in
    Gi*)   FULL_PORT="GigabitEthernet${PORT#Gi}" ;;
    Fa*)   FULL_PORT="FastEthernet${PORT#Fa}" ;;
    Te*)   FULL_PORT="TenGigabitEthernet${PORT#Te}" ;;
    Tw*)   FULL_PORT="TwoGigabitEthernet${PORT#Tw}" ;;
    Fo*)   FULL_PORT="FortyGigabitEthernet${PORT#Fo}" ;;
    Hu*)   FULL_PORT="HundredGigabitEthernet${PORT#Hu}" ;;
    Po*)   FULL_PORT="Port-channel${PORT#Po}" ;;
    Vl*)   FULL_PORT="Vlan${PORT#Vl}" ;;
    Lo*)   FULL_PORT="Loopback${PORT#Lo}" ;;
    *)     FULL_PORT="$PORT" ;;
esac

SSH_ERR=$(mktemp)

sshpass -p "$SSH_PASS" ssh \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o KexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1,diffie-hellman-group-exchange-sha1 \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o Ciphers=+aes128-cbc,aes192-cbc,aes256-cbc \
    "$SSH_USER@$HOST" \
    "$(printf 'terminal length 0\nshow interfaces %s transceiver detail' "$FULL_PORT")" > "$SSH_ERR" 2>&1
SSH_RC=$?
OUTPUT=$(cat "$SSH_ERR")

if [ $SSH_RC -ne 0 ] || [ -z "$OUTPUT" ]; then
    SSH_MSG=$(cat "$SSH_ERR" 2>/dev/null | tail -10)
    rm -f "$SSH_ERR"
    echo "CRITICAL - SSH failed to $HOST (rc=$SSH_RC: $SSH_MSG)"
    exit $CRITICAL
fi
rm -f "$SSH_ERR"

# Parse Receive Power from transceiver detail output.
# Supports tabular format (all values on same line as "Receive Power"):
#   Receive Power (dBm):  -2.5  0.0  -1.0  -15.0  -17.0
RX_LINE=$(echo "$OUTPUT" | awk '
    /[Rr]eceive [Pp]ower/ {
        vals = ""
        for (i = 1; i <= NF; i++) {
            if ($i ~ /^-?[0-9]+(\.[0-9]+)?$/) {
                vals = vals ? vals " " $i : $i
            }
        }
        if (vals) {
            print NR, vals
            exit
        }
    }
')

if [ -z "$RX_LINE" ]; then
    echo "UNKNOWN - Could not parse Receive Power data for $PORT on $HOST"
    echo "---BEGIN RAW OUTPUT---"
    echo "$OUTPUT" | tail -40
    echo "---END RAW OUTPUT---"
    exit $UNKNOWN
fi

RX_VALUE=$(echo "$RX_LINE" | awk '{print $2}')
HIGH_ALARM=$(echo "$RX_LINE" | awk '{print $3}')
HIGH_WARN=$(echo "$RX_LINE" | awk '{print $4}')
LOW_WARN=$(echo "$RX_LINE" | awk '{print $5}')
LOW_ALARM=$(echo "$RX_LINE" | awk '{print $6}')

# Validate all values are numeric
for val in "$RX_VALUE" "$HIGH_ALARM" "$HIGH_WARN" "$LOW_WARN" "$LOW_ALARM"; do
    if ! echo "$val" | grep -qE '^-?[0-9]+(\.[0-9]+)?$'; then
        echo "UNKNOWN - Failed to parse numeric value: '$val' (raw line: $RX_LINE)"
        exit $UNKNOWN
    fi
done

# Compare against built-in thresholds
STATUS=$OK
STATUS_TEXT="OK"

check_threshold() {
    local current=$1
    local threshold=$2
    local direction=$3  # "high" (worse if ABOVE) or "low" (worse if BELOW)
    
    if [ "$direction" = "high" ]; then
        if [ "$(echo "$current > $threshold" | bc -l)" -eq 1 ]; then
            return 0
        fi
    else
        if [ "$(echo "$current < $threshold" | bc -l)" -eq 1 ]; then
            return 0
        fi
    fi
    return 1
}

# Check thresholds in order: critical first (more severe), then warning
if check_threshold "$RX_VALUE" "$HIGH_ALARM" "high" || check_threshold "$RX_VALUE" "$LOW_ALARM" "low"; then
    STATUS=$CRITICAL
    STATUS_TEXT="CRITICAL"
elif check_threshold "$RX_VALUE" "$HIGH_WARN" "high" || check_threshold "$RX_VALUE" "$LOW_WARN" "low"; then
    STATUS=$WARNING
    STATUS_TEXT="WARNING"
fi

PERFDATA="rxpower=$RX_VALUE;$LOW_WARN;$LOW_ALARM;$HIGH_WARN;$HIGH_ALARM"

echo "$STATUS_TEXT - Rx Power $RX_VALUE dBm on $PORT (low: ${LOW_ALARM}/${LOW_WARN}, high: ${HIGH_WARN}/${HIGH_ALARM}) | $PERFDATA"
exit $STATUS
