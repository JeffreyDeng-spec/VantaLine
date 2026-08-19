from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


STX = b"\x02"
ETX = b"\x03"
ACK = b"\x06"
NAK = b"\x15"
PROTOCOL_ID = "fx_programming_port_ascii"
CHECKSUM_EXCLUDE_ETX_LEGACY_VB = "exclude_etx_legacy_vb"
CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT = "include_etx_documented_comment"
CHECKSUM_INCLUDE_ETX = "include_etx"
CHECKSUM_MODES = {
    CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
    CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT,
    CHECKSUM_INCLUDE_ETX,
}
MAX_DISPATCH_WALL_SECONDS = 60.0
PLC_CONFIG_ABSENT = object()


class PlcTerminalResultCode(str, Enum):
    """Exhaustive terminal outcomes for an attempt that reached the typed start event."""

    ACKNOWLEDGED = "acknowledged"
    NAK = "nak"
    TIMEOUT = "timeout"
    SHORT_RESPONSE = "short_response"
    UNEXPECTED_RESPONSE = "unexpected_response"
    SHORT_WRITE = "short_write"
    WRITE_RESULT_UNKNOWN = "write_result_unknown"
    SERIAL_IO_FAILED = "serial_io_failed"
    FLUSH_FAILED = "flush_failed"
    SERIAL_OPEN_FAILED = "serial_open_failed"
    SERIAL_DEPENDENCY_MISSING = "serial_dependency_missing"
    INTERNAL_TRANSITION_ERROR = "internal_transition_error"


class PlcTransportPhase(str, Enum):
    OPEN = "open"
    WRITE = "write"
    FLUSH = "flush"
    READ = "read"
    RESPONSE = "response"
    INTERNAL = "internal"


PLC_TERMINAL_RESULT_CODES = frozenset(PlcTerminalResultCode)
PLC_TERMINAL_DIAGNOSTIC_SOURCES: dict[PlcTerminalResultCode, frozenset[str]] = {
    PlcTerminalResultCode.ACKNOWLEDGED: frozenset({"ack_byte"}),
    PlcTerminalResultCode.NAK: frozenset({"nak_byte"}),
    PlcTerminalResultCode.TIMEOUT: frozenset(
        {"empty_read", "read_timeout_exception", "write_timeout_exception", "flush_timeout_exception"}
    ),
    PlcTerminalResultCode.SHORT_RESPONSE: frozenset({"non_ack_control_byte"}),
    PlcTerminalResultCode.UNEXPECTED_RESPONSE: frozenset({"multi_byte_response"}),
    PlcTerminalResultCode.SHORT_WRITE: frozenset({"write_length_mismatch"}),
    PlcTerminalResultCode.WRITE_RESULT_UNKNOWN: frozenset(
        {"write_returned_none", "write_returned_invalid_type", "write_returned_out_of_range"}
    ),
    PlcTerminalResultCode.SERIAL_IO_FAILED: frozenset({"write_exception", "read_exception"}),
    PlcTerminalResultCode.FLUSH_FAILED: frozenset({"flush_exception"}),
    PlcTerminalResultCode.SERIAL_OPEN_FAILED: frozenset(
        {"serial_open_exception", "transport_factory_exception"}
    ),
    PlcTerminalResultCode.SERIAL_DEPENDENCY_MISSING: frozenset({"pyserial_import"}),
    PlcTerminalResultCode.INTERNAL_TRANSITION_ERROR: frozenset(
        {"unknown_client_terminal_code", "terminal_diagnostic_contract_violation"}
    ),
}
PLC_TERMINAL_ALLOWED_PHASES: dict[PlcTerminalResultCode, frozenset[PlcTransportPhase]] = {
    PlcTerminalResultCode.ACKNOWLEDGED: frozenset({PlcTransportPhase.RESPONSE}),
    PlcTerminalResultCode.NAK: frozenset({PlcTransportPhase.RESPONSE}),
    PlcTerminalResultCode.TIMEOUT: frozenset(
        {PlcTransportPhase.WRITE, PlcTransportPhase.FLUSH, PlcTransportPhase.READ}
    ),
    PlcTerminalResultCode.SHORT_RESPONSE: frozenset({PlcTransportPhase.RESPONSE}),
    PlcTerminalResultCode.UNEXPECTED_RESPONSE: frozenset({PlcTransportPhase.RESPONSE}),
    PlcTerminalResultCode.SHORT_WRITE: frozenset({PlcTransportPhase.WRITE}),
    PlcTerminalResultCode.WRITE_RESULT_UNKNOWN: frozenset({PlcTransportPhase.WRITE}),
    PlcTerminalResultCode.SERIAL_IO_FAILED: frozenset(
        {PlcTransportPhase.WRITE, PlcTransportPhase.READ}
    ),
    PlcTerminalResultCode.FLUSH_FAILED: frozenset({PlcTransportPhase.FLUSH}),
    PlcTerminalResultCode.SERIAL_OPEN_FAILED: frozenset({PlcTransportPhase.OPEN}),
    PlcTerminalResultCode.SERIAL_DEPENDENCY_MISSING: frozenset({PlcTransportPhase.OPEN}),
    PlcTerminalResultCode.INTERNAL_TRANSITION_ERROR: frozenset({PlcTransportPhase.INTERNAL}),
}
PLC_RETRYABLE_TERMINAL_RESULTS = frozenset(
    {
        (PlcTerminalResultCode.NAK, PlcTransportPhase.RESPONSE),
        (PlcTerminalResultCode.TIMEOUT, PlcTransportPhase.READ),
        (PlcTerminalResultCode.SHORT_RESPONSE, PlcTransportPhase.RESPONSE),
        (PlcTerminalResultCode.UNEXPECTED_RESPONSE, PlcTransportPhase.RESPONSE),
    }
)


def plc_terminal_result_is_retryable(code: Any, phase: Any) -> bool:
    try:
        canonical_code = code if isinstance(code, PlcTerminalResultCode) else PlcTerminalResultCode(code)
        canonical_phase = phase if isinstance(phase, PlcTransportPhase) else PlcTransportPhase(phase)
    except (TypeError, ValueError):
        return False
    return (canonical_code, canonical_phase) in PLC_RETRYABLE_TERMINAL_RESULTS


@dataclass(frozen=True)
class PlcAttemptTerminalResult:
    code: PlcTerminalResultCode
    phase: PlcTransportPhase
    bytes_written: int
    diagnostic_source: str

DEFAULT_PLC_CONFIG: dict[str, Any] = {
    "enabled": False,
    "protocol": PROTOCOL_ID,
    "checksum_mode": CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
    "serial_port": "",
    "baudrate": 9600,
    "parity": "E",
    "data_bits": 7,
    "stop_bits": 1,
    "result_register": "D206",
    "output_control_point": "Y04",
    "capture_trigger_enabled": False,
    "capture_input_register": "",
    "capture_trigger_value": 1,
    "timeout": 1.0,
    "retries": 1,
}

