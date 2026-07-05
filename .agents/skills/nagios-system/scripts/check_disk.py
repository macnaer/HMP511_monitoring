#!/usr/bin/env python3
# /// script
# dependencies = [
#   "psutil>=5.9.0",
# ]
# ///
"""
Disk usage check for Nagios.

Usage:
    check_disk.py --path / --warn 80 --crit 90
    check_disk.py --path C:\\ --warn 80 --crit 90

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


def check_disk(path: str) -> tuple[int, str, str]:
    """Check disk usage and return (exit_code, message, perfdata)."""
    try:
        usage = psutil.disk_usage(path)

        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        percent = usage.percent

        perfdata = (
            f"disk_total={total_gb:.2f}GB "
            f"disk_used={used_gb:.2f}GB "
            f"disk_free={free_gb:.2f}GB "
            f"disk_percent={percent}%"
        )

        message = f"Disk {path}: {percent}% used ({used_gb:.1f}/{total_gb:.1f}GB, {free_gb:.1f}GB free)"

        return OK, message, perfdata

    except FileNotFoundError:
        return UNKNOWN, f"Path not found: {path}", ""
    except PermissionError:
        return UNKNOWN, f"Permission denied: {path}", ""
    except Exception as e:
        return UNKNOWN, f"Error checking disk: {e}", ""


def main():
    parser = argparse.ArgumentParser(description="Disk usage check for Nagios")
    parser.add_argument("--path", default="/", help="Path to check (default: /)")
    parser.add_argument("--warn", type=float, required=True, help="Warning threshold (%)")
    parser.add_argument("--crit", type=float, required=True, help="Critical threshold (%)")
    args = parser.parse_args()

    exit_code, message, perfdata = check_disk(args.path)

    if exit_code == OK:
        try:
            disk_percent = float(message.split(": ")[1].split("%")[0])
            if disk_percent >= args.crit:
                exit_code = CRITICAL
                message = f"Disk {args.path}: {disk_percent}% used (>={args.crit}%)"
            elif disk_percent >= args.warn:
                exit_code = WARNING
                message = f"Disk {args.path}: {disk_percent}% used (>={args.warn}%)"
        except (ValueError, IndexError):
            pass

    output = f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}"
    if perfdata:
        output += f" | {perfdata}"

    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
