#!/usr/bin/env python3
# /// script
# dependencies = [
#   "psutil>=5.9.0",
# ]
# ///
"""
Network interface status check for Nagios.

Usage:
    check_interface_status.py --interface eth0

Exit codes:
    0 = OK (interface is up)
    2 = CRITICAL (interface is down)
    3 = UNKNOWN (interface not found or error)
"""

import argparse
import sys
import os
import psutil


# Nagios exit codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def check_interface_status(interface: str) -> tuple[int, str]:
    """Check if a network interface is up or down."""
    try:
        # Get all interface stats
        stats = psutil.net_if_stats()

        if interface not in stats:
            # List available interfaces for error message
            available = ", ".join(stats.keys()) if stats else "none"
            return UNKNOWN, f"Interface not found: {interface} (available: {available})"

        iface = stats[interface]

        if iface.isup:
            speed = iface.speed if iface.speed > 0 else "unknown"
            duplex = iface.duplex.name if hasattr(iface.duplex, 'name') else str(iface.duplex)
            return OK, f"Interface {interface} is UP (speed: {speed} Mbps, duplex: {duplex})"
        else:
            return CRITICAL, f"Interface {interface} is DOWN"

    except Exception as e:
        return UNKNOWN, f"Error checking interface: {e}"


def check_interface_stats(interface: str) -> tuple[int, str, dict]:
    """Check interface and return stats."""
    try:
        stats = psutil.net_if_stats()
        counters = psutil.net_io_counters(pernic=True)

        if interface not in stats:
            return UNKNOWN, f"Interface not found: {interface}", {}

        iface = stats[interface]
        io = counters.get(interface)

        result = {
            "isup": iface.isup,
            "speed": iface.speed,
            "mtu": iface.mtu,
        }

        if io:
            result.update({
                "bytes_recv": io.bytes_recv,
                "bytes_sent": io.bytes_sent,
                "packets_recv": io.packets_recv,
                "packets_sent": io.packets_sent,
                "errin": io.errin,
                "errout": io.errout,
                "dropin": io.dropin,
                "dropout": io.dropout,
            })

        return OK, "OK", result

    except Exception as e:
        return UNKNOWN, f"Error: {e}", {}


def main():
    parser = argparse.ArgumentParser(description="Interface status check for Nagios")
    parser.add_argument("--interface", required=True, help="Network interface name (e.g., eth0, ens192)")
    parser.add_argument("--list", action="store_true", help="List all available interfaces")
    args = parser.parse_args()

    if args.list:
        stats = psutil.net_if_stats()
        print("Available interfaces:")
        for name, iface in stats.items():
            status = "UP" if iface.isup else "DOWN"
            print(f"  {name}: {status} (speed: {iface.speed} Mbps, mtu: {iface.mtu})")
        sys.exit(OK)

    exit_code, message = check_interface_status(args.interface)
    print(f"{['OK', 'WARNING', 'CRITICAL', 'UNKNOWN'][exit_code]} - {message}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
