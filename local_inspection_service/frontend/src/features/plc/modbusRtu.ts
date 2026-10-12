import { diagnosticError } from "./diagnosticLog";

export function modbusCrc(data: Uint8Array): number {
  let crc = 0xffff;
  for (const byte of data) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xa001 : 0);
  }
  return crc;
}

export function parseModbusWord(response: Uint8Array): number {
  if (response.length !== 7 || response[0] !== 1 || response[1] !== 3 || response[2] !== 2) {
    throw diagnosticError(new Error("Modbus 读取响应格式或站号不匹配"), {code:"invalid_frame",expected_bytes:7,actual_bytes:response.length});
  }
  if (modbusCrc(response.slice(0, -2)) !== (response[5] | response[6] << 8)) {
    throw diagnosticError(new Error("Modbus CRC 校验失败"), {code:"invalid_checksum",expected_bytes:7,actual_bytes:response.length});
  }
  return response[3] << 8 | response[4];
}
