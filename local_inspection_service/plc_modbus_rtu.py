"""Bounded XD5 Modbus RTU adapter. No serial access or physical retries."""
from .plc_fx_ascii import PlcConfigError

PROFILE = "xinje_xd5_modbus_rtu"
PROTOCOL = "modbus_rtu"
UNIT = 1

def crc16(data: bytes) -> int:
    crc = 0xffff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xa001 if crc & 1 else 0)
    return crc

def frame(payload: bytes) -> bytes:
    return payload + crc16(payload).to_bytes(2, "little")

def read_word(address: int) -> bytes:
    if not 0 <= address <= 255:
        raise PlcConfigError("unsupported Modbus address")
    return frame(bytes([UNIT, 3]) + address.to_bytes(2, "big") + b"\x00\x01")

def write_word(address: int, value: int) -> bytes:
    if not 0 <= address <= 255 or not 0 <= value <= 65535:
        raise PlcConfigError("unsupported Modbus word")
    return frame(bytes([UNIT, 6]) + address.to_bytes(2, "big") + value.to_bytes(2, "big"))

def parse_word(response: bytes) -> int:
    if len(response) != 7 or response[:3] != bytes([UNIT, 3, 2]):
        raise PlcConfigError("invalid Modbus read response")
    if crc16(response[:-2]) != int.from_bytes(response[-2:], "little"):
        raise PlcConfigError("invalid Modbus CRC")
    return int.from_bytes(response[3:5], "big")

def validate_write(response: bytes, request: bytes) -> bool:
    return len(request) == 8 and request[:2] == bytes([UNIT, 6]) and response == request and crc16(response[:-2]) == int.from_bytes(response[-2:], "little")
