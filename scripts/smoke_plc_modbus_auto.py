"""Synthetic Modbus protocol and evidence checks. No physical I/O."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.plc_modbus_rtu import PROFILE, PROTOCOL, frame, read_word, write_word, parse_word, validate_write
from local_inspection_service.plc_web_serial import DEFAULT_WEB_SERIAL_CONFIG, normalize_web_serial_config, build_connection_check, validate_connection_check, build_web_serial_plan, build_web_serial_capture_read_plan, web_serial_resolved_addresses
from local_inspection_service.plc_fx_ascii import PlcConfigError
from local_inspection_service.schemas.plc import PlcConnectionReadEvidence

class ModbusContract(unittest.TestCase):
    def setUp(self):
        self.fx = {**DEFAULT_WEB_SERIAL_CONFIG, "enabled": True}
        self.config = {**self.fx,"profile_id":PROFILE,"protocol":PROTOCOL,"checksum_mode":"crc16","baudrate":19200,"data_bits":8}
        self.lease = dict(station_id="station",session_id="session",lease_epoch=1,config_generation=1,expires_at=200)
        self.lease["connection_check"] = build_connection_check(self.lease,self.fx,"check")
    def test_vectors(self):
        self.assertEqual(read_word(0).hex(),"010300000001840a")
        self.assertEqual(parse_word(frame(bytes.fromhex("0103021234"))),0x1234)
        self.assertTrue(validate_write(write_word(206,1),write_word(206,1)))
        self.assertFalse(validate_write(write_word(205,1),write_word(206,1)))
    def test_bounded_read_only_candidates(self):
        check=self.lease["connection_check"]
        self.assertEqual(len(check["alternatives"]),1)
        alt=check["alternatives"][0]
        self.assertEqual(alt["serial_options"]["baudRate"],19200)
        self.assertFalse(alt["config"]["capture_trigger_enabled"])
        self.assertTrue(all(bytes.fromhex(f["frame_hex"])[1]==3 for f in alt["frames"]))
        reads=[dict(target=f["target"],response_hex=frame(bytes.fromhex("0103020000")).hex()) for f in alt["frames"]]
        self.assertEqual(validate_connection_check(self.lease,alt["id"],reads,100)["protocol"],PROTOCOL)
        for evidence in reads: PlcConnectionReadEvidence(**evidence)
        with self.assertRaises(ValueError): validate_connection_check(self.lease,"invented",reads,100)
        with self.assertRaises(ValueError): validate_connection_check(self.lease,alt["id"],reads,200)
        reads[0]["response_hex"]="01030200000000"
        with self.assertRaises(ValueError): validate_connection_check(self.lease,alt["id"],reads,100)
    def test_strict_config_and_frames(self):
        self.assertEqual(normalize_web_serial_config(self.config),self.config)
        for key,value in (("retries",3),("data_bits",7),("baudrate",9600),("output_control_point","Y04")):
            with self.assertRaises(PlcConfigError): normalize_web_serial_config({**self.config,key:value})
        frames=build_web_serial_plan(self.config,True)
        self.assertEqual(len(frames),1)
        self.assertEqual(frames[0]["frame_hex"],write_word(206,1).hex().upper())
        self.assertEqual(frames[0]["expected_response_hex"],frames[0]["frame_hex"])
        self.assertEqual(build_web_serial_capture_read_plan(self.config,2)["expected_response_bytes"],7)
        self.assertEqual(web_serial_resolved_addresses(self.config)["result_register"],"00CE")
        self.assertFalse(build_connection_check(self.lease,self.config,"check").get("alternatives"))
        self.assertFalse(build_connection_check(self.lease,{**self.fx,"output_control_point":"Y04"},"check").get("alternatives"))
    def test_read_rejects_noise_wrong_unit_exception_crc(self):
        for response in (frame(bytes.fromhex("0203020000")),frame(bytes.fromhex("018302")),frame(bytes.fromhex("0103020000"))+b"x",bytes.fromhex("01030200000000")):
            with self.assertRaises(PlcConfigError): parse_word(response)
    def test_fx_bytes_unchanged(self):
        self.assertEqual(build_web_serial_capture_read_plan(self.fx,1)["frame_hex"],"0230313139413032033731")
        self.assertEqual(build_web_serial_plan(self.fx,True)[0]["expected_response_hex"],"06")
        reads=[dict(target=t,response_hex="0230303030034333") for t in ("D205","D206")]
        self.assertEqual(validate_connection_check(self.lease,"check",reads,100),self.fx)

    def test_actual_activation_persists_fenced_profile(self):
        import copy
        from types import SimpleNamespace as NS
        from local_inspection_service.plc.lease_acquisition import LeaseAcquisition
        state={"station":{"id":"station","config":self.fx,"config_generation":1,"profile_verified":True},
               "lease":{**self.lease,"owner_user_id":"owner","state":"connecting"},"clock":{"now":100}}
        def record(row): return dict((row or {}).get("raw_json", row or {}))
        def mutate(station,dispatch,callback):
            candidate=copy.deepcopy(state);callback(candidate);state.update(candidate);return candidate
        ports=NS(current_user=lambda:lambda:{"id":"owner"},record=lambda:record,mutate=lambda:mutate,
                 config_error=lambda:PlcConfigError,clock=lambda:lambda:100,
                 active_ttl=lambda:15,lease_row=lambda:lambda row:row)
        alt=self.lease["connection_check"]["alternatives"][0]
        request=NS(session_id="session",lease_epoch=1,usb_vendor_id=None,usb_product_id=None,
                   connection_check_id=alt["id"],connection_reads=[dict(target=f["target"],response_hex=frame(bytes.fromhex("0103020000")).hex()) for f in alt["frames"]])
        result=LeaseAcquisition(ports).activate("station",request)
        station=record(state["station"])
        self.assertEqual(station["config"]["protocol"],PROTOCOL)
        self.assertFalse(station["profile_verified"])
        self.assertFalse(station["config"]["capture_trigger_enabled"])
        self.assertEqual(station["config_generation"],2)
        self.assertEqual(result["config_generation"],2)
        self.assertTrue(result["communication_verified"])
        # Repeated activation cannot mutate a now active lease.
        with self.assertRaises(PlcConfigError): LeaseAcquisition(ports).activate("station",request)

    def test_actual_server_write_evidence(self):
        from types import SimpleNamespace as NS
        from local_inspection_service.plc.browser_dispatch import PlcBrowserDispatchService
        service=PlcBrowserDispatchService(None,None,NS(PlcConfigError=lambda:PlcConfigError),None)
        frames=build_web_serial_plan(self.config,True)
        evidence=dict(target="D206",frame_sha256=frames[0]["frame_sha256"],status="acknowledged",response_hex=frames[0]["frame_hex"])
        self.assertEqual(service._plc_web_serial_receipt_outcome(frames,[evidence]),"acknowledged")
        for status,response in (("acknowledged","06"),("nak","15")):
            with self.assertRaises(PlcConfigError): service._plc_web_serial_receipt_outcome(frames,[{**evidence,"status":status,"response_hex":response}])
        self.assertEqual(service._plc_web_serial_receipt_outcome(frames,[{**evidence,"status":"timeout","response_hex":""}]),"uncertain")

    def test_connected_station_does_not_require_manual_mapping_confirmation(self):
        from types import SimpleNamespace as NS
        from local_inspection_service.plc.browser_dispatch import PlcBrowserDispatchService
        for verified, fingerprint in ((False,""),(True,"stale")):
            station={"config":self.config,"profile_verified":verified,"profile_verified_fingerprint":fingerprint}
            lease={"model_id":"model","lease_epoch":1,"expires_at":200}
            state={"station":station,"lease":lease,"dispatch":None}
            service=PlcBrowserDispatchService(
                NS(_plc_web_serial_mutate=lambda:lambda sid,did,callback:(callback(state),state)[1],_plc_web_serial_record=lambda:lambda row:row,
                   _plc_web_serial_dispatch_row=lambda:lambda row:row,
                   _plc_workstation_lease_row=lambda:lambda row:row),
                NS(_plc_web_serial_require_active_lease=lambda:lambda state,session:(station,lease,100)),
                NS(migrate_web_serial_config=lambda:normalize_web_serial_config,PlcConfigError=lambda:PlcConfigError,
                   WEB_SERIAL_PROTOCOL_VERSION=lambda:"plc-web-serial-v4",
                   web_serial_config_fingerprint=lambda:lambda config:"config-fingerprint"),None)
            record, created = service.plc_web_serial_begin_camera_detection("station","session","request-123","model","fingerprint")
            self.assertTrue(created)
            self.assertEqual(record["status"], "detecting")
            self.assertEqual(record["frames"], [])
            self.assertEqual(lease["in_flight_dispatch_id"], record["dispatch_id"])

    def test_source_contract_rejects_mutations_and_preserves_parent(self):
        import hashlib
        from plc_modbus_source_contract import checked_fixture, restore_modbus_business
        fixture=checked_fixture()
        root=Path(__file__).resolve().parents[1]
        for path,change in fixture["files"].items():
            current=(root/path).read_bytes()
            self.assertEqual(hashlib.sha256(restore_modbus_business(path,current)).hexdigest(),change["parent_sha256"])
            with self.assertRaises(AssertionError): restore_modbus_business(path,current+b"\n# unexpected mutation\n")
        # A mutated added protocol adapter must fail before any inverse runs.
        from unittest.mock import patch
        original=Path.read_bytes
        added=root/"local_inspection_service/plc_modbus_rtu.py"
        with patch.object(Path,"read_bytes",lambda p: original(p)+b"\n# mutation" if p==added else original(p)):
            with self.assertRaisesRegex(AssertionError,"adapter changed"): checked_fixture()

if __name__=="__main__": unittest.main()
