#!/usr/bin/env python3
# /// script
# dependencies = [
#   "psutil>=5.9.0",
# ]
# ///
"""
System load average check for Nagios.

Usage:
    check_load.py --warn 4.0 --crit 8.0

Exit codes:
    0 = OK
    1 = WARNING
    2 = CRITICAL
    3 = UNKNOWN
"""

import argparse
import os
import sys
import psutil


# Nagios exit codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def check_load() -> tuple[int, str, str]:
    """Check system load average and return (exit_code, message, perfdata)."""
    try:
        load1, load5, load15 = os.getloadavg()
        cpu_count = psutil.cpu_count() or 1

        # Normalize load by CPU count
        load1_norm = load1 / cpu_count
        load5_norm = load5 / cpu_count
        load15_norm = load15 / cpu_count

        perfdata = (
            f"load1={load1:.2f} "
            f"load5={load5:.2f} "
            f"load15={load15:.2f} "
            f"cpus={cpu_count}"
        )

        message = (
            f"Load average: {load1:.2f} (1m), {load5:.2f} (5m), {load15:.2f} (15m) "
            f"[{cpu_count} CPUs]"
        )

        return OK, message, perfdata

    except OSError as e:
        return UNKNOWN, f"Cannot read load average: {e}", ""
    except Exception as e:
        return UNKNOWN, f"Error: {e}", ""


def main():
    parser = argparse.ArgumentParser(description="System load check for Nagios")
    parser.add_argument("--warn", type=float, required=True, help="Warning threshold (1-minute load)")
    parser.add_argument("--crit", type=float, required=True, help="Critical threshold (1-minute load)")
    parser.add_argument("--per-cpu", action="store_true", help="Normalize load by CPU count")
    args = parser.parse_args()

    exit_code, message, perfdata = check_load()

    if exit_code == OK:
        try:
            # Extract 1-minute load from message
            load1 = float(message.split("Load average: ")[1].split(" ")[0])

            if args.per_cpu:
                cpu_count = psutil.cpu_count() or 1
                load1 = load1 / cpu_count

            if load1 >= args.crit:
                exit_code = CRITICAL
                message = f"Load average: {load1:.2f} (>={args.crit})"
            elif load1 >= args.warn:
                exit_code = WARNING
                message = f"Load average: {load1:.2f} (>={args.warn})"
        except (ValueError, IndexError):
            pass

    output = f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}"
    if perfdata:
        output += f" | {perfdata}"

    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
