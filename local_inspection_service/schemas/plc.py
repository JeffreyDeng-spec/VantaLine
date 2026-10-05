"""Strict PLC HTTP request shapes; physical I/O remains browser-owned."""
from pydantic import BaseModel, StrictBool, StrictFloat, StrictInt, StrictStr
from ..plc_fx_ascii import PROTOCOL_ID as PLC_PROTOCOL_ID
from ..plc_web_serial import WEB_SERIAL_PROFILE_ID, WEB_SERIAL_SCHEMA_VERSION


class PlcConfigRequest(BaseModel):
    class Config:
        extra = "forbid"

    enabled: StrictBool | None = None
    protocol: StrictStr | None = None
    checksum_mode: StrictStr | None = None
    serial_port: StrictStr | None = None
    baudrate: StrictInt | None = None
    parity: StrictStr | None = None
    data_bits: StrictInt | None = None
    stop_bits: StrictInt | None = None
    result_register: StrictStr | None = None
    output_control_point: StrictStr | None = None
    capture_trigger_enabled: StrictBool | None = None
    capture_input_register: StrictStr | None = None
    capture_trigger_value: StrictInt | None = None
    # Rolling-deploy input compatibility only. Canonical responses never expose these fields.
    d206_address: StrictStr | None = None
    y04_address: StrictStr | None = None
    write_y04: StrictBool | None = None
    timeout: StrictFloat | StrictInt | None = None
    retries: StrictInt | None = None


class PlcCaptureSessionRequest(BaseModel):
    class Config:
        extra = "forbid"

    model_id: StrictStr | None = None
    camera_ready: StrictBool


class PlcCaptureSessionHeartbeatRequest(BaseModel):
    class Config:
        extra = "forbid"

    session_id: StrictStr


class PlcWebSerialConfigRequest(BaseModel):
    class Config:
        extra = "forbid"

    schema_version: StrictInt = WEB_SERIAL_SCHEMA_VERSION
    transport_mode: StrictStr = "web_serial"
    profile_id: StrictStr = WEB_SERIAL_PROFILE_ID
    enabled: StrictBool = False
    protocol: StrictStr = PLC_PROTOCOL_ID
    checksum_mode: StrictStr = "include_etx"
    baudrate: StrictInt = 9600
    parity: StrictStr = "E"
    data_bits: StrictInt = 7
    stop_bits: StrictInt = 1
    result_register: StrictStr = "D206"
    output_control_point: StrictStr = ""
    capture_trigger_enabled: StrictBool = False
    capture_input_register: StrictStr = "D205"
    capture_trigger_value: StrictInt = 1
    capture_poll_interval_ms: StrictInt = 200
    ack_timeout_ms: StrictInt = 500
    retries: StrictInt = 0


class PlcWorkstationPairRequest(BaseModel):
    class Config:
        extra = "forbid"

    name: StrictStr
    station_id: StrictStr | None = None


class PlcWorkstationVerifyRequest(BaseModel):
    class Config:
        extra = "forbid"

    verified: StrictBool


class PlcWorkstationLeaseRequest(BaseModel):
    class Config:
        extra = "forbid"

    client_instance_id: StrictStr
    model_id: StrictStr
    bundle_version: StrictStr


class PlcWorkstationLeaseActivateRequest(BaseModel):
    class Config:
        extra = "forbid"

    session_id: StrictStr
    lease_epoch: StrictInt
    usb_vendor_id: StrictInt | None = None
    usb_product_id: StrictInt | None = None


class PlcWorkstationLeaseHeartbeatRequest(BaseModel):
    class Config:
        extra = "forbid"

    session_id: StrictStr
    lease_epoch: StrictInt


class PlcWorkstationLeaseRebindRequest(BaseModel):
    class Config:
        extra = "forbid"

    session_id: StrictStr
    lease_epoch: StrictInt
    model_id: StrictStr


class PlcWebSerialAttemptRequest(BaseModel):
    class Config:
        extra = "forbid"

    session_id: StrictStr
    lease_epoch: StrictInt
    config_generation: StrictInt


class PlcWebSerialDiagnosticReceiptRequest(BaseModel):
    class Config:
        extra = "forbid"

    session_id: StrictStr
    lease_epoch: StrictInt
    diagnostic_id: StrictStr
    attempt_token: StrictStr
    outcome: StrictStr


class PlcWebSerialDiagnosticConfirmRequest(BaseModel):
    class Config:
        extra = "forbid"

    session_id: StrictStr
    lease_epoch: StrictInt
    diagnostic_id: StrictStr
    attempt_token: StrictStr


class PlcWebSerialReceiptOperation(BaseModel):
    class Config:
        extra = "forbid"

    target: StrictStr
    frame_sha256: StrictStr
    status: StrictStr
    response_hex: StrictStr
    completed_at: StrictInt


class PlcWebSerialReceiptRequest(BaseModel):
    class Config:
        extra = "forbid"

    session_id: StrictStr
    lease_epoch: StrictInt
    attempt_token: StrictStr
    outcome: StrictStr
    operations: list[PlcWebSerialReceiptOperation]
