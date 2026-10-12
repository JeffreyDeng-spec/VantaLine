"""Bounded, credential-free browser diagnostic reports, never PLC authority."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt

Step = Literal['selection','workstation','lease','open','quiet','read','activate','heartbeat','write','disconnect','summary']
Result = Literal['started','ok','failed','cancelled','uncertain','summary']
Code = Literal['','unsupported','cancelled','occupied','serial_error','timeout','partial_response','invalid_frame','invalid_checksum','residual_data','permission_denied','lease_rejected','lease_lost','config_changed','background','nak','uncertain','unplugged','user_disconnect','connection_failed','transport_error']

class DiagnosticConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    baudrate: Literal[9600, 19200] = 9600
    data_bits: Literal[7, 8] = 7
    parity: Literal['E'] = 'E'
    stop_bits: Literal[1] = 1
    input_register: str = Field(default='', pattern=r'^(|D(?:0|[1-9][0-9]{0,2}))$')
    result_register: str = Field(default='', pattern=r'^(|D(?:0|[1-9][0-9]{0,2}))$')
    output_control_point: str = Field(default='', pattern=r'^(|Y(?:0[0-7]|1[0-7]))$')
    timeout_ms: Literal[500] = 500
    capture_enabled: bool = False
    trigger_value: StrictInt = Field(default=1,ge=0,le=65535)

class PlcDiagnosticEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    event_id: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    attempt_id: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    sequence: StrictInt = Field(ge=0,le=2147483647)
    station_id: str | None = Field(default=None,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    step: Step
    result: Result
    code: Code = ''
    client_time_ms: StrictInt = Field(ge=0,le=9999999999999)
    duration_ms: StrictInt = Field(default=0,ge=0,le=86400000)
    config_generation: StrictInt = Field(default=0,ge=0,le=2147483647)
    lease_epoch: StrictInt = Field(default=0,ge=0,le=2147483647)
    bundle_version: str = Field(default='',max_length=100,pattern=r'^[A-Za-z0-9._-]*$')
    dispatch_id: str = Field(default='',max_length=100,pattern=r'^[A-Za-z0-9_-]*$')
    target: str = Field(default='',pattern=r'^(|D(?:0|[1-9][0-9]{0,2})|Y(?:0[0-7]|1[0-7]))$')
    trigger_state: Literal['','high','reset'] = ''
    expected_bytes: StrictInt = Field(default=0,ge=0,le=64)
    actual_bytes: StrictInt = Field(default=0,ge=0,le=65536)
    reads_ok: StrictInt = Field(default=0,ge=0,le=2147483647)
    heartbeats_ok: StrictInt = Field(default=0,ge=0,le=2147483647)
    writes_ok: StrictInt = Field(default=0,ge=0,le=2147483647)
    dropped: StrictInt = Field(default=0,ge=0,le=2147483647)
    config: DiagnosticConfig | None = None

class PlcDiagnosticBatch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    events: list[PlcDiagnosticEvent] = Field(min_length=1,max_length=20)
