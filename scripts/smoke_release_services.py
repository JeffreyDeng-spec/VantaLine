"""Unit-file rollback and effective systemd settings using a private directory."""
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from release_runtime_contract import ContractError, Topology, WEB, LABEL
from release_services import ServiceCommands, UnitChanges, WEB_DROPIN, LABEL_UNIT, MARKER, duration_seconds


class Commands:
    def __init__(self):
        self.enabled='not-found'; self.events=[]; self.budget='8min 20s'; self.kill='control-group'
    def run(self,*arguments,**options):
        self.events.append(arguments)
        return SimpleNamespace(stdout=self.enabled if arguments[0]=='is-enabled' else '',returncode=0)
    def property(self,service,name,**options):
        if name=='ActiveState': return 'active' if service==WEB else 'inactive'
        if name=='TimeoutStopUSec': return self.budget
        if name=='KillMode': return self.kill
        raise AssertionError(name)


class Units(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.commands=Commands(); self.units=UnitChanges(self.root,self.commands)
        self.external=Topology('a'*40,'external',1)
        self.embedded=Topology('a'*40,'embedded',1)

    def test_new_units_restore_to_absence_and_disable_before_removal(self):
        saved=self.units.capture(); self.units.install(self.external)
        self.assertTrue((self.root/WEB_DROPIN).is_file())
        self.assertIn('TimeoutStopSec=500',(self.root/LABEL_UNIT).read_text())
        self.units.restore(saved)
        self.assertFalse((self.root/WEB_DROPIN).exists()); self.assertFalse((self.root/LABEL_UNIT).exists())
        self.assertEqual(self.commands.events[-2:], [('disable',LABEL),('daemon-reload',)])

    def test_owned_unit_bytes_mode_and_enabled_state_restored(self):
        path=self.root/LABEL_UNIT; text=MARKER+'[Service]\nRestart=no\n'; path.write_text(text); path.chmod(0o640)
        self.commands.enabled='enabled'
        saved=self.units.capture(); self.units.install(self.external); self.units.restore(saved)
        self.assertEqual(path.read_text(),text); self.assertEqual(path.stat().st_mode & 0o777,0o640)
        self.assertEqual(self.commands.events[-1],('enable',LABEL))

    def test_masked_worker_restored_without_enabling(self):
        path=self.root/LABEL_UNIT; path.symlink_to('/dev/null'); self.commands.enabled='masked'
        saved=self.units.capture(); self.units.install(self.external); self.units.restore(saved)
        self.assertTrue(path.is_symlink()); self.assertEqual(os.readlink(path),'/dev/null')
        self.assertEqual(self.commands.events.count(('enable',LABEL)),1)

    def test_embedded_mode_does_not_install_or_enable_worker(self):
        self.units.install(self.embedded)
        self.assertFalse((self.root/LABEL_UNIT).exists())
        self.assertNotIn(('enable',LABEL),self.commands.events)

    def test_unmanaged_unit_refused(self):
        path=self.root/LABEL_UNIT; path.write_text('[Service]\nExecStart=/unmanaged\n')
        with self.assertRaises(ContractError): self.units.capture()
        self.assertEqual(path.read_text(),'[Service]\nExecStart=/unmanaged\n')

    def test_writable_unit_refused(self):
        path=self.root/LABEL_UNIT; path.write_text(MARKER); path.chmod(0o666)
        with self.assertRaises(ContractError): self.units.capture()

    def test_unexpected_symlink_and_fifo_refused(self):
        path=self.root/LABEL_UNIT; path.symlink_to(self.root/'elsewhere')
        with self.assertRaises(ContractError): self.units.capture()
        path.unlink(); os.mkfifo(path)
        with self.assertRaises(ContractError): self.units.capture()

    def test_symlink_directory_refused(self):
        external=self.root/'elsewhere'; external.mkdir()
        (self.root/WEB_DROPIN.parent).symlink_to(external,target_is_directory=True)
        with self.assertRaises(ContractError): self.units.capture()

    def test_effective_settings_must_match_not_just_written_template(self):
        for field,value in (('budget','90s'),('kill','process')):
            with self.subTest(field=field):
                commands=Commands(); setattr(commands,field,value)
                with self.assertRaises(ContractError): UnitChanges(self.root,commands).install(self.external)
                self.assertNotIn(('enable',LABEL),commands.events)

    def test_effective_budget_parser(self):
        for value in ('8min 20s','500s','500000000us','500000ms'):
            self.assertEqual(duration_seconds(value),500)
        for value in ('infinity','500','500s garbage','-500s',''):
            with self.assertRaises(ContractError): duration_seconds(value)

    def test_commissioned_web_allowance_preserves_admin_file_and_template(self):
        admin = self.root / WEB_DROPIN.parent / '90-administrator.conf'
        admin.parent.mkdir(); content = '[Service]\nTimeoutStopSec=510\n'
        admin.write_text(content); admin.chmod(0o640)
        self.commands.budget = '8min 30s'
        saved = self.units.capture()
        self.units.install(self.embedded)
        self.assertIn('TimeoutStopSec=500', (self.root / WEB_DROPIN).read_text())
        self.assertEqual(admin.read_text(), content)
        self.units.restore(saved)
        self.assertEqual(admin.read_text(), content)
        self.assertEqual(admin.stat().st_mode & 0o777, 0o640)
        self.assertFalse((self.root / WEB_DROPIN).exists())

    def test_only_web_exact_500_or_510_is_compatible(self):
        for value in ('0s', '479s', '480s', '499s', '500.1s', '509s', '510.1s', '511s', '600s', 'infinity'):
            with self.subTest(value=value):
                self.commands.budget = value
                with self.assertRaises(ContractError): self.units.install(self.embedded)
        self.commands.budget = '510s'
        with self.assertRaises(ContractError): self.units.install(self.external)
        self.assertNotIn(('enable', LABEL), self.commands.events)
        self.commands.kill = 'process'
        with self.assertRaises(ContractError): self.units.install(self.embedded)

    def test_web510_and_worker500_can_be_verified_together(self):
        self.commands.budget = '510s'
        original = self.commands.property
        def property_value(service, name, **options):
            if service == LABEL and name == 'TimeoutStopUSec': return '500s'
            return original(service, name, **options)
        with patch.object(self.commands, 'property', side_effect=property_value):
            self.units.install(self.external)
        self.assertIn(('enable', LABEL), self.commands.events)
        self.assertIn('TimeoutStopSec=500', (self.root / LABEL_UNIT).read_text())

    def test_stop_deadline_requires_inactive_and_both_pids_zero(self):
        # Real stop loop with a virtual clock, not 500 seconds of sleeping.
        for field, value in (('ActiveState', 'deactivating'), ('MainPID', '12'), ('ControlPID', '13')):
            with self.subTest(field=field):
                now = [0.0]; commands = ServiceCommands(); events = []
                def sleep(amount): now[0] += amount
                def state(service, name, **options):
                    self.assertGreater(options['timeout'], 0)
                    return value if name == field else {'ActiveState':'inactive', 'MainPID':'0', 'ControlPID':'0'}[name]
                with (patch('release_services.time.monotonic', side_effect=lambda: now[0]),
                      patch('release_services.time.sleep', side_effect=sleep),
                      patch.object(commands, 'property', side_effect=state),
                      patch.object(commands, 'run', side_effect=lambda *args, **kw: events.append(args))):
                    with self.assertRaisesRegex(ContractError, 'stop budget expired'):
                        commands.stop_all((WEB,), deadline=500)
                self.assertEqual(now[0], 500)
                self.assertEqual(events, [('stop', '--no-block', WEB)])
        commands = ServiceCommands()
        with (patch.object(commands, 'property', side_effect=lambda service, name, **kw: {'ActiveState':'inactive', 'MainPID':'0', 'ControlPID':'0'}[name]),
              patch.object(commands, 'run') as run, patch('release_services.time.monotonic', return_value=0)):
            commands.stop_all((WEB, LABEL), deadline=500)
            run.assert_called_once_with('stop', '--no-block', WEB, LABEL, timeout=500)


if __name__=='__main__': unittest.main()