_WINDOWS_PORT_RE = re.compile(r"COM(?:[1-9]|[1-9][0-9]{1,2})", re.IGNORECASE)
_POSIX_PORT_RE = re.compile(
    r"/dev/(?:tty(?:S|USB|ACM)[0-9]{1,3}|serial/by-id/[A-Za-z0-9._:+-]{1,160})"
)
_HEX_ADDRESS_RE = re.compile(r"[0-9A-F]{4}")
_D_REGISTER_RE = re.compile(r"D(?:0|[1-9][0-9]{0,4})", re.IGNORECASE)
_Y_POINT_RE = re.compile(r"Y[0-7]+", re.IGNORECASE)
_BAUDRATES = {1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200}
_PARITIES = {"E", "O", "N"}
_DATA_BITS = {7, 8}
_STOP_BITS = {1, 2}


class PlcConfigError(ValueError):
    pass


def logical_device_address(device: str) -> str:
    """Translate a PLC-programmer device name into the FX protocol word address."""
    text = str(device or "").strip().upper()
    if _D_REGISTER_RE.fullmatch(text):
        protocol_address = 0x1000 + (int(text[1:], 10) * 2)
    elif _Y_POINT_RE.fullmatch(text):
        protocol_address = 0x0100 + (int(text[1:], 8) * 2)
    else:
        raise PlcConfigError("device must use a D decimal register or Y octal output-point name")
    if protocol_address > 0xFFFF:
        raise PlcConfigError("device address is outside the four-character FX protocol range")
    return f"{protocol_address:04X}"


def logical_force_y_address(device: str) -> str:
    """Translate an octal Y point to the byte-swapped FORCE 7/8 wire address.

    The FX force table maps Y0..Y177 to internal addresses 0x0500..0x057F.
    FORCE frames transmit the low address byte before the high address byte,
    so Y04 is internal 0x0504 and appears on the wire as ASCII ``0405``.
    """
    text = str(device or "").strip().upper()
    if not _Y_POINT_RE.fullmatch(text):
        raise PlcConfigError("force target must use an octal Y point name")
    point = int(text[1:], 8)
    if not 0 <= point <= 0x7F:
        raise PlcConfigError("force target must be Y0 through Y177")
    internal_address = 0x0500 + point
    return f"{internal_address & 0xFF:02X}{internal_address >> 8:02X}"


def canonical_logical_device(device: str) -> str:
    text = str(device or "").strip().upper()
    if _D_REGISTER_RE.fullmatch(text):
        canonical = f"D{int(text[1:], 10)}"
    elif _Y_POINT_RE.fullmatch(text):
        canonical = f"Y{int(text[1:], 8):02o}"
    else:
        raise PlcConfigError("device must use a D decimal register or Y octal output-point name")
    logical_device_address(canonical)
    return canonical


def legacy_protocol_address_to_device(address: Any, device_type: str) -> str:
    """Reverse a canonical legacy protocol address without guessing across device families."""
    text = _string_value(address, f"legacy {device_type} address").upper()
    if not _HEX_ADDRESS_RE.fullmatch(text):
        raise PlcConfigError(f"legacy {device_type} address must contain exactly four hexadecimal characters")
    value = int(text, 16)
    base = 0x1000 if device_type == "D" else 0x0100
    offset = value - base
    if offset < 0 or offset % 2:
        raise PlcConfigError(f"legacy {device_type} address cannot be converted safely")
    number = offset // 2
    device = f"D{number}" if device_type == "D" else f"Y{number:02o}"
    if logical_device_address(device) != text:
        raise PlcConfigError(f"legacy {device_type} address is not canonical")
    return device


class PlcTransportError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        attempts: int = 0,
        diagnostic_source: str = "",
        phase: PlcTransportPhase | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.attempts = attempts
        self.diagnostic_source = diagnostic_source
        self.phase = phase
        self.receipts: list[FrameReceipt] = []
        self.failed_target = ""
        self.operations: list[dict[str, Any]] = []


@dataclass(frozen=True)
class FrameReceipt:
    target: str
    frame_hex: str
    attempts: int


