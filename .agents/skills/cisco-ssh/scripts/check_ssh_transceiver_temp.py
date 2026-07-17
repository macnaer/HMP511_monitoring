#!/usr/bin/env python3
"""
Nagios check for SFP transceiver temperature via SSH on Cisco switch.

Connects via SSH, runs 'show interfaces <interface> transceiver detail',
extracts temperature and its DDM thresholds (High/Low Alarm/Warning),
and alerts if the temperature exceeds any threshold.

Usage:
    check_ssh_transceiver_temp.py
    check_ssh_transceiver_temp.py --interface GigabitEthernet0/45
    check_ssh_transceiver_temp.py --host 10.7.99.5 --user demo --password XXX

Exit codes:
    0 = OK
    1 = WARNING
    2 = CRITICAL
    3 = UNKNOWN
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from read_env import load_env

OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def parse_transceiver_output(output: str) -> dict:
    data = {}

    in_temp = False
    for line in output.splitlines():
        stripped = line.strip().lower()
        if "temperature" in stripped and "threshold" in stripped:
            in_temp = True
            continue
        if not in_temp:
            continue
        if "voltage" in stripped and "threshold" in stripped:
            break
        if line.strip().startswith("---"):
            continue

        parts = line.strip().split()
        if len(parts) >= 6:
            try:
                data["temperature"] = float(parts[1])
                data["high_alarm"] = float(parts[2])
                data["high_warn"] = float(parts[3])
                data["low_warn"] = float(parts[4])
                data["low_alarm"] = float(parts[5])
                break
            except (ValueError, IndexError):
                continue

    return data


def run_ssh_command_via_sshpass(host, port, username, password, interface, timeout=15):
    cmd = (
        f"terminal length 0; show interfaces {interface} transceiver detail"
    )
    ssh_args = [
        "sshpass", "-p", password, "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-o", "KexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1,diffie-hellman-group-exchange-sha1",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-p", str(port),
        f"{username}@{host}",
        cmd,
    ]
    try:
        result = subprocess.run(
            ssh_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or f"sshpass exited with code {result.returncode}"
            return CRITICAL, f"SSH error: {err}"
        return OK, result.stdout
    except subprocess.TimeoutExpired:
        return CRITICAL, f"SSH timeout after {timeout}s"
    except FileNotFoundError:
        return CRITICAL, "sshpass not found"
    except Exception as e:
        return CRITICAL, f"SSH error: {type(e).__name__}: {e}"


def run_ssh_command_via_paramiko(host, port, username, password, interface, timeout=15):
    import paramiko

    try:
        import paramiko
        available = set(paramiko.Transport._preferred_kex)
        legacy = {"diffie-hellman-group14-sha1", "diffie-hellman-group-exchange-sha1",
                  "diffie-hellman-group1-sha1", "ecdh-sha2-nistp256",
                  "diffie-hellman-group14-sha256", "diffie-hellman-group-exchange-sha256",
                  "diffie-hellman-group16-sha512"}
        merged = list(dict.fromkeys([k for k in (list(legacy & available) + list(available))]))
        paramiko.Transport._preferred_kex = tuple(merged)
    except (ImportError, AttributeError):
        pass

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            host, port, username, password,
            timeout=timeout, allow_agent=False, look_for_keys=False,
        )
    except paramiko.AuthenticationException:
        return CRITICAL, "Authentication failed"
    except Exception as e:
        return CRITICAL, f"Connection error: {type(e).__name__}: {e}"

    try:
        shell = client.invoke_shell()
        time.sleep(2)
        if shell.recv_ready():
            shell.recv(65535)

        shell.send("terminal length 0\n")
        time.sleep(1)
        if shell.recv_ready():
            shell.recv(65535)

        cmd = f"show interfaces {interface} transceiver detail\n"
        shell.send(cmd)
        time.sleep(3)

        output = b""
        end_time = time.time() + timeout
        while time.time() < end_time:
            if shell.recv_ready():
                chunk = shell.recv(65535)
                output += chunk
            else:
                if output and (b"> " in output[-50:] or b"# " in output[-50:]):
                    break
                time.sleep(0.3)

        shell.close()
        client.close()

        text = output.decode("utf-8", errors="ignore")
        return OK, text
    except Exception as e:
        try:
            client.close()
        except Exception:
            pass
        return CRITICAL, f"Execution error: {type(e).__name__}: {e}"


def run_ssh_command(host, port, username, password, interface, timeout=15):
    if shutil.which("sshpass"):
        code, msg = run_ssh_command_via_sshpass(host, port, username, password, interface, timeout)
        if code == OK or code == CRITICAL:
            return code, msg
        return code, msg
    return run_ssh_command_via_paramiko(host, port, username, password, interface, timeout)


def check_temperature(host, port, username, password, interface, timeout):
    exit_code, raw = run_ssh_command(host, port, username, password, interface, timeout)
    if exit_code != OK:
        return exit_code, raw

    data = parse_transceiver_output(raw)

    if "temperature" not in data:
        return UNKNOWN, f"Cannot parse temperature for {interface}"

    temp = data["temperature"]
    high_alarm = data.get("high_alarm")
    high_warn = data.get("high_warn")
    low_warn = data.get("low_warn")
    low_alarm = data.get("low_alarm")

    thresholds_str = f"HighAlarm={high_alarm}, HighWarn={high_warn}, LowWarn={low_warn}, LowAlarm={low_alarm}"

    if high_alarm is not None and temp >= high_alarm:
        return CRITICAL, f"{interface} Temp: {temp}C >= {high_alarm}C (High Alarm) [{thresholds_str}]"
    if low_alarm is not None and temp <= low_alarm:
        return CRITICAL, f"{interface} Temp: {temp}C <= {low_alarm}C (Low Alarm) [{thresholds_str}]"
    if high_warn is not None and temp >= high_warn:
        return WARNING, f"{interface} Temp: {temp}C >= {high_warn}C (High Warn) [{thresholds_str}]"
    if low_warn is not None and temp <= low_warn:
        return WARNING, f"{interface} Temp: {temp}C <= {low_warn}C (Low Warn) [{thresholds_str}]"

    return OK, f"{interface} Temp: {temp}C [{thresholds_str}]"


def main():
    parser = argparse.ArgumentParser(description="SFP transceiver temperature check for Nagios (SSH)")
    parser.add_argument("--interface", default="GigabitEthernet0/45",
                        help="Interface name (default: GigabitEthernet0/45)")
    parser.add_argument("--host", help="Device IP (overrides env/ .env)")
    parser.add_argument("--port", type=int, default=None, help="SSH port (overrides env/ .env)")
    parser.add_argument("--user", help="SSH username (overrides env/ .env)")
    parser.add_argument("--password", help="SSH password (overrides env/ .env)")
    parser.add_argument("--timeout", type=int, default=15, help="Connection/command timeout")
    args = parser.parse_args()

    # Credentials priority: CLI args > env vars > .env file
    env_host = os.environ.get("SSH_HOST") or os.environ.get("INTERNAL_IP")
    env_port = os.environ.get("SSH_PORT") or os.environ.get("INTERNAL_PORT")
    env_user = os.environ.get("SSH_USER") or os.environ.get("USERNAME") or os.environ.get("USRERNAME")
    env_pass = os.environ.get("SSH_PASSWORD") or os.environ.get("PASSWORD")

    creds = {}
    if env_user and env_pass:
        creds["host"] = env_host
        creds["port"] = int(env_port) if env_port else 22
        creds["username"] = env_user
        creds["password"] = env_pass
    else:
        creds = load_env()

    host = args.host or creds.get("host") or creds.get("internal_ip")
    port = args.port or creds.get("port") or creds.get("internal_port", 22)
    username = args.user or creds.get("username")
    password = args.password or creds.get("password")

    if not username or not password:
        print("UNKNOWN - SSH credentials not found. Set SSH_USER/SSH_PASSWORD env vars, --user/--password flags, or .env file.")
        sys.exit(UNKNOWN)

    if not host:
        print("UNKNOWN - Host not specified. Use --host, SSH_HOST env var, or INTERNAL_IP in .env")
        sys.exit(UNKNOWN)

    exit_code, message = check_temperature(host, port, username, password, args.interface, args.timeout)

    perfdata = ""
    if exit_code == OK or exit_code == WARNING or exit_code == CRITICAL:
        try:
            temp_val = re.search(r"Temp:\s*([\d.-]+)", message)
            if temp_val:
                t = temp_val.group(1)
                perfdata = f" | temp={t}"
        except Exception:
            pass

    labels = {0: "OK", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}
    print(f"{labels[exit_code]} - {message}{perfdata}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
