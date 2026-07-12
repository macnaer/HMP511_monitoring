import socket
import struct

HOST = "10.7.99.5"
PORT = 161
COMMUNITY = "public"

def build_snmp_get_request(community, oid_str):
    oid_parts = [int(x) for x in oid_str.split('.')]
    oid_bytes = bytes([0x06, len(oid_parts) + (1 if oid_parts[0] >= 40 else 0)])
    oid_payload = bytes(oid_parts[:2])
    if oid_parts[0] >= 40:
        oid_payload = bytes([oid_parts[0] * 40 + oid_parts[1]]) + bytes(oid_parts[2:])
    else:
        oid_payload = bytes([oid_parts[0] * 40 + oid_parts[1]]) + bytes(oid_parts[1:])
        oid_parts_full = oid_parts
    
    # Build OID bytes properly
    full_oid = oid_parts
    first_two = full_oid[0] * 40 + full_oid[1]
    oid_content = bytes([first_two]) + bytes(full_oid[2:])
    
    # Length of OID content
    oid_tag = bytes([0x06, len(oid_content)]) + oid_content
    
    # GetRequest PDU: request-id(1), error-status(0), error-index(0), varbind
    request_id = bytes([0x02, 0x04]) + struct.pack('>I', 12345)
    error_status = bytes([0x02, 0x01, 0x00])
    error_index = bytes([0x02, 0x01, 0x00])
    
    # VarBind: SEQUENCE { OID, NULL }
    varbind_content = oid_tag + bytes([0x05, 0x00])
    varbind = bytes([0x30, len(varbind_content)]) + varbind_content
    
    # VarBindList
    varbindlist = bytes([0x30, len(varbind)]) + varbind
    
    # PDU
    pdu_content = request_id + error_status + error_index + varbindlist
    pdu = bytes([0xa0, len(pdu_content)]) + pdu_content
    
    # Community
    comm_bytes = community.encode()
    comm_tag = bytes([0x04, len(comm_bytes)]) + comm_bytes
    
    # Version
    version = bytes([0x02, 0x01, 0x01])  # SNMPv2c
    
    # SEQUENCE
    msg_content = version + comm_tag + pdu
    msg = bytes([0x30, len(msg_content)]) + msg_content
    
    return msg

def build_snmp_getnext_request(community, oid_str):
    oid_parts = [int(x) for x in oid_str.split('.')]
    first_two = oid_parts[0] * 40 + oid_parts[1]
    oid_content = bytes([first_two]) + bytes(oid_parts[2:])
    oid_tag = bytes([0x06, len(oid_content)]) + oid_content
    
    request_id = bytes([0x02, 0x04]) + struct.pack('>I', 12345)
    error_status = bytes([0x02, 0x01, 0x00])
    error_index = bytes([0x02, 0x01, 0x00])
    
    varbind_content = oid_tag + bytes([0x05, 0x00])
    varbind = bytes([0x30, len(varbind_content)]) + varbind_content
    varbindlist = bytes([0x30, len(varbind)]) + varbind
    
    pdu_content = request_id + error_status + error_index + varbindlist
    pdu = bytes([0xa1, len(pdu_content)]) + pdu_content  # GetNextRequest = 0xa1
    
    comm_bytes = community.encode()
    comm_tag = bytes([0x04, len(comm_bytes)]) + comm_bytes
    version = bytes([0x02, 0x01, 0x01])
    
    msg_content = version + comm_tag + pdu
    msg = bytes([0x30, len(msg_content)]) + msg_content
    return msg

def parse_oid(data, offset):
    length = data[offset]
    offset += 1
    oid_bytes = data[offset:offset+length]
    offset += length
    
    first_byte = oid_bytes[0]
    first = first_byte // 40
    second = first_byte - first * 40
    parts = [first, second]
    i = 1
    while i < len(oid_bytes):
        part = 0
        while True:
            b = oid_bytes[i]
            part = (part << 7) | (b & 0x7f)
            i += 1
            if not (b & 0x80):
                break
        parts.append(part)
    
    return '.'.join(str(p) for p in parts), offset

