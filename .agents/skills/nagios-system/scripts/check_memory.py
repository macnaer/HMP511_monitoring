#!/usr/bin/env python3
# /// script
# dependencies = [
#   "psutil>=5.9.0",
# ]
# ///
"""
Memory usage check for Nagios.

Usage:
    check_memory.py --warn 80 --crit 95

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


def check_memory() -> tuple[int, str, dict]:
    """Check memory usage and return (exit_code, message, perfdata)."""
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Memory details
        total_gb = mem.total / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        percent = mem.percent

        # Swap details
        swap_total_gb = swap.total / (1024 ** 3)
        swap_used_gb = swap.used / (1024 ** 3)
        swap_percent = swap.percent

        perfdata = (
            f"mem_total={total_gb:.2f}GB "
            f"mem_used={used_gb:.2f}GB "
            f"mem_available={available_gb:.2f}GB "
            f"mem_percent={percent}% "
            f"swap_total={swap_total_gb:.2f}GB "
            f"swap_used={swap_used_gb:.2f}GB "
            f"swap_percent={swap_percent}%"
        )

        message = (
            f"RAM: {percent}% used ({used_gb:.1f}/{total_gb:.1f}GB), "
            f"Swap: {swap_percent}% used ({swap_used_gb:.1f}/{swap_total_gb:.1f}GB)"
        )

        return OK, message, perfdata

    except Exception as e:
        return UNKNOWN, f"Error reading memory: {e}", ""


def main():
    parser = argparse.ArgumentParser(description="Memory usage check for Nagios")
    parser.add_argument("--warn", type=float, required=True, help="Warning threshold (%)")
    parser.add_argument("--crit", type=float, required=True, help="Critical threshold (%)")
    args = parser.parse_args()

    exit_code, message, perfdata = check_memory()

    if exit_code == OK:
        try:
            # Extract RAM percentage from message
            ram_percent = float(message.split("RAM: ")[1].split("%")[0])
            if ram_percent >= args.crit:
                exit_code = CRITICAL
                message = f"RAM: {ram_percent}% used (>={args.crit}%)"
            elif ram_percent >= args.warn:
                exit_code = WARNING
                message = f"RAM: {ram_percent}% used (>={args.warn}%)"
        except (ValueError, IndexError):
            pass

    output = f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}"
    if perfdata:
        output += f" | {perfdata}"

    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