def _bool_value(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise PlcConfigError(f"{field} must be a boolean")


def _int_value(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlcConfigError(f"{field} must be an integer")
    return value


def _float_value(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlcConfigError(f"{field} must be a number")
    parsed = float(value)
    if not (float("-inf") < parsed < float("inf")):
        raise PlcConfigError(f"{field} must be finite")
    return parsed


def _string_value(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise PlcConfigError(f"{field} must be a string")
    return value.strip()


def normalize_config(raw: Any = PLC_CONFIG_ABSENT) -> dict[str, Any]:
    if raw is PLC_CONFIG_ABSENT:
        source: dict[str, Any] = {}
    elif not isinstance(raw, dict):
        raise PlcConfigError("plc namespace must be an object when present")
    else:
        source = raw
    allowed_fields = set(DEFAULT_PLC_CONFIG) | {"d206_address", "y04_address", "write_y04"}
    unexpected = set(source) - allowed_fields
    if unexpected:
        raise PlcConfigError(f"unknown PLC configuration fields: {', '.join(sorted(unexpected))}")
    legacy_address_fields = {"d206_address", "y04_address", "write_y04"}
    v2_address_fields = {
        "result_register",
        "output_control_point",
        "capture_trigger_enabled",
        "capture_input_register",
        "capture_trigger_value",
    }
    if set(source) & legacy_address_fields and set(source) & v2_address_fields:
        raise PlcConfigError("legacy and v2 PLC address fields cannot be mixed")
    if set(source) & legacy_address_fields and not legacy_address_fields.issubset(source):
        raise PlcConfigError("legacy PLC address migration requires d206_address, y04_address, and write_y04")
    config = {**DEFAULT_PLC_CONFIG, **{key: value for key, value in source.items() if key in DEFAULT_PLC_CONFIG}}

    enabled = _bool_value(config.get("enabled"), "enabled")
    protocol = _string_value(config.get("protocol"), "protocol")
    if protocol != PROTOCOL_ID:
        raise PlcConfigError(f"protocol must be {PROTOCOL_ID}")
    checksum_mode = _string_value(config.get("checksum_mode"), "checksum_mode")
    if checksum_mode not in CHECKSUM_MODES:
        raise PlcConfigError("checksum_mode is not allowed")

    serial_port = _string_value(config.get("serial_port"), "serial_port")
    if serial_port and not (_WINDOWS_PORT_RE.fullmatch(serial_port) or _POSIX_PORT_RE.fullmatch(serial_port)):
        raise PlcConfigError("serial_port is not in the allowed COM or /dev serial-port format")
    if enabled and not serial_port:
        raise PlcConfigError("serial_port is required when PLC synchronization is enabled")

    baudrate = _int_value(config.get("baudrate"), "baudrate")
    if baudrate not in _BAUDRATES:
        raise PlcConfigError("baudrate is not allowed")
    parity = _string_value(config.get("parity"), "parity").upper()
    if parity not in _PARITIES:
        raise PlcConfigError("parity must be E, O, or N")
    data_bits = _int_value(config.get("data_bits"), "data_bits")
    if data_bits not in _DATA_BITS:
        raise PlcConfigError("data_bits must be 7 or 8")
    stop_bits = _int_value(config.get("stop_bits"), "stop_bits")
    if stop_bits not in _STOP_BITS:
        raise PlcConfigError("stop_bits must be 1 or 2")

    result_register = _string_value(config.get("result_register"), "result_register").upper()
    if "d206_address" in source:
        result_register = legacy_protocol_address_to_device(source["d206_address"], "D")
    if not _D_REGISTER_RE.fullmatch(result_register):
        raise PlcConfigError("result_register must use a D decimal register name such as D206")
    result_register = canonical_logical_device(result_register)

    output_control_point = _string_value(config.get("output_control_point"), "output_control_point").upper()
    if "write_y04" in source:
        legacy_write_output = _bool_value(source["write_y04"], "write_y04")
        if legacy_write_output:
            output_control_point = legacy_protocol_address_to_device(source["y04_address"], "Y")
        else:
            output_control_point = ""
    elif "y04_address" in source:
        output_control_point = legacy_protocol_address_to_device(source["y04_address"], "Y")
    if output_control_point:
        if not _Y_POINT_RE.fullmatch(output_control_point):
            raise PlcConfigError("output_control_point must use a Y octal point name such as Y04, or be empty")
        output_control_point = canonical_logical_device(output_control_point)

    capture_trigger_enabled = _bool_value(config.get("capture_trigger_enabled"), "capture_trigger_enabled")
    capture_input_register = _string_value(config.get("capture_input_register"), "capture_input_register").upper()
    if capture_input_register:
        if not _D_REGISTER_RE.fullmatch(capture_input_register):
            raise PlcConfigError("capture_input_register must use a D decimal register name such as D210")
        capture_input_register = canonical_logical_device(capture_input_register)
    if capture_trigger_enabled and not capture_input_register:
        raise PlcConfigError("capture_input_register is required when PLC capture triggering is enabled")
    if capture_input_register and capture_input_register == result_register:
        raise PlcConfigError("capture_input_register must be different from result_register")
    capture_trigger_value = _int_value(config.get("capture_trigger_value"), "capture_trigger_value")
    if not 0 <= capture_trigger_value <= 0xFFFF:
        raise PlcConfigError("capture_trigger_value must be between 0 and 65535")

    timeout = _float_value(config.get("timeout"), "timeout")
    if not 0.1 <= timeout <= 10.0:
        raise PlcConfigError("timeout must be between 0.1 and 10 seconds")
    retries = _int_value(config.get("retries"), "retries")
    if not 0 <= retries <= 5:
        raise PlcConfigError("retries must be between 0 and 5")
    target_count = 2 if output_control_point else 1
    estimated_max_seconds = target_count * (retries + 1) * ((timeout * 2.0) + 0.25)
    if estimated_max_seconds > MAX_DISPATCH_WALL_SECONDS:
        raise PlcConfigError(
            f"timeout/retries/output_control_point combination exceeds the {int(MAX_DISPATCH_WALL_SECONDS)} second dispatch budget"
        )

    return {
        "enabled": enabled,
        "protocol": protocol,
        "checksum_mode": checksum_mode,
        "serial_port": serial_port,
        "baudrate": baudrate,
        "parity": parity,
        "data_bits": data_bits,
        "stop_bits": stop_bits,
        "result_register": result_register,
        "output_control_point": output_control_point,
        "capture_trigger_enabled": capture_trigger_enabled,
        "capture_input_register": capture_input_register,
        "capture_trigger_value": capture_trigger_value,
        "timeout": round(timeout, 3),
        "retries": retries,
    }


def checksum(payload_from_command_through_etx: bytes, mode: str = CHECKSUM_EXCLUDE_ETX_LEGACY_VB) -> bytes:
    if mode not in CHECKSUM_MODES:
        raise ValueError("checksum mode is not allowed")
    payload = payload_from_command_through_etx
    if mode == CHECKSUM_EXCLUDE_ETX_LEGACY_VB:
        if not payload.endswith(ETX):
            raise ValueError("legacy VB checksum payload must end with ETX")
        payload = payload[:-1]
    return f"{sum(payload) & 0xFF:02X}".encode("ascii")


def build_frame(
    command: str,
    address: str,
    data: str = "",
    checksum_mode: str = CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
) -> bytes:
    command_text = str(command).strip()
    address_text = str(address).strip().upper()
    data_text = str(data).strip().upper()
    if len(command_text) != 1 or not command_text.isascii():
        raise ValueError("command must be one ASCII character")
    if not _HEX_ADDRESS_RE.fullmatch(address_text):
        raise ValueError("address must contain exactly four hexadecimal characters")
    if data_text and not re.fullmatch(r"[0-9A-F]{4}", data_text):
        raise ValueError("data must contain exactly four hexadecimal characters")
    body = f"{command_text}{address_text}{data_text}".encode("ascii") + ETX
    return STX + body + checksum(body, checksum_mode)


def build_d206_frame(
    address: str,
    passed: bool,
    checksum_mode: str = CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
) -> bytes:
    return build_frame("1", address, "0001" if passed else "0000", checksum_mode)


def build_y04_frame(
    address: str,
    passed: bool,
    checksum_mode: str = CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
) -> bytes:
    return build_frame("7" if passed else "8", address, checksum_mode=checksum_mode)


def encode_fx_word(value: int) -> str:
    """Encode one unsigned FX word as low byte then high byte ASCII hex."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF:
        raise ValueError("FX word value must be an integer from 0 through 65535")
    return value.to_bytes(2, byteorder="little", signed=False).hex().upper()


def build_d_register_write_frame(
    address: str,
    value: int,
    checksum_mode: str = CHECKSUM_INCLUDE_ETX,
) -> bytes:
    """Build a documented one-word DEVICE WRITE frame.

    A one-word write carries the mandatory byte-count field ``02`` and two
    little-endian data bytes.  The documented checksum covers CMD through ETX.
    """
    if checksum_mode != CHECKSUM_INCLUDE_ETX:
        raise ValueError("documented DEVICE WRITE requires a checksum that includes ETX")
    address_text = str(address).strip().upper()
    if not _HEX_ADDRESS_RE.fullmatch(address_text):
        raise ValueError("address must contain exactly four hexadecimal characters")
    body = f"1{address_text}02{encode_fx_word(value)}".encode("ascii") + ETX
    return STX + body + checksum(body, checksum_mode)


def build_y_force_frame(
    device: str,
    turn_on: bool,
    checksum_mode: str = CHECKSUM_INCLUDE_ETX,
) -> bytes:
    """Build a FORCE ON/OFF frame using the FX force-bit address table."""
    if checksum_mode != CHECKSUM_INCLUDE_ETX:
        raise ValueError("documented FORCE requires a checksum that includes ETX")
    command = "7" if turn_on else "8"
    body = f"{command}{logical_force_y_address(device)}".encode("ascii") + ETX
    return STX + body + checksum(body, checksum_mode)


def build_d_register_read_frame(
    address: str,
    checksum_mode: str = CHECKSUM_INCLUDE_ETX,
) -> bytes:
    """Build a documented one-word DEVICE READ frame."""
    if checksum_mode != CHECKSUM_INCLUDE_ETX:
        raise ValueError("documented DEVICE READ requires a checksum that includes ETX")
    address_text = str(address).strip().upper()
    if not _HEX_ADDRESS_RE.fullmatch(address_text):
        raise ValueError("address must contain exactly four hexadecimal characters")
    body = f"0{address_text}02".encode("ascii") + ETX
    return STX + body + checksum(body, checksum_mode)


def parse_d_register_read_response(
    response: bytes,
    checksum_mode: str = CHECKSUM_INCLUDE_ETX,
) -> int:
    if checksum_mode != CHECKSUM_INCLUDE_ETX:
        raise ValueError("documented DEVICE READ response requires a checksum that includes ETX")
    if not isinstance(response, bytes) or len(response) != 8:
        raise PlcTransportError(
            PlcTerminalResultCode.SHORT_RESPONSE,
            "PLC D-register response must contain STX, four data characters, ETX and checksum",
            diagnostic_source="non_ack_control_byte",
            phase=PlcTransportPhase.RESPONSE,
        )
    if response[:1] != STX or response[5:6] != ETX:
        raise PlcTransportError(
            PlcTerminalResultCode.UNEXPECTED_RESPONSE,
            "PLC D-register response framing is invalid",
            diagnostic_source="multi_byte_response",
            phase=PlcTransportPhase.RESPONSE,
        )
    data = response[1:5]
    try:
        raw_word = bytes.fromhex(data.decode("ascii"))
        value = int.from_bytes(raw_word, byteorder="little", signed=False)
    except (UnicodeDecodeError, ValueError) as exc:
        raise PlcTransportError(
            PlcTerminalResultCode.UNEXPECTED_RESPONSE,
            "PLC D-register response data is not hexadecimal",
            diagnostic_source="multi_byte_response",
            phase=PlcTransportPhase.RESPONSE,
        ) from exc
    if response[6:8].upper() != checksum(data + ETX, checksum_mode):
        raise PlcTransportError(
            PlcTerminalResultCode.UNEXPECTED_RESPONSE,
            "PLC D-register response checksum is invalid",
            diagnostic_source="multi_byte_response",
            phase=PlcTransportPhase.RESPONSE,
        )
    return value


def read_d_register_value(
    config: dict[str, Any],
    register: str,
    transport_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> int:
    normalized = normalize_config(config)
    frame = build_d_register_read_frame(
        logical_device_address(register), normalized["checksum_mode"]
    )
    factory = transport_factory or open_pyserial_transport
    transport = None
    try:
        transport = factory(normalized)
        if hasattr(transport, "reset_input_buffer"):
            transport.reset_input_buffer()
        written = transport.write(frame)
        if isinstance(written, bool) or not isinstance(written, int) or written != len(frame):
            raise PlcTransportError(
                PlcTerminalResultCode.SHORT_WRITE,
                "PLC read request was not written completely",
                diagnostic_source="write_length_mismatch",
                phase=PlcTransportPhase.WRITE,
            )
        if hasattr(transport, "flush"):
            transport.flush()
        response = transport.read(8)
        if not response:
            raise PlcTransportError(
                PlcTerminalResultCode.TIMEOUT,
                "PLC D-register read timed out",
                diagnostic_source="empty_read",
                phase=PlcTransportPhase.READ,
            )
        return parse_d_register_read_response(bytes(response), normalized["checksum_mode"])
    finally:
        if transport is not None:
            _close_transport(transport)


def open_pyserial_transport(config: dict[str, Any]) -> Any:
    try:
        import serial  # type: ignore[import-not-found]
    except ImportError as exc:
        raise PlcTransportError(
            PlcTerminalResultCode.SERIAL_DEPENDENCY_MISSING,
            "pyserial is not installed",
            diagnostic_source="pyserial_import",
            phase=PlcTransportPhase.OPEN,
        ) from exc
    try:
        return serial.Serial(
            port=config["serial_port"],
            baudrate=config["baudrate"],
            parity={"E": serial.PARITY_EVEN, "O": serial.PARITY_ODD, "N": serial.PARITY_NONE}[config["parity"]],
            bytesize={7: serial.SEVENBITS, 8: serial.EIGHTBITS}[config["data_bits"]],
            stopbits={1: serial.STOPBITS_ONE, 2: serial.STOPBITS_TWO}[config["stop_bits"]],
            timeout=config["timeout"],
            write_timeout=config["timeout"],
        )
    except Exception as exc:
        raise PlcTransportError(
            PlcTerminalResultCode.SERIAL_OPEN_FAILED,
            "serial port could not be opened",
            diagnostic_source="serial_open_exception",
            phase=PlcTransportPhase.OPEN,
        ) from exc


def _close_transport(transport: Any) -> None:
    try:
        transport.close()
    except Exception:
        pass


def _send_once(
    target: str,
    frame: bytes,
    config: dict[str, Any],
    transport_factory: Callable[[dict[str, Any]], Any],
    on_write_started: Callable[[str, bytes], None] | None = None,
    on_write_result: Callable[[str, bytes, int | None], None] | None = None,
) -> None:
    transport = None
    try:
        transport = transport_factory(config)
    except PlcTransportError:
        raise
    except Exception as exc:
        raise PlcTransportError(
            PlcTerminalResultCode.SERIAL_OPEN_FAILED,
            "serial port could not be opened",
            diagnostic_source="transport_factory_exception",
            phase=PlcTransportPhase.OPEN,
        ) from exc
    try:
        if on_write_started:
            on_write_started(target, frame)
        try:
            written = transport.write(frame)
        except TimeoutError as exc:
            raise PlcTransportError(
                PlcTerminalResultCode.TIMEOUT,
                "PLC serial write timed out",
                diagnostic_source="write_timeout_exception",
                phase=PlcTransportPhase.WRITE,
            ) from exc
        except PlcTransportError:
            raise
        except Exception as exc:
            raise PlcTransportError(
                PlcTerminalResultCode.SERIAL_IO_FAILED,
                "serial transport write failed",
                diagnostic_source="write_exception",
                phase=PlcTransportPhase.WRITE,
            ) from exc
        if written is None:
            if on_write_result:
                on_write_result(target, frame, None)
            raise PlcTransportError(
                PlcTerminalResultCode.WRITE_RESULT_UNKNOWN,
                "serial transport did not report a write length",
                diagnostic_source="write_returned_none",
                phase=PlcTransportPhase.WRITE,
            )
        if isinstance(written, bool) or not isinstance(written, int):
            if on_write_result:
                on_write_result(target, frame, None)
            raise PlcTransportError(
                PlcTerminalResultCode.WRITE_RESULT_UNKNOWN,
                "serial transport returned a non-integer write length",
                diagnostic_source="write_returned_invalid_type",
                phase=PlcTransportPhase.WRITE,
            )
        if written < 0 or written > len(frame):
            if on_write_result:
                on_write_result(target, frame, None)
            raise PlcTransportError(
                PlcTerminalResultCode.WRITE_RESULT_UNKNOWN,
                "serial transport returned an out-of-range write length",
                diagnostic_source="write_returned_out_of_range",
                phase=PlcTransportPhase.WRITE,
            )
        written_count = written
        if on_write_result:
            on_write_result(target, frame, written_count)
        if written_count != len(frame):
            raise PlcTransportError(
                PlcTerminalResultCode.SHORT_WRITE,
                "serial transport accepted a partial frame",
                diagnostic_source="write_length_mismatch",
                phase=PlcTransportPhase.WRITE,
            )
        if hasattr(transport, "flush"):
            try:
                transport.flush()
            except TimeoutError as exc:
                raise PlcTransportError(
                    PlcTerminalResultCode.TIMEOUT,
                    "PLC serial flush timed out",
                    diagnostic_source="flush_timeout_exception",
                    phase=PlcTransportPhase.FLUSH,
                ) from exc
            except PlcTransportError:
                raise
            except Exception as exc:
                raise PlcTransportError(
                    PlcTerminalResultCode.FLUSH_FAILED,
                    "serial transport flush failed",
                    diagnostic_source="flush_exception",
                    phase=PlcTransportPhase.FLUSH,
                ) from exc
        try:
            response = transport.read(1)
        except TimeoutError as exc:
            raise PlcTransportError(
                PlcTerminalResultCode.TIMEOUT,
                "PLC response timed out",
                diagnostic_source="read_timeout_exception",
                phase=PlcTransportPhase.READ,
            ) from exc
        except PlcTransportError:
            raise
        except Exception as exc:
            raise PlcTransportError(
                PlcTerminalResultCode.SERIAL_IO_FAILED,
                "serial transport read failed",
                diagnostic_source="read_exception",
                phase=PlcTransportPhase.READ,
            ) from exc
    except PlcTransportError:
        raise
    finally:
        if transport is not None:
            _close_transport(transport)

    if response == ACK:
        return
    if response == NAK:
        raise PlcTransportError(
            PlcTerminalResultCode.NAK,
            "PLC returned NAK",
            diagnostic_source="nak_byte",
            phase=PlcTransportPhase.RESPONSE,
        )
    if not response:
        raise PlcTransportError(
            PlcTerminalResultCode.TIMEOUT,
            "PLC returned no response byte before the configured read timeout",
            diagnostic_source="empty_read",
            phase=PlcTransportPhase.READ,
        )
    if len(response) == 1:
        raise PlcTransportError(
            PlcTerminalResultCode.SHORT_RESPONSE,
            "PLC returned a non-empty byte that did not complete an ACK/NAK response",
            diagnostic_source="non_ack_control_byte",
            phase=PlcTransportPhase.RESPONSE,
        )
    raise PlcTransportError(
        PlcTerminalResultCode.UNEXPECTED_RESPONSE,
        "PLC returned an unexpected multi-byte response",
        diagnostic_source="multi_byte_response",
        phase=PlcTransportPhase.RESPONSE,
    )


class FxAsciiClient:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        transport_factory: Callable[[dict[str, Any]], Any] | None = None,
        on_write_started: Callable[[str, bytes], None] | None = None,
        on_write_result: Callable[[str, bytes, int | None], None] | None = None,
        before_attempt: Callable[[str, int], bool | str] | None = None,
        after_attempt: Callable[[str, int], None] | None = None,
        on_attempt_started: Callable[[str, int, bytes], dict[str, Any]] | None = None,
        on_attempt_finished: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = normalize_config(config)
        if not self.config["enabled"]:
            raise PlcConfigError("PLC client cannot be created while synchronization is disabled")
        self.transport_factory = transport_factory or open_pyserial_transport
        self.on_write_started = on_write_started
        self.on_write_result = on_write_result
        self.before_attempt = before_attempt
        self.after_attempt = after_attempt
        self.on_attempt_started = on_attempt_started
        self.on_attempt_finished = on_attempt_finished
        self.operations: list[dict[str, Any]] = []

    def send(self, target: str, frame: bytes) -> FrameReceipt:
        last_error: PlcTransportError | None = None
        max_attempts = self.config["retries"] + 1
        attempts_used = 0
        for attempt in range(1, max_attempts + 1):
            try:
                gate_result = self.before_attempt(target, attempt) if self.before_attempt else True
            except Exception as exc:
                control_error = PlcTransportError(
                    "control_state_check_failed",
                    "PLC control state could not be verified before a new physical attempt",
                    attempts=attempt - 1,
                    diagnostic_source="before_attempt_control_read",
                )
                control_error.operations = [dict(item) for item in self.operations]
                raise control_error from exc
            if gate_result is not True:
                cancel_code = str(gate_result) if isinstance(gate_result, str) and gate_result else "cancelled_after_disable"
                cancel_message = (
                    "PLC synchronization deadline expired before a new physical attempt"
                    if cancel_code == "deadline_exceeded"
                    else (
                        "PLC synchronization was cancelled before a new physical attempt because the physical I/O configuration changed"
                        if cancel_code == "cancelled_after_config_change"
                        else "PLC synchronization was cancelled before a new physical attempt because the configuration was disabled"
                    )
                )
                last_error = PlcTransportError(
                    cancel_code,
                    cancel_message,
                    attempts=attempt - 1,
                )
                break
            attempts_used = attempt
            operation = (
                dict(self.on_attempt_started(target, attempt, frame))
                if self.on_attempt_started
                else {
                    "attempt_id": f"{target}:{attempt}",
                    "target": target,
                    "attempt": attempt,
                    "frame_hex": frame.hex().upper(),
                    "frame_bytes": len(frame),
                    "bytes_written": 0,
                    "write_count_known": False,
                    "reported_write_count": None,
                    "physical_status": "not_attempted",
                    "outcome": "not_attempted",
                    "started_at": int(time.time()),
                }
            )
            self.operations.append(operation)

            def operation_write_started(callback_target: str, callback_frame: bytes) -> None:
                operation["physical_status"] = "write_call_started"
                operation["outcome"] = "write_outcome_uncertain"
                if self.on_write_started:
                    self.on_write_started(callback_target, callback_frame)

            def operation_write_result(
                callback_target: str, callback_frame: bytes, count: int | None
            ) -> None:
                if count is None:
                    operation["write_count_known"] = False
                    operation["reported_write_count"] = None
                    if self.on_write_result:
                        self.on_write_result(callback_target, callback_frame, None)
                    return
                operation["write_count_known"] = True
                operation["reported_write_count"] = count
                operation["bytes_written"] = count
                if count == len(callback_frame):
                    operation["physical_status"] = "full_frame_written"
                    operation["outcome"] = "awaiting_acknowledgement"
                elif count > 0:
                    operation["physical_status"] = "partial_write"
                    operation["outcome"] = "outcome_uncertain"
                else:
                    operation["physical_status"] = "not_written"
                    operation["outcome"] = "not_written"
                if self.on_write_result:
                    self.on_write_result(callback_target, callback_frame, count)

            try:
                _send_once(
                    target,
                    frame,
                    self.config,
                    self.transport_factory,
                    operation_write_started,
                    operation_write_result,
                )
                operation["physical_status"] = "acknowledged"
                operation["outcome"] = "acknowledged"
                operation["result_code"] = PlcTerminalResultCode.ACKNOWLEDGED
                operation["result_phase"] = PlcTransportPhase.RESPONSE.value
                operation["diagnostic_source"] = "ack_byte"
                operation["finished_at"] = int(time.time())
                return FrameReceipt(target=target, frame_hex=frame.hex().upper(), attempts=attempt)
            except PlcTransportError as exc:
                last_error = exc
                operation["result_code"] = exc.code
                operation["result_phase"] = exc.phase.value if isinstance(exc.phase, PlcTransportPhase) else ""
                operation["diagnostic_source"] = exc.diagnostic_source
                operation["finished_at"] = int(time.time())
                if exc.code == PlcTerminalResultCode.NAK:
                    operation["physical_status"] = "rejected"
                    operation["outcome"] = "rejected"
                elif int(operation.get("bytes_written") or 0) > 0:
                    operation["outcome"] = "outcome_uncertain"
                if not plc_terminal_result_is_retryable(exc.code, exc.phase):
                    break
            finally:
                if self.on_attempt_finished and operation.get("finished_at") is not None:
                    self.on_attempt_finished(dict(operation))
                if self.after_attempt:
                    self.after_attempt(target, attempt)
        assert last_error is not None
        error = PlcTransportError(
            last_error.code,
            str(last_error),
            attempts=attempts_used or last_error.attempts,
            diagnostic_source=last_error.diagnostic_source,
            phase=last_error.phase,
        )
        error.operations = [dict(item) for item in self.operations]
        raise error from last_error

    def sync_result(self, passed: bool) -> list[FrameReceipt]:
        checksum_mode = self.config["checksum_mode"]
        result_register = self.config["result_register"]
        output_control_point = self.config["output_control_point"]
        receipts: list[FrameReceipt] = []
        try:
            receipts.append(
                self.send(
                    result_register,
                    build_d206_frame(logical_device_address(result_register), passed, checksum_mode),
                )
            )
        except PlcTransportError as exc:
            exc.receipts = list(receipts)
            exc.failed_target = result_register
            raise
        if output_control_point:
            try:
                receipts.append(
                    self.send(
                        output_control_point,
                        build_y04_frame(logical_device_address(output_control_point), passed, checksum_mode),
                    )
                )
            except PlcTransportError as exc:
                exc.receipts = list(receipts)
                exc.failed_target = output_control_point
                raise
        return receipts


_dispatch_lock = threading.RLock()
_memory_dispatches: dict[str, dict[str, Any]] = {}
_MEMORY_DISPATCH_LIMIT = 200


def _remember_dispatch(dispatch_id: str, record: dict[str, Any]) -> None:
    _memory_dispatches[dispatch_id] = record
    while len(_memory_dispatches) > _MEMORY_DISPATCH_LIMIT:
        oldest = next(iter(_memory_dispatches))
        _memory_dispatches.pop(oldest, None)


def clear_memory_dispatches() -> None:
    with _dispatch_lock:
        _memory_dispatches.clear()


def dispatch_detection_result(
    *,
    dispatch_id: str,
    source: str,
    request_id: str,
    passed: bool,
    config: dict[str, Any] | None,
    transport_factory: Callable[[dict[str, Any]], Any] | None = None,
    load_existing: Callable[[str], dict[str, Any] | None] | None = None,
    persist: Callable[[dict[str, Any], str], None] | None = None,
    before_attempt: Callable[[str, int], bool | str] | None = None,
    after_attempt: Callable[[str, int], None] | None = None,
    on_attempt_started: Callable[[str, int, bytes], dict[str, Any]] | None = None,
    on_attempt_finished: Callable[[dict[str, Any]], None] | None = None,
    is_dispatch_active: Callable[[], bool] | None = None,
    dispatch_cancel_reason: Callable[[], str] | None = None,
    now: Callable[[], float] = time.time,
) -> dict[str, Any]:
    clean_dispatch_id = str(dispatch_id or "").strip()
    if not clean_dispatch_id:
        raise ValueError("dispatch_id is required")

    with _dispatch_lock:
        existing = load_existing(clean_dispatch_id) if load_existing else _memory_dispatches.get(clean_dispatch_id)
        if isinstance(existing, dict):
            return {**existing, "duplicate": True}

        def persist_safely(record: dict[str, Any], transition_kind: str = "record_update") -> bool:
            if not persist:
                return True
            try:
                persist(record, transition_kind)
                return True
            except Exception:
                return False

        try:
            normalized = normalize_config(config)
        except PlcConfigError as exc:
            record = {
                "dispatch_id": clean_dispatch_id,
                "source": str(source),
                "request_id": str(request_id),
                "passed": bool(passed),
                "enabled": False,
                "attempted": False,
                "status": "failed",
                "error_code": "invalid_config",
                "message": str(exc),
                "updated_at": int(now()),
            }
            _remember_dispatch(clean_dispatch_id, record)
            if not persist_safely(record):
                record = {**record, "audit_status": "persist_failed"}
                _remember_dispatch(clean_dispatch_id, record)
            return dict(record)

        base = {
            "record_schema_version": 1,
            "dispatch_id": clean_dispatch_id,
            "source": str(source),
            "request_id": str(request_id),
            "passed": bool(passed),
            "enabled": normalized["enabled"],
            "protocol": PROTOCOL_ID,
            "checksum_mode": normalized["checksum_mode"],
            "planned_targets": [
                normalized["result_register"],
                *([normalized["output_control_point"]] if normalized["output_control_point"] else []),
            ],
            "planned_frames": [
                {
                    "target": normalized["result_register"],
                    "frame_hex": build_d206_frame(
                        logical_device_address(normalized["result_register"]),
                        bool(passed),
                        normalized["checksum_mode"],
                    ).hex().upper(),
                },
                *(
                    [
                        {
                            "target": normalized["output_control_point"],
                            "frame_hex": build_y04_frame(
                                logical_device_address(normalized["output_control_point"]),
                                bool(passed),
                                normalized["checksum_mode"],
                            ).hex().upper(),
                        }
                    ]
                    if normalized["output_control_point"]
                    else []
                ),
            ],
            "attempted": False,
            "duplicate": False,
            "updated_at": int(now()),
        }
        if not normalized["enabled"]:
            record = {**base, "status": "disabled", "message": "PLC synchronization is disabled"}
            _remember_dispatch(clean_dispatch_id, record)
            return dict(record)

        def transition(status: str, **extra: Any) -> dict[str, Any]:
            previous = _memory_dispatches.get(clean_dispatch_id) or {}
            history = [dict(item) for item in previous.get("history", []) if isinstance(item, dict)]
            history_item: dict[str, Any] = {"status": status, "at": int(now())}
            if extra.get("target"):
                history_item["target"] = str(extra["target"])
            history.append(history_item)
            record = {**previous, **base, "status": status, "updated_at": int(now()), "history": history, **extra}
            _remember_dispatch(clean_dispatch_id, record)
            return record

        queued = transition("queued", message="PLC synchronization queued")
        if not persist_safely(queued):
            failed = transition(
                "failed",
                attempted=False,
                physical_status="not_attempted",
                audit_status="persist_failed",
                error_code="audit_persist_failed_before_io",
                message="PLC synchronization was not attempted because the queued audit record could not be persisted",
            )
            persist_safely(failed, "finalize")
            return dict(failed)

        attempting = transition(
            "attempting",
            attempted=False,
            physical_status="not_attempted",
            message="Preparing to open the configured serial port and write a PLC frame",
        )
        if not persist_safely(attempting, "dispatch_transition"):
            failed = transition(
                "failed",
                attempted=False,
                physical_status="not_attempted",
                audit_status="persist_failed",
                error_code="audit_persist_failed_before_io",
                message="PLC synchronization was not attempted because the pre-I/O audit record could not be persisted",
            )
            persist_safely(failed, "finalize")
            return dict(failed)

        audit_persist_failed_after_io = False
        target_states: dict[str, dict[str, Any]] = {}
        sent_targets: set[str] = set()
        client: FxAsciiClient | None = None

        def operations_snapshot(raw_operations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
            source_operations = raw_operations if raw_operations is not None else (client.operations if client else [])
            snapshots: list[dict[str, Any]] = []
            for item in source_operations:
                attempt_id = str(item.get("attempt_id") or "")
                snapshots.append(
                    {
                        **dict(item),
                        "attempt_id": (
                            attempt_id
                            if attempt_id.startswith(f"{clean_dispatch_id}:")
                            else f"{clean_dispatch_id}:{attempt_id}"
                        ),
                    }
                )
            return snapshots

        def update_current(**extra: Any) -> dict[str, Any]:
            previous = _memory_dispatches.get(clean_dispatch_id) or {}
            record = {**previous, "updated_at": int(now()), **extra}
            _remember_dispatch(clean_dispatch_id, record)
            return record

        def state_for(target: str, frame: bytes | None = None) -> dict[str, Any]:
            state = target_states.setdefault(
                target,
                {
                    "target": target,
                    "write_call_started": False,
                    "bytes_written": 0,
                    "frame_bytes": len(frame) if frame is not None else 0,
                    "full_frame_written": False,
                    "physical_status": "not_attempted",
                    "outcome": "not_attempted",
                },
            )
            if frame is not None:
                state["frame_bytes"] = len(frame)
            return state

        def guarded_before_attempt(target: str, attempt: int) -> bool | str:
            allowed = before_attempt(target, attempt) if before_attempt else True
            if allowed is True:
                state_for(target)["attempts_started"] = attempt
            return allowed

        def write_started(target: str, frame: bytes) -> None:
            nonlocal audit_persist_failed_after_io
            state = state_for(target, frame)
            state["write_call_started"] = True
            state["physical_status"] = "write_call_started"
            state["outcome"] = "write_outcome_uncertain"
            started = update_current(
                physical_status="write_call_started",
                outcome="write_outcome_uncertain",
                target=target,
                frame_bytes=len(frame),
                operations=operations_snapshot(),
                message="The typed attempt is persisted and the serial write call is starting",
            )
            if not persist_safely(started, "advance_attempt"):
                audit_persist_failed_after_io = True

        def write_result(target: str, frame: bytes, written_count: int | None) -> None:
            nonlocal audit_persist_failed_after_io
            state = state_for(target, frame)
            if written_count is None:
                state["write_count_known"] = False
                state["reported_write_count"] = None
                return
            state["write_count_known"] = True
            state["reported_write_count"] = written_count
            if written_count > 0:
                state["bytes_written"] = max(int(state["bytes_written"]), written_count)
            if written_count != len(frame):
                state["physical_status"] = "partial_write" if written_count > 0 else "not_written"
                state["outcome"] = "outcome_uncertain" if written_count > 0 else "not_written"
                partial = update_current(
                    attempted=written_count > 0,
                    physical_status=state["physical_status"],
                    outcome=state["outcome"],
                    target=target,
                    bytes_written=max(
                        int((_memory_dispatches.get(clean_dispatch_id) or {}).get("bytes_written") or 0),
                        max(0, written_count),
                    ),
                    frame_bytes=len(frame),
                    operations=operations_snapshot(),
                    message="Serial transport reported a partial frame write" if written_count > 0 else "Serial transport reported zero bytes written",
                )
                if not persist_safely(partial, "advance_attempt"):
                    audit_persist_failed_after_io = True
                return
            state["full_frame_written"] = True
            state["physical_status"] = "full_frame_written"
            state["outcome"] = "awaiting_acknowledgement"
            if target in sent_targets:
                retried_write = update_current(
                    attempted=True,
                    physical_status="full_frame_written",
                    outcome="awaiting_acknowledgement",
                    target=target,
                    bytes_written=max(
                        int((_memory_dispatches.get(clean_dispatch_id) or {}).get("bytes_written") or 0),
                        written_count,
                    ),
                    frame_bytes=len(frame),
                    operations=operations_snapshot(),
                    message="A complete retry frame write returned successfully; awaiting acknowledgement",
                )
                if not persist_safely(retried_write, "advance_attempt"):
                    audit_persist_failed_after_io = True
                return
            sent_targets.add(target)
            sent = transition(
                "sent",
                attempted=True,
                physical_status="full_frame_written",
                target=target,
                bytes_written=max(
                    int((_memory_dispatches.get(clean_dispatch_id) or {}).get("bytes_written") or 0),
                    written_count,
                ),
                frame_bytes=len(frame),
                operations=operations_snapshot(),
                message="A complete PLC frame write returned successfully; awaiting acknowledgement",
            )
            if not persist_safely(sent, "advance_attempt"):
                audit_persist_failed_after_io = True

        try:
            client = FxAsciiClient(
                normalized,
                transport_factory=transport_factory,
                on_write_started=write_started,
                on_write_result=write_result,
                before_attempt=guarded_before_attempt,
                after_attempt=after_attempt,
                on_attempt_started=on_attempt_started,
                on_attempt_finished=on_attempt_finished,
            )
            receipts = client.sync_result(bool(passed))
        except (PlcConfigError, PlcTransportError) as exc:
            error_code = exc.code if isinstance(exc, PlcTransportError) else "invalid_config"
            attempts = exc.attempts if isinstance(exc, PlcTransportError) else 0
            receipts = list(exc.receipts) if isinstance(exc, PlcTransportError) else []
            operations = operations_snapshot(exc.operations if isinstance(exc, PlcTransportError) else None)
            failed_target = exc.failed_target if isinstance(exc, PlcTransportError) else ""
            if error_code == "control_state_check_failed":
                error_code = (
                    "control_state_check_failed_after_partial_ack"
                    if receipts
                    else "control_state_check_failed_before_io"
                )
            failed_state = dict(target_states.get(failed_target, {}))
            any_write_started = any(bool(state.get("write_call_started")) for state in target_states.values())
            any_bytes_written = any(int(state.get("bytes_written") or 0) > 0 for state in target_states.values())
            attempted = bool(receipts) or any_write_started or any_bytes_written
            if error_code == "nak":
                failed_state["physical_status"] = "rejected"
                failed_state["outcome"] = "rejected"
            elif error_code in {"cancelled_after_disable", "cancelled_after_config_change", "deadline_exceeded"}:
                failed_state.setdefault("physical_status", "not_attempted")
                failed_state.setdefault(
                    "outcome",
                    "deadline_exceeded" if error_code == "deadline_exceeded" else "cancelled_before_attempt",
                )
            elif failed_state.get("full_frame_written"):
                failed_state["physical_status"] = "full_frame_written"
                failed_state["outcome"] = "outcome_uncertain"
            elif int(failed_state.get("bytes_written") or 0) > 0:
                failed_state["physical_status"] = "partial_write"
                failed_state["outcome"] = "outcome_uncertain"
            elif failed_state.get("write_call_started"):
                failed_state["physical_status"] = "write_outcome_uncertain"
                failed_state["outcome"] = "outcome_uncertain"
            physical_status = (
                "partial_success"
                if receipts
                else str(failed_state.get("physical_status") or ("write_outcome_uncertain" if attempted else "not_attempted"))
            )
            outcome = "partial_failure" if receipts else str(failed_state.get("outcome") or ("outcome_uncertain" if attempted else "not_attempted"))
            frames = [
                {"target": receipt.target, "frame_hex": receipt.frame_hex, "attempts": receipt.attempts}
                for receipt in receipts
            ]
            canonical_operation = next(
                (
                    dict(item)
                    for item in reversed(operations)
                    if item.get("target") == failed_target
                ),
                None,
            )
            failed_operation = {
                "attempt_id": str((canonical_operation or {}).get("attempt_id") or ""),
                "target": failed_target,
                "frame_hex": str((canonical_operation or {}).get("frame_hex") or ""),
                "error_code": error_code,
                "attempts": attempts,
                "physical_status": (canonical_operation or failed_state).get("physical_status", "not_attempted"),
                "outcome": (canonical_operation or failed_state).get("outcome", "not_attempted"),
                "bytes_written": int((canonical_operation or failed_state).get("bytes_written") or 0),
                "frame_bytes": int((canonical_operation or failed_state).get("frame_bytes") or 0),
                "diagnostic_source": str((canonical_operation or {}).get("diagnostic_source") or ""),
            }
            failed = transition(
                "failed",
                attempted=attempted,
                physical_status=physical_status,
                outcome=outcome,
                audit_status="persist_failed" if audit_persist_failed_after_io else "persisted",
                error_code=error_code,
                diagnostic_source=exc.diagnostic_source if isinstance(exc, PlcTransportError) else "",
                attempts=attempts,
                acknowledged_targets=[receipt.target for receipt in receipts],
                failed_target=failed_target,
                targets=[receipt.target for receipt in receipts],
                frames=frames,
                failed_operation=failed_operation,
                operations=operations,
                cancelled_after_disable=error_code == "cancelled_after_disable",
                cancelled_after_config_change=error_code == "cancelled_after_config_change",
                deadline_exceeded=error_code == "deadline_exceeded",
                no_automatic_retry=True if receipts else False,
                message=str(exc),
            )
            if not persist_safely(failed, "finalize"):
                failed = {**failed, "audit_status": "persist_failed"}
                _remember_dispatch(clean_dispatch_id, failed)
            return dict(failed)

        frames = [
            {"target": receipt.target, "frame_hex": receipt.frame_hex, "attempts": receipt.attempts}
            for receipt in receipts
        ]
        acknowledged_targets = [receipt.target for receipt in receipts]
        operations = operations_snapshot()
        try:
            cancel_reason = dispatch_cancel_reason() if dispatch_cancel_reason is not None else ""
        except Exception:
            control_unknown = transition(
                "failed",
                attempted=True,
                physical_status="acknowledged",
                audit_status="persisted",
                outcome="acknowledged_control_state_unknown",
                error_code="control_state_check_failed_after_ack",
                attempts=sum(receipt.attempts for receipt in receipts),
                acknowledged_targets=acknowledged_targets,
                targets=acknowledged_targets,
                frames=frames,
                operations=operations,
                message="PLC acknowledged all frames, but the final control-state check failed; do not automatically retry",
            )
            if not persist_safely(control_unknown, "finalize"):
                control_unknown = {**control_unknown, "audit_status": "persist_failed"}
                _remember_dispatch(clean_dispatch_id, control_unknown)
            return dict(control_unknown)
        if not cancel_reason and is_dispatch_active is not None and not is_dispatch_active():
            cancel_reason = "cancelled_after_disable"
        if cancel_reason:
            cancelled_by_deadline = cancel_reason == "deadline_exceeded"
            cancelled_by_config_change = cancel_reason == "cancelled_after_config_change"
            cancelled = transition(
                "failed",
                attempted=True,
                physical_status="acknowledged",
                audit_status="persisted",
                outcome=(
                    "acknowledged_after_deadline"
                    if cancelled_by_deadline
                    else ("acknowledged_after_config_change" if cancelled_by_config_change else "acknowledged_after_disable")
                ),
                error_code=(
                    "deadline_exceeded"
                    if cancelled_by_deadline
                    else ("cancelled_after_config_change" if cancelled_by_config_change else "cancelled_after_disable")
                ),
                cancelled_after_disable=not cancelled_by_deadline and not cancelled_by_config_change,
                cancelled_after_config_change=cancelled_by_config_change,
                deadline_exceeded=cancelled_by_deadline,
                attempts=sum(receipt.attempts for receipt in receipts),
                acknowledged_targets=acknowledged_targets,
                targets=acknowledged_targets,
                frames=frames,
                operations=operations,
                message=(
                    "PLC acknowledged the already-started frame after the request deadline; the completed physical I/O was not revoked"
                    if cancelled_by_deadline
                    else (
                        "PLC acknowledged the already-started frame, but the physical I/O configuration changed before completion; the completed physical I/O was not revoked"
                        if cancelled_by_config_change
                        else "PLC acknowledged the already-started frame, but synchronization was disabled before completion; the completed physical I/O was not revoked"
                    )
                ),
            )
            if not persist_safely(cancelled, "finalize"):
                cancelled = {**cancelled, "audit_status": "persist_failed"}
                _remember_dispatch(clean_dispatch_id, cancelled)
            return dict(cancelled)

        acknowledged = transition(
            "acknowledged",
            attempted=True,
            physical_status="acknowledged",
            audit_status="persisted",
            attempts=sum(receipt.attempts for receipt in receipts),
            acknowledged_targets=acknowledged_targets,
            targets=acknowledged_targets,
            frames=frames,
            operations=operations,
            message="PLC acknowledged all frames",
        )
        if persist_safely(acknowledged, "finalize"):
            return dict(acknowledged)

        audit_failed = transition(
            "failed",
            attempted=True,
            physical_status="acknowledged",
            audit_status="persist_failed",
            outcome="acknowledged_audit_unpersisted",
            error_code="audit_persist_failed_after_ack",
            attempts=acknowledged["attempts"],
            targets=acknowledged["targets"],
            frames=acknowledged["frames"],
            message="PLC acknowledged all frames, but final audit persistence failed; do not automatically retry",
        )
        persist_safely(audit_failed, "audit_failure_finalize")
        return dict(audit_failed)
