import os
import sys

from dotenv import load_dotenv
import requests
from pysnmp.hlapi import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    nextCmd,
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SNMP_PORT = int(os.getenv("SNMP_PORT", "161"))
SWITCHES = os.getenv("SWITCHES", "")

WARNING_PCT = 80
CRITICAL_PCT = 90

OID_HR_STORAGE_ENTRY = "1.3.6.1.2.1.25.2.3.1"
STORAGE_TYPES = {
    "1.3.6.1.2.1.25.2.1.4",  # fixedDisk
    "1.3.6.1.2.1.25.2.1.9",  # flashMemory
}


def walk_oid(host, oid_prefix):
    results = []
    iterator = nextCmd(
        SnmpEngine(),
        CommunityData(SNMP_COMMUNITY),
        UdpTransportTarget((host, SNMP_PORT), timeout=5, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid_prefix)),
        lexicographicMode=False,
    )
    for errorIndication, errorStatus, errorIndex, varBinds in iterator:
        if errorIndication:
            raise Exception(f"SNMP error: {errorIndication}")
        if errorStatus:
            at = (
                varBinds[int(errorIndex) - 1][0]
                if errorIndex
                else "?"
            )
            raise Exception(f"SNMP error: {errorStatus} at {at}")
        for varBind in varBinds:
            oid_str = str(varBind[0])
            if not oid_str.startswith(oid_prefix.rstrip(".") + "."):
                return results
            results.append((oid_str, varBind[1]))
    return results


def get_storage_info(host):
    rows = walk_oid(host, OID_HR_STORAGE_ENTRY)
    storage = {}
    for oid_str, value in rows:
        parts = oid_str.split(".")
        idx = parts[-1]
        col = parts[-2]
        if idx not in storage:
            storage[idx] = {}
        if col == "2":
            storage[idx]["type"] = str(value)
        elif col == "3":
            storage[idx]["descr"] = str(value)
        elif col == "4":
            storage[idx]["alloc"] = int(value)
        elif col == "5":
            storage[idx]["size"] = int(value)
        elif col == "6":
            storage[idx]["used"] = int(value)
    result = []
    for idx, info in storage.items():
        if info.get("type") not in STORAGE_TYPES:
            continue
        size = info.get("size", 0)
        used = info.get("used", 0)
        alloc = info.get("alloc", 1)
        if size <= 0:
            continue
        used_pct = (used / size) * 100
        result.append({
            "descr": info.get("descr", "unknown"),
            "used_pct": used_pct,
            "total_bytes": size * alloc,
            "used_bytes": used * alloc,
        })
    return result


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured", file=sys.stderr)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        },
        timeout=10,
    )
    resp.raise_for_status()


def main():
    switches = [s.strip() for s in SWITCHES.split(",") if s.strip()]
    if not switches:
        print("No switches configured", file=sys.stderr)
        sys.exit(1)
    messages = []
    for ip in switches:
        print(f"Checking {ip}...")
        try:
            entries = get_storage_info(ip)
            if not entries:
                print(f"  No relevant storage found")
                continue
            for entry in entries:
                pct = entry["used_pct"]
                if pct > CRITICAL_PCT:
                    severity = "CRITICAL"
                    icon = "🚨"
                elif pct > WARNING_PCT:
                    severity = "WARNING"
                    icon = "⚠️"
                else:
                    continue
                used_mb = entry["used_bytes"] // 1024 // 1024
                total_mb = entry["total_bytes"] // 1024 // 1024
                msg = (
                    f"{icon} <b>{severity}</b>\n"
                    f"Switch: {ip}\n"
                    f"Storage: {entry['descr']}\n"
                    f"Used: {pct:.1f}% ({used_mb}MB / {total_mb}MB)"
                )
                messages.append(msg)
                print(f"  {severity}: {entry['descr']} {pct:.1f}%")
        except Exception as e:
            msg = f"❌ <b>ERROR</b>\nSwitch: {ip}\nError: {e}"
            messages.append(msg)
            print(f"  Error: {e}", file=sys.stderr)
    if messages:
        send_telegram("\n\n".join(messages))
        print("\nTelegram notification sent")
    else:
        print("\nAll switches OK")


if __name__ == "__main__":
    main()
