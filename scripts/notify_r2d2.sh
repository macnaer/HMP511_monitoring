#!/bin/bash

TOKEN="8656758355:AAHwJRJlkhmq8ToN1X2kKrzcszu78rD1KKU"
CHAT_ID="-1003817709239"

STATE="$1"
MESSAGE="$2"

# Вибір емоджі за станом
case "$STATE" in
    OK)
        EMOJI="🟢"
        ;;
    WARNING)
        EMOJI="🟡"
        ;;
    UNKNOWN)
        EMOJI="⚪"
        ;;
    CRITICAL)
        EMOJI="🔴"
        ;;
    *)
        EMOJI="⚙️"
        ;;
esac

FINAL_MSG="[$EMOJI Nagios] $MESSAGE"

curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d chat_id="${CHAT_ID}" \
    -d parse_mode="Markdown" \
    -d text="$FINAL_MSG" > /dev/null 2>&1