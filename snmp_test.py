import socket, struct

HOST = '10.7.99.5'
PORT = 161

def build_getnext(community, oid_str):
    oid_parts = [int(x) for x in oid_str.split('.')]
    first_two = oid_parts[0] * 40 + oid_parts[1]
    oid_content = bytes([first_two]) + bytes(oid_parts[2:])
    oid_tag = bytes([0x06, len(oid_content)]) + oid_content
    request_id = bytes([0x02, 0x04]) + struct.pack('>I', 54321)
    error_status = bytes([0x02, 0x01, 0x00])
    error_index = bytes([0x02, 0x01, 0x00])
    varbind_content = oid_tag + bytes([0x05, 0x00])
    varbind = bytes([0x30, len(varbind_content)]) + varbind_content
    varbindlist = bytes([0x30, len(varbind)]) + varbind
    pdu_content = request_id + error_status + error_index + varbindlist
    pdu = bytes([0xa1, len(pdu_content)]) + pdu_content
    comm_bytes = community.encode()
    comm_tag = bytes([0x04, len(comm_bytes)]) + comm_bytes
    version = bytes([0x02, 0x01, 0x01])
    msg_content = version + comm_tag + pdu
    return bytes([0x30, len(msg_content)]) + msg_content

for community in ['public', 'LibreNms', 'private', 'cisco', 'monitor']:
    msg = build_getnext(community, '1.3.6.1.2.1.1.1.0')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)
    try:
        sock.sendto(msg, (HOST, PORT))
        data, addr = sock.recvfrom(65535)
        print(f'Community "{community}": Got {len(data)} bytes response')
    except socket.timeout:
        print(f'Community "{community}": Timeout')
    except Exception as e:
        print(f'Community "{community}": {e}')
    finally:
        sock.close()