def parse_value(data, offset):
    tag = data[offset]
    offset += 1
    length = data[offset]
    offset += 1
    
    if tag == 0x02:  # Integer
        val = int.from_bytes(data[offset:offset+length], 'big', signed=True)
        return val, offset + length
    elif tag == 0x04:  # OctetString
        val = data[offset:offset+length].decode('ascii', errors='replace')
        return val, offset + length
    elif tag == 0x05:  # NULL
        return None, offset
    elif tag == 0x06:  # OID
        oid_str, new_offset = parse_oid(data, offset - 2)
        return oid_str, new_offset
    elif tag == 0x40:  # IpAddress
        val = '%d.%d.%d.%d' % tuple(data[offset:offset+4])
        return val, offset + length
    elif tag == 0x41:  # Counter32
        val = int.from_bytes(data[offset:offset+length], 'big')
        return val, offset + length
    elif tag == 0x42:  # Gauge32 / TimeTicks
        val = int.from_bytes(data[offset:offset+length], 'big')
        return val, offset + length
    elif tag == 0x43:  # TimeTicks
        val = int.from_bytes(data[offset:offset+length], 'big')
        return f"{val} ({val//360000}h {(val%360000)//6000}m {((val%6000)//100)}s)"
    else:
        return f"tag=0x{tag:02x} len={length} hex={data[offset:offset+length].hex()}", offset + length

def parse_snmp_response(data):
    offset = 0
    # outer SEQUENCE
    if data[offset] != 0x30:
        return None
    offset += 2  # skip tag + length
    
    # version
    offset += 1  # tag
    ver_len = data[offset]
    offset += 1
    version = int.from_bytes(data[offset:offset+ver_len], 'big')
    offset += ver_len
    
    # community
    offset += 1  # tag
    comm_len = data[offset]
    offset += 1
    community = data[offset:offset+comm_len].decode()
    offset += comm_len
    
    # PDU tag
    pdu_tag = data[offset]
    offset += 1
    pdu_len = data[offset]
    offset += 1
    
    # request-id
    offset += 2  # tag + length
    req_id = int.from_bytes(data[offset:offset+4], 'big')
    offset += 4
    
    # error-status
    offset += 2
    error_status = data[offset]
    offset += 1
    
    # error-index
    offset += 2
    error_index = data[offset]
    offset += 1
    
    # varbind list
    offset += 2  # SEQUENCE tag + length
    
    results = []
    while offset < len(data):
        if data[offset] == 0x30:  # varbind SEQUENCE
            vb_len = data[offset+1]
            offset += 2
            oid_str, offset = parse_oid(data, offset)
            val, offset = parse_value(data, offset)
            results.append((oid_str, val))
        else:
            break
    
    return {'version': version, 'community': community, 'error_status': error_status, 'results': results}

def snmp_get(oid_str):
    msg = build_snmp_get_request(COMMUNITY, oid_str)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    try:
        sock.sendto(msg, (HOST, PORT))
        data, addr = sock.recvfrom(65535)
        return parse_snmp_response(data)
    except socket.timeout:
        return None
    finally:
        sock.close()

def snmp_getnext(oid_str):
    msg = build_snmp_getnext_request(COMMUNITY, oid_str)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    try:
        sock.sendto(msg, (HOST, PORT))
        data, addr = sock.recvfrom(65535)
        return parse_snmp_response(data)
    except socket.timeout:
        return None
    finally:
        sock.close()

def snmp_walk(base_oid):
    results = []
    current_oid = base_oid
    for _ in range(100):
        resp = snmp_getnext(current_oid)
        if not resp or resp['error_status'] != 0 or not resp['results']:
            break
        oid_str, val = resp['results'][0]
        if not oid_str.startswith(base_oid.rstrip('.')):
            break
        results.append((oid_str, val))
        current_oid = oid_str
    return results

print("=== sysDescr ===")
resp = snmp_get("1.3.6.1.2.1.1.1.0")
if resp:
    for oid, val in resp['results']:
        print(f"  {oid} = {val}")
else:
    print("  No response")

print("\n=== CISCO-SFP-MONITOR-MIB Walk (1.3.6.1.4.1.9.9.91) ===")
results = snmp_walk("1.3.6.1.4.1.9.9.91")
for oid, val in results:
    print(f"  {oid} = {val}")
if not results:
    print("  No data")

print("\n=== ENTITY-SENSOR-MIB (1.3.6.1.4.1.9.9.91.1.1.1.1) ===")
results = snmp_walk("1.3.6.1.4.1.9.9.91.1.1.1.1")
for oid, val in results:
    print(f"  {oid} = {val}")
if not results:
    print("  No data")

print("\n=== entPhysicalTable names (1.3.6.1.2.1.47.1.1.1.1.2) ===")
results = snmp_walk("1.3.6.1.2.1.47.1.1.1.1.2")
for oid, val in results:
    print(f"  {oid} = {val}")
if not results:
    print("  No data")

print("\n=== ifTable (1.3.6.1.2.1.2.2.1.2) ===")
results = snmp_walk("1.3.6.1.2.1.2.2.1.2")
for oid, val in results:
    print(f"  {oid} = {val}")
if not results:
    print("  No data")
