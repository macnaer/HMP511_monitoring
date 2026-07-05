#!/usr/bin/env python3
# /// script
# dependencies = [
#   "psutil>=5.9.0",
# ]
# ///
"""
CPU usage check for Nagios.

Usage:
    check_cpu.py --warn 80 --crit 95

Exit codes:
    0 = OK
    1 = WARNING
    2 = CRITICAL
    3 = UNKNOWN
"""

import argparse
import sys
import psutil


# Nagios exit codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def check_cpu(interval: float = 1.0) -> tuple[int, str]:
    """Check CPU usage and return (exit_code, message)."""
    try:
        cpu_percent = psutil.cpu_percent(interval=interval)
        if cpu_percent is None:
            return UNKNOWN, "Cannot read CPU usage"

        return OK, f"CPU usage: {cpu_percent}%"
    except Exception as e:
        return UNKNOWN, f"Error reading CPU: {e}"


def main():
    parser = argparse.ArgumentParser(description="CPU usage check for Nagios")
    parser.add_argument("--warn", type=float, required=True, help="Warning threshold (%)")
    parser.add_argument("--crit", type=float, required=True, help="Critical threshold (%)")
    parser.add_argument("--interval", type=float, default=1.0, help="Measurement interval in seconds")
    args = parser.parse_args()

    exit_code, message = check_cpu(args.interval)

    if exit_code == OK:
        try:
            cpu_value = float(message.split(": ")[1].rstrip("%"))
            if cpu_value >= args.crit:
                exit_code = CRITICAL
                message = f"CPU usage: {cpu_value}% (>={args.crit}%)"
            elif cpu_value >= args.warn:
                exit_code = WARNING
                message = f"CPU usage: {cpu_value}% (>={args.warn}%)"
        except (ValueError, IndexError):
            pass

    print(f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
