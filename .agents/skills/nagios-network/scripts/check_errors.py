#!/usr/bin/env python3
# /// script
# dependencies = [
#   "psutil>=5.9.0",
# ]
# ///
"""
Network interface errors check for Nagios.

Usage:
    check_errors.py --interface eth0 --warn 100 --crit 1000

Exit codes:
    0 = OK
    1 = WARNING
    2 = CRITICAL
    3 = UNKNOWN
"""

import argparse
import sys
import time
import psutil


# Nagios exit codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def get_errors(interface: str) -> dict | None:
    """Get current error counters for an interface."""
    try:
        stats = psutil.net_io_counters(pernic=True)
        if interface not in stats:
            return None
        return {
            "errin": stats[interface].errin,
            "errout": stats[interface].errout,
            "dropin": stats[interface].dropin,
            "dropout": stats[interface].dropout,
        }
    except Exception:
        return None


def check_errors(interface: str, interval: float = 1.0,
                 warn: float = 100, crit: float = 1000) -> tuple[int, str, str]:
    """Check interface errors and discards."""
    try:
        # Get initial counters
        stats1 = get_errors(interface)
        if stats1 is None:
            return UNKNOWN, f"Interface not found: {interface}", ""

        time.sleep(interval)

        # Get final counters
        stats2 = get_errors(interface)
        if stats2 is None:
            return UNKNOWN, f"Interface not found: {interface}", ""

        # Calculate rates (errors per second)
        errin_rate = (stats2["errin"] - stats1["errin"]) / interval
        errout_rate = (stats2["errout"] - stats1["errout"]) / interval
        dropin_rate = (stats2["dropin"] - stats1["dropin"]) / interval
        dropout_rate = (stats2["dropout"] - stats1["dropout"]) / interval

        total_errors = errin_rate + errout_rate
        total_drops = dropin_rate + dropout_rate

        perfdata = (
            f"errors_in={errin_rate:.2f}/s "
            f"errors_out={errout_rate:.2f}/s "
            f"drops_in={dropin_rate:.2f}/s "
            f"drops_out={dropout_rate:.2f}/s"
        )

        # Check thresholds
        if total_errors >= crit or total_drops >= crit:
            return CRITICAL, (
                f"Errors: {errin_rate:.1f}/s in, {errout_rate:.1f}/s out, "
                f"Drops: {dropin_rate:.1f}/s in, {dropout_rate:.1f}/s out"
            ), perfdata
        elif total_errors >= warn or total_drops >= warn:
            return WARNING, (
                f"Errors: {errin_rate:.1f}/s in, {errout_rate:.1f}/s out, "
                f"Drops: {dropin_rate:.1f}/s in, {dropout_rate:.1f}/s out"
            ), perfdata

        message = (
            f"Errors: {errin_rate:.1f}/s in, {errout_rate:.1f}/s out, "
            f"Drops: {dropin_rate:.1f}/s in, {dropout_rate:.1f}/s out"
        )
        return OK, message, perfdata

    except Exception as e:
        return UNKNOWN, f"Error checking errors: {e}", ""


def main():
    parser = argparse.ArgumentParser(description="Network errors check for Nagios")
    parser.add_argument("--interface", required=True, help="Network interface name (e.g., eth0, ens192)")
    parser.add_argument("--interval", type=float, default=1.0, help="Measurement interval in seconds")
    parser.add_argument("--warn", type=float, default=100, help="Warning threshold (errors/drops per second)")
    parser.add_argument("--crit", type=float, default=1000, help="Critical threshold (errors/drops per second)")
    args = parser.parse_args()

    exit_code, message, perfdata = check_errors(
        args.interface, args.interval, args.warn, args.crit
    )

    output = f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}"
    if perfdata:
        output += f" | {perfdata}"

    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
