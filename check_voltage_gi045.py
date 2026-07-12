#!/usr/bin/env python3
"""
Nagios check plugin: SFP Voltage on Cisco switch
Checks voltage of SFP transceiver via SSH (plink)

Nagios exit codes:
  0 = OK
  1 = WARNING
  2 = CRITICAL
  3 = UNKNOWN

Usage:
  python check_voltage_gi045.py
  python check_voltage_gi045.py -H 194.44.149.125 -p 8759 -i Gi0/45 -w 3.00,3.50 -c 2.90,3.60
"""

import subprocess
import os
import sys
import argparse

PLINK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plink.exe")

EXIT_OK = 0
EXIT_WARNING = 1
EXIT_CRITICAL = 2
EXIT_UNKNOWN = 3


def parse_args():
    parser = argparse.ArgumentParser(description="Nagios check: SFP Voltage")
    parser.add_argument("-H", "--host", default="194.44.149.125", help="Switch IP")
    parser.add_argument("-p", "--port", type=int, default=8759, help="SSH port")
    parser.add_argument("-u", "--user", default="demo", help="SSH user")
    parser.add_argument("-P", "--password", default="Qwerty-1", help="SSH password")
    parser.add_argument("-i", "--interface", default="Gi0/45", help="Interface name")
    parser.add_argument(
        "-w", "--warning", default="3.00,3.50",
        help="Warning thresholds: low,high (default: 3.00,3.50)"
    )
    parser.add_argument(
        "-c", "--critical", default="2.90,3.60",
        help="Critical thresholds: low,high (default: 2.90,3.60)"
    )
    return parser.parse_args()


def get_transceiver(host, port, user, password, interface):
    cmd = (
        f'echo y | "{PLINK}" -P {port} -pw {password} '
        f'{user}@{host} show interface {interface} transceiver detail'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return result.stdout


def parse_voltage(output):
    lines = output.splitlines()
    voltage = None
    section = None

    for line in lines:
        stripped = line.strip()
        if "Voltage" in stripped and "Threshold" in stripped:
            section = "voltage"
            continue
        if "Temperature" in stripped and "Threshold" in stripped:
            section = None
            continue
        if "Transmit Power" in stripped:
            section = None
            continue
        if "Receive Power" in stripped:
            section = None
            continue

        if stripped.startswith("Gi") and section == "voltage":
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    voltage = float(parts[1])
                except ValueError:
                    pass
            section = None

    return voltage


def main():
    args = parse_args()

    try:
        warn_low, warn_high = [float(x.strip()) for x in args.warning.split(",")]
        crit_low, crit_high = [float(x.strip()) for x in args.critical.split(",")]
    except ValueError:
        print(f"UNKNOWN - Invalid threshold format. Use: low,high")
        sys.exit(EXIT_UNKNOWN)

    try:
        output = get_transceiver(args.host, args.port, args.user, args.password, args.interface)
    except subprocess.TimeoutExpired:
        print(f"CRITICAL - SSH connection timeout to {args.host}")
        sys.exit(EXIT_CRITICAL)
    except Exception as e:
        print(f"UNKNOWN - {e}")
        sys.exit(EXIT_UNKNOWN)

    voltage = parse_voltage(output)

    if voltage is None:
        print(f"UNKNOWN - Could not parse voltage from {args.interface}")
        sys.exit(EXIT_UNKNOWN)

    perfdata = f"voltage={voltage:.2f}V;{warn_low},{warn_high};{crit_low},{crit_high}"

    if voltage < crit_low:
        print(f"CRITICAL - {args.interface} voltage LOW: {voltage:.2f}V (threshold: <{crit_low:.2f}V) | {perfdata}")
        sys.exit(EXIT_CRITICAL)
    elif voltage > crit_high:
        print(f"CRITICAL - {args.interface} voltage HIGH: {voltage:.2f}V (threshold: >{crit_high:.2f}V) | {perfdata}")
        sys.exit(EXIT_CRITICAL)
    elif voltage < warn_low:
        print(f"WARNING - {args.interface} voltage low: {voltage:.2f}V (threshold: <{warn_low:.2f}V) | {perfdata}")
        sys.exit(EXIT_WARNING)
    elif voltage > warn_high:
        print(f"WARNING - {args.interface} voltage high: {voltage:.2f}V (threshold: >{warn_high:.2f}V) | {perfdata}")
        sys.exit(EXIT_WARNING)
    else:
        print(f"OK - {args.interface} voltage: {voltage:.2f}V | {perfdata}")
        sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
