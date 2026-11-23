"""Authenticate a connected loopback peer using Windows TCP process ownership."""
import ctypes
import os
import socket
import struct


class TcpRow(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
                ("state", "local_address", "local_port", "remote_address", "remote_port", "pid")]


def peer_is_owned(connection, expected_pid):
    if os.name != "nt":
        raise OSError("TCP peer ownership requires Windows.")
    local_address, local_port = connection.getsockname()[:2]
    remote_address, remote_port = connection.getpeername()[:2]
    library = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = library.GetExtendedTcpTable
    get_table.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int,
                          ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    get_table.restype = ctypes.c_uint32
    size = ctypes.c_uint32()
    code = get_table(None, ctypes.byref(size), False, socket.AF_INET, 5, 0)
    if code not in (0, 122) or size.value > 16 * 1024 * 1024:
        raise OSError("Cannot inspect the local model connection.")
    for _ in range(3):
        buffer = ctypes.create_string_buffer(size.value)
        code = get_table(buffer, ctypes.byref(size), False, socket.AF_INET, 5, 0)
        if code == 122 and size.value <= 16 * 1024 * 1024:
            continue
        if code:
            raise OSError("Cannot verify local model process ownership.")
        count = ctypes.c_uint32.from_buffer(buffer).value
        if 4 + count * ctypes.sizeof(TcpRow) > len(buffer):
            raise OSError("Invalid Windows TCP ownership table.")
        for index in range(count):
            row = TcpRow.from_buffer(buffer, 4 + index * ctypes.sizeof(TcpRow))
            if (row.pid == expected_pid and socket.ntohs(row.local_port & 0xFFFF) == remote_port
                    and socket.ntohs(row.remote_port & 0xFFFF) == local_port
                    and socket.inet_ntoa(struct.pack("<I", row.local_address)) == remote_address
                    and socket.inet_ntoa(struct.pack("<I", row.remote_address)) == local_address):
                return True
        return False
    raise OSError("Windows TCP ownership table changed during verification.")
