#!/usr/bin/env python3
"""
Cisco transceiver check for Nagios via SSH.

Monitors SFP transceiver metrics by parsing CLI output:
  show interfaces <iface> transceiver detail

Metrics: temperature, voltage, TX power, RX power (with device thresholds).

Usage:
    check_snmp_cisco_transceiver.py --host HOST --interface INTERFACE \\
        --ssh-user USER --ssh-pass PASS [--warn-temp ...] [--crit-temp ...]

Exit codes: 0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN
"""

import argparse
import os
import re
import sys
import time

try:
    import paramiko
except ImportError:
    print("UNKNOWN - paramiko not installed. pip install paramiko")
    sys.exit(3)


OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def none_or_float(val):
    if val is None or isinstance(val, str) and val.lower() in ("none", ""):
        return None
    return float(val)


def ssh_exec(host, port, user, password, command, timeout=15):
    """Run a command on a remote Cisco device via paramiko."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        transport = paramiko.Transport((host, port))
        transport.connect(username=user, password=password)
        client._transport = transport

        shell = client.invoke_shell()
        time.sleep(1)
        if shell.recv_ready():
            shell.recv(65535)

        shell.send("terminal length 0\n")
        time.sleep(1)
        if shell.recv_ready():
            shell.recv(65535)

        shell.send(command + "\n")
        time.sleep(3)

        output = b""
        end_time = time.time() + timeout
        while time.time() < end_time:
            if shell.recv_ready():
                output += shell.recv(65535)
            elif output:
                tail = output[-100:]
                if (b"# " in tail or b"#\r" in tail or
                    b"> " in tail or b">\r" in tail or
                    tail.endswith(b">") or tail.endswith(b"#")):
                    break
            time.sleep(0.3)

        shell.close()
        client.close()
        return 0, output.decode("utf-8", errors="ignore").strip(), ""

    except paramiko.AuthenticationException:
        return -1, "", "Authentication failed"
    except Exception as e:
        return -1, "", "%s: %s" % (type(e).__name__, str(e))


def parse_transceiver_output(output, interface):
    """Parse 'show interfaces <iface> transceiver detail' output.

    Returns dict: {metric_name: {value, high_alarm, high_warn, low_warn, low_alarm}}
    """
    results = {}
    lines = output.splitlines()

    metric_pattern = re.compile(
        r"^\s*(\S+)\s+"
        r"([\-\d.]+)\s+"
        r"([\-\d.]+)\s+"
        r"([\-\d.]+)\s+"
        r"([\-\d.]+)\s+"
        r"([\-\d.]+)\s*$"
    )

    current_metric = None
    for line in lines:
        line_lower = line.lower().strip()

        # Detect metric from keyword on its own line
        if "temperature" in line_lower and "celsius" not in line_lower:
            current_metric = "temperature"
            continue
        elif "voltage" in line_lower and "volts" not in line_lower:
            current_metric = "voltage"
            continue
        elif "transmit power" in line_lower:
            current_metric = "tx_power"
            continue
        elif "receive power" in line_lower:
            current_metric = "rx_power"
            continue

        if current_metric is None:
            continue

        m = metric_pattern.match(line)
        if m:
            port = m.group(1)
            # Skip separator lines (all dashes)
            if port.startswith("-") or not any(c.isdigit() for c in m.group(2)):
                continue
            iface_short = re.sub(r"[^A-Za-z0-9/]", "", interface)
            # Match: Gi0/45 matches GigabitEthernet0/45
            # Build short form from interface: GigabitEthernet0/45 -> Gi0/45
            m2 = re.match(r"^(GigabitEthernet|FastEthernet|TenGigabit|Serial|Ethernet)(\d+/\d+)$", interface, re.IGNORECASE)
            iface_short2 = ""
            if m2:
                prefix_map = {"gigabitethernet": "Gi", "fastethernet": "Fa", "tengigabitethernet": "Te", "serial": "Se", "ethernet": "Et"}
                iface_short2 = prefix_map.get(m2.group(1).lower(), m2.group(1)[:2]) + m2.group(2)
            if (port == iface_short or port == iface_short2 or
                    port in interface or interface.startswith(port)):
                try:
                    results[current_metric] = {
                        "value": float(m.group(2)),
                        "high_alarm": float(m.group(3)),
                        "high_warn": float(m.group(4)),
                        "low_warn": float(m.group(5)),
                        "low_alarm": float(m.group(6)),
                    }
                except ValueError:
                    pass
                current_metric = None

    return results


def check_transceiver(host, user, password, interface, ssh_port, timeout,
                      warn_temp, crit_temp, warn_volt, crit_volt,
                      warn_tx, crit_tx, warn_rx, crit_rx):
    rc, stdout, stderr = ssh_exec(
        host, ssh_port, user, password,
        "show interfaces %s transceiver detail" % interface,
        timeout=timeout,
    )

    if rc == -1:
        return UNKNOWN, "SSH error: %s" % stderr
    if not stdout:
        return UNKNOWN, "No output from switch"

    if "Diagnostic Monitoring is not implemented" in stdout:
        return UNKNOWN, "Transceiver diagnostic monitoring not supported on %s" % interface

    if "Temperature" not in stdout and "Voltage" not in stdout:
        return UNKNOWN, "No transceiver data found for %s" % interface

    data = parse_transceiver_output(stdout, interface)
    if not data:
        return UNKNOWN, "Cannot parse transceiver data for %s" % interface

    overall = OK
    parts = []
    perfdata = []

    # Temperature
    if "temperature" in data:
        t = data["temperature"]["value"]
        d = data["temperature"]
        parts.append("Temp: %.1fC" % t)
        perfdata.append("temp=%.1f;%.1f;%.1f;%.1f;%.1f" % (t, d["high_warn"], d["high_alarm"], d["low_warn"], d["low_alarm"]))
        if crit_temp is not None and t >= crit_temp:
            overall = max(overall, CRITICAL)
        elif warn_temp is not None and t >= warn_temp:
            overall = max(overall, WARNING)
        elif t >= d["high_alarm"]:
            overall = max(overall, CRITICAL)
        elif t >= d["high_warn"]:
            overall = max(overall, WARNING)

    # Voltage
    if "voltage" in data:
        v = data["voltage"]["value"]
        d = data["voltage"]
        parts.append("Volt: %.2fV" % v)
        perfdata.append("volt=%.2f;%.2f;%.2f;%.2f;%.2f" % (v, d["high_warn"], d["high_alarm"], d["low_warn"], d["low_alarm"]))
        if crit_volt is not None and v >= crit_volt:
            overall = max(overall, CRITICAL)
        elif warn_volt is not None and v >= warn_volt:
            overall = max(overall, WARNING)
        elif v >= d["high_alarm"]:
            overall = max(overall, CRITICAL)
        elif v >= d["high_warn"]:
            overall = max(overall, WARNING)

    # TX Power
    if "tx_power" in data:
        tx = data["tx_power"]["value"]
        d = data["tx_power"]
        parts.append("TX: %.1fdBm" % tx)
        perfdata.append("tx=%.1f;%.1f;%.1f;%.1f;%.1f" % (tx, d["high_warn"], d["high_alarm"], d["low_warn"], d["low_alarm"]))
        if crit_tx is not None and tx >= crit_tx:
            overall = max(overall, CRITICAL)
        elif warn_tx is not None and tx >= warn_tx:
            overall = max(overall, WARNING)
        elif tx >= d["high_alarm"]:
            overall = max(overall, CRITICAL)
        elif tx >= d["high_warn"]:
            overall = max(overall, WARNING)

    # RX Power
    if "rx_power" in data:
        rx = data["rx_power"]["value"]
        d = data["rx_power"]
        parts.append("RX: %.1fdBm" % rx)
        perfdata.append("rx=%.1f;%.1f;%.1f;%.1f;%.1f" % (rx, d["high_warn"], d["high_alarm"], d["low_warn"], d["low_alarm"]))
        if crit_rx is not None and rx >= crit_rx:
            overall = max(overall, CRITICAL)
        elif warn_rx is not None and rx >= warn_rx:
            overall = max(overall, WARNING)
        elif rx >= d["high_alarm"]:
            overall = max(overall, CRITICAL)
        elif rx >= d["high_warn"]:
            overall = max(overall, WARNING)

    if not parts:
        return UNKNOWN, "No readable metrics for %s" % interface

    labels = {0: "OK", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}
    message = ", ".join(parts)
    perf = " | " + " ".join(perfdata)
    return overall, "%s %s%s" % (interface, message, perf)


def main():
    parser = argparse.ArgumentParser(description="Cisco transceiver check for Nagios (SSH)")
    parser.add_argument("--host", required=True, help="Switch IP or hostname")
    parser.add_argument("--interface", required=True, help="Interface name (e.g., GigabitEthernet0/45)")
    parser.add_argument("--ssh-port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("--ssh-user", default=os.environ.get("NAGIOS_SSH_USER", "admin"),
                        help="SSH username")
    parser.add_argument("--ssh-pass", default=os.environ.get("NAGIOS_SSH_PASS", ""),
                        help="SSH password")
    parser.add_argument("--timeout", type=int, default=15, help="SSH timeout in seconds")
    parser.add_argument("--warn-temp", type=none_or_float, default=None, help="Temperature warning threshold")
    parser.add_argument("--crit-temp", type=none_or_float, default=None, help="Temperature critical threshold")
    parser.add_argument("--warn-volt", type=none_or_float, default=None, help="Voltage warning threshold")
    parser.add_argument("--crit-volt", type=none_or_float, default=None, help="Voltage critical threshold")
    parser.add_argument("--warn-tx", type=none_or_float, default=None, help="TX power warning threshold (dBm)")
    parser.add_argument("--crit-tx", type=none_or_float, default=None, help="TX power critical threshold (dBm)")
    parser.add_argument("--warn-rx", type=none_or_float, default=None, help="RX power warning threshold (dBm)")
    parser.add_argument("--crit-rx", type=none_or_float, default=None, help="RX power critical threshold (dBm)")
    args = parser.parse_args()

    try:
        exit_code, message = check_transceiver(
            host=args.host, user=args.ssh_user, password=args.ssh_pass,
            interface=args.interface, ssh_port=args.ssh_port, timeout=args.timeout,
            warn_temp=args.warn_temp, crit_temp=args.crit_temp,
            warn_volt=args.warn_volt, crit_volt=args.crit_volt,
            warn_tx=args.warn_tx, crit_tx=args.crit_tx,
            warn_rx=args.warn_rx, crit_rx=args.crit_rx,
        )
        labels = {0: "OK", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}
        print("%s - %s" % (labels[exit_code], message))
        sys.exit(exit_code)
    except Exception as e:
        print("UNKNOWN - Script error: %s" % str(e))
        sys.exit(UNKNOWN)


if __name__ == "__main__":
    main()
