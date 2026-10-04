"""Unit-file rollback and effective systemd settings using a private directory."""
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from release_runtime_contract import ContractError, Topology, WEB, LABEL
from release_services import UnitChanges, WEB_DROPIN, LABEL_UNIT, MARKER, duration_seconds


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


if __name__=='__main__': unittest.main()
