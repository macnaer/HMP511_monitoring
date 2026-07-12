import subprocess
import time
import os
import sys

PLINK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plink.exe")
HOST = "194.44.149.125"
PORT = 8759
USER = "demo"
PASS = "Qwerty-1"
INTERFACE = "Gi0/45"
INTERVAL = 30

def get_transceiver():
    cmd = f'echo y | "{PLINK}" -P {PORT} -pw {PASS} {USER}@{HOST} show interface {INTERFACE} transceiver detail'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return result.stdout

def get_interface():
    cmd = f'echo y | "{PLINK}" -P {PORT} -pw {PASS} {USER}@{HOST} show interface {INTERFACE}'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return result.stdout

def parse_transceiver(output):
    data = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Voltage" in line and "Volts" in line:
            continue
        if "Threshold" in line or "High Alarm" in line or "Low Alarm" in line:
            continue
        if "Port" in line and ("(Volts)" in line or "(Celsius)" in line or "(dBm)" in line):
            continue
        if "mA:" in line or "ITU Channel" in line or "Transceiver is" in line or "A2D readouts" in line or "The threshold" in line:
            continue
        if line.startswith("------") or line.startswith("---------"):
            continue

        parts = line.split()
        if not parts:
            continue

        if "Gi" in parts[0] and len(parts) >= 2:
            try:
                val = float(parts[1])
                if "Voltage" in line or "(Volts)" in output:
                    pass
            except ValueError:
                pass

    lines = output.splitlines()
    voltage = None
    temperature = None
    tx_power = None
    rx_power = None

    section = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "Temperature" in line and "Celsius" in line:
            section = "temp"
        elif "Voltage" in line and "Volts" in line:
            section = "voltage"
        elif "Transmit Power" in line and "dBm" in line:
            section = "tx"
        elif "Receive Power" in line and "dBm" in line:
            section = "rx"

        if stripped.startswith("Gi") and section:
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    val = float(parts[1])
                    if section == "temp":
                        temperature = val
                    elif section == "voltage":
                        voltage = val
                    elif section == "tx":
                        tx_power = val
                    elif section == "rx":
                        rx_power = val
                except ValueError:
                    pass
            section = None

    return voltage, temperature, tx_power, rx_power

def parse_interface(output):
    status = None
    for line in output.splitlines():
        if "GigabitEthernet" in line and "is" in line:
            status = line.strip()
            break
    return status

os.system('cls' if os.name == 'nt' else 'clear')

count = 0
while True:
    count += 1
    try:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        tx_out = get_transceiver()
        ifc_out = get_interface()

        voltage, temperature, tx_power, rx_power = parse_transceiver(tx_out)
        ifc_status = parse_interface(ifc_out)

        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"=== MONITORING {INTERFACE} | #{count} | {now} | every {INTERVAL}s ===")
        print()
        if ifc_status:
            print(f"  Interface: {ifc_status}")
        print()

        if voltage is not None:
            if voltage < 3.00:
                v_status = "!! LOW ALARM"
            elif voltage < 3.10:
                v_status = "! LOW WARN"
            elif voltage > 3.60:
                v_status = "!! HIGH ALARM"
            elif voltage > 3.50:
                v_status = "! HIGH WARN"
            else:
                v_status = "OK"
            print(f"  Voltage:     {voltage:.2f}V   [{v_status}]   (norm: 2.90-3.70V)")
        else:
            print(f"  Voltage:     N/A")

        if temperature is not None:
            if temperature > 80:
                t_status = "!! HIGH"
            elif temperature > 75:
                t_status = "! WARN"
            else:
                t_status = "OK"
            print(f"  Temperature: {temperature:.1f}C  [{t_status}]   (norm: -5.0-85.0C)")
        else:
            print(f"  Temperature: N/A")

        if tx_power is not None:
            print(f"  TX Power:    {tx_power:.1f} dBm (norm: -13.0 - 1.0 dBm)")
        else:
            print(f"  TX Power:    N/A")

        if rx_power is not None:
            print(f"  RX Power:    {rx_power:.1f} dBm (norm: -27.0 - 1.0 dBm)")
        else:
            print(f"  RX Power:    N/A")

        print()
        print(f"  Press Ctrl+C to stop. Next update in {INTERVAL}s...")

    except Exception as e:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"=== MONITORING {INTERFACE} | ERROR ===")
        print(f"  {e}")
        print(f"  Retrying in {INTERVAL}s...")

    time.sleep(INTERVAL)
