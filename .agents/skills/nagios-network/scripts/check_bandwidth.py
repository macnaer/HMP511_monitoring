#!/usr/bin/env python3
# /// script
# dependencies = [
#   "psutil>=5.9.0",
# ]
# ///
"""
Network interface bandwidth check for Nagios.

Usage:
    check_bandwidth.py --interface eth0 --warn 80 --crit 95

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


def get_bytes(interface: str) -> tuple[int | None, int | None]:
    """Get current bytes sent/received for an interface."""
    try:
        stats = psutil.net_io_counters(pernic=True)
        if interface not in stats:
            return None, None
        return stats[interface].bytes_recv, stats[interface].bytes_sent
    except Exception:
        return None, None


def check_bandwidth(interface: str, interval: float = 1.0,
                    warn: float = 80.0, crit: float = 95.0,
                    speed: int | None = None) -> tuple[int, str, str]:
    """Check interface bandwidth usage."""
    try:
        # Get initial counters
        rx1, tx1 = get_bytes(interface)
        if rx1 is None:
            return UNKNOWN, f"Interface not found: {interface}", ""

        time.sleep(interval)

        # Get final counters
        rx2, tx2 = get_bytes(interface)
        if rx2 is None:
            return UNKNOWN, f"Interface not found: {interface}", ""

        # Calculate rates
        rx_rate = (rx2 - rx1) / interval  # bytes per second
        tx_rate = (tx2 - tx1) / interval

        rx_mbps = (rx_rate * 8) / (1024 * 1024)  # Convert to Mbps
        tx_mbps = (tx_rate * 8) / (1024 * 1024)

        perfdata = (
            f"rx_rate={rx_mbps:.2f}Mbps "
            f"tx_rate={tx_mbps:.2f}Mbps"
        )

        # Check against speed if provided
        if speed and speed > 0:
            rx_percent = (rx_mbps / speed) * 100
            tx_percent = (tx_mbps / speed) * 100

            max_percent = max(rx_percent, tx_percent)
            if max_percent >= crit:
                return CRITICAL, (
                    f"Bandwidth: RX {rx_mbps:.1f} Mbps ({rx_percent:.1f}%), "
                    f"TX {tx_mbps:.1f} Mbps ({tx_percent:.1f}%)"
                ), perfdata
            elif max_percent >= warn:
                return WARNING, (
                    f"Bandwidth: RX {rx_mbps:.1f} Mbps ({rx_percent:.1f}%), "
                    f"TX {tx_mbps:.1f} Mbps ({tx_percent:.1f}%)"
                ), perfdata

        message = f"Bandwidth: RX {rx_mbps:.1f} Mbps, TX {tx_mbps:.1f} Mbps"
        return OK, message, perfdata

    except Exception as e:
        return UNKNOWN, f"Error checking bandwidth: {e}", ""


def main():
    parser = argparse.ArgumentParser(description="Bandwidth check for Nagios")
    parser.add_argument("--interface", required=True, help="Network interface name (e.g., eth0, ens192)")
    parser.add_argument("--interval", type=float, default=1.0, help="Measurement interval in seconds")
    parser.add_argument("--speed", type=int, default=None, help="Interface speed in Mbps (e.g., 1000, 10000)")
    parser.add_argument("--warn", type=float, default=80.0, help="Warning threshold (%)")
    parser.add_argument("--crit", type=float, default=95.0, help="Critical threshold (%)")
    args = parser.parse_args()

    exit_code, message, perfdata = check_bandwidth(
        args.interface, args.interval, args.warn, args.crit, args.speed
    )

    output = f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}"
    if perfdata:
        output += f" | {perfdata}"

    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
