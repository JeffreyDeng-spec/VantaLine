"""Offline deployment state-machine faults with explicit process/queue evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from release_runtime_contract import ContractError, WEB, LABEL, Topology
from release_runtime_transition import RuntimeTransition


class Harness:
    def __init__(self, root):
        self.root = root
        self.current = root/'current'
        self.old = self.release('v2026.10.1', 'a'*40, 'embedded', protocol=True)
        self.new = self.release('v2026.10.2', 'b'*40, 'external', protocol=True)
        self.current.symlink_to(self.old, target_is_directory=True)
        self.now, self.serial = 10.0, 100
        self.events, self.processes = [], {}
        self.queue, self.active = 0, 0
        self.maintenance, self.config = False, 'e'*64
        self.fail_start = self.fail_status = self.fail_stop = None
        self.mutate = lambda service, value: value
        self.run('start', WEB)
        self.events.clear()
        self.journal = root/'journal.json'
        self.transition = RuntimeTransition(self.journal, commands=self, units=self,
            client=self.request, clock=lambda: self.now, sleep=self.sleep, uid=1000, backgrounds=root/'shared-backgrounds')

    def release(self, name, commit, mode, protocol):
        path = self.root/name; path.mkdir()
        (path/'VERSION.json').write_text(json.dumps({'git_commit': commit, 'release': name}))
        topology = {'schema': 2 if protocol else 1, 'git_commit': commit,
                    'worker_mode': mode, 'services': [WEB]+([LABEL] if mode == 'external' else [])}
        if protocol: topology['runtime_protocol'] = 1
        (path/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(topology))
        return path

    def sleep(self, amount):
        self.now += amount

    def property(self, service, name, **options):
        process = self.processes.get(service)
        if name == 'MainPID': return str(process['pid']) if process else '0'
        if name == 'ControlPID': return '0'
        if name == 'LoadState': return 'loaded' if service == WEB or process else 'not-found'
        if name == 'ActiveState': return 'active' if process else 'inactive'
        raise AssertionError(name)

    def run(self, command, *services, **options):
        self.events.append((command, *services))
        if command == 'start':
            service = services[0]
            if service == self.fail_start: raise ContractError('Synthetic start failure')
            if service in self.processes: return  # systemctl start is idempotent.
            self.serial += 1
            directory = self.current.resolve()
            topology = json.loads((directory/'RUNTIME_TOPOLOGY.json').read_text())
            self.processes[service] = {'topology': topology, 'release': directory.name,
                'pid': self.serial, 'instance': f'{self.serial:032x}',
                'state': 'drained' if self.maintenance else 'ready', 'revision': '0'*32}

    def stop_all(self, services, *, deadline):
        self.events.append(('stop', *services))
        if self.fail_stop: raise ContractError('Synthetic stop failure')
        for service in services: self.processes.pop(service, None)

    def capture(self):
        self.events.append(('capture',))
        return {'fixture': True}

    def install(self, topology, *, deadline=None, stopping_services=()): self.events.append(('install', topology.mode))
    def restore(self, snapshot):
        assert snapshot == {'fixture': True}
        self.events.append(('restore',))

    def request(self, service, command, revision, **options):
        self.events.append(('control', service, command))
        if self.fail_status: raise ContractError('Synthetic database failure')
        process = self.processes[service]
        assert options['pid'] == process['pid']
        if command != 'status': process['revision'] = revision
        if command == 'close_admission': self.maintenance = True
        if command == 'open_admission': self.maintenance = False
        if command == 'pause': process['state'] = 'drained'
        if command == 'resume': process['state'] = 'ready'
        value = {'schema': 1, 'git_commit': process['topology']['git_commit'],
            'release': process['release'], 'role': 'web' if service == WEB else 'label',
            'worker_mode': process['topology']['worker_mode'], 'instance': process['instance'],
            'pid': process['pid'], 'heartbeat': self.now, 'state': process['state'],
            'control_revision': process['revision'], 'active_iterations': 0,
            'queued_runs': self.queue, 'active_runs': self.active,
            'maintenance': self.maintenance, 'config_revision': self.config}
        return self.mutate(service, value)

    def switch(self):
        self.current.unlink(); self.current.symlink_to(self.new, target_is_directory=True)


class Transitions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.h = Harness(Path(self.temp.name))

    def test_success_stops_embedded_before_starting_external_and_opens_last(self):
        h=self.h
        h.transition.begin(h.old, h.new)
        self.assertTrue(h.maintenance)
        self.assertEqual(h.processes, {})
        h.switch(); h.transition.start()
        self.assertTrue(h.maintenance)
        self.assertEqual(set(h.processes), {WEB, LABEL})
        self.assertEqual(h.processes[LABEL]['state'], 'drained')
        h.transition.accept()
        self.assertFalse(h.maintenance)
        self.assertEqual(h.processes[LABEL]['state'], 'ready')
        self.assertLess(h.events.index(('stop', WEB)), h.events.index(('start', LABEL)))
        self.assertEqual(h.events[-1], ('control', WEB, 'open_admission'))

    def test_unaccepted_paused_candidate_rolls_back_with_queued_work_untouched(self):
        h = self.h
        # The legacy bridge can inherit a durable queued row from the old Web.
        h.old.joinpath('RUNTIME_TOPOLOGY.json').write_text(json.dumps({
            'schema': 1, 'git_commit': 'a'*40, 'worker_mode': 'embedded', 'services': [WEB]}))
        h.new.joinpath('RUNTIME_TOPOLOGY.json').write_text(json.dumps({
            'schema': 2, 'git_commit': 'b'*40, 'worker_mode': 'embedded',
            'services': [WEB], 'runtime_protocol': 1}))
        h.queue = 3
        h.transition.begin(h.old, h.new)
        h.maintenance = True  # New managed Web always initializes fenced.
        h.switch(); h.transition.start()
        h.events.clear()
        h.transition.rollback(h.current)
        self.assertEqual(h.queue, 3)
        self.assertEqual(h.current.resolve(), h.old)
        self.assertNotIn(('control', WEB, 'resume'), h.events)
        self.assertLess(h.now, 20)

    def test_preexisting_paused_backlog_survives_forward_switch_and_rollback(self):
        for rollback in (False, True):
            with self.subTest(rollback=rollback):
                with tempfile.TemporaryDirectory() as directory:
                    h = Harness(Path(directory))
                    h.queue = 4
                    h.processes[WEB]['state'] = 'drained'
                    h.maintenance = True
                    h.transition.begin(h.old, h.new)
                    h.switch(); h.transition.start()
                    if rollback:
                        h.transition.rollback(h.current)
                    else:
                        h.transition.accept()
                    self.assertEqual(h.queue, 4)
                    self.assertTrue(h.maintenance)
                    self.assertNotIn('resume', [e[-1] for e in h.events if e[0] == 'control'])

    def test_rollback_does_not_confuse_paused_threads_with_running_database_work(self):
        h = self.h
        h.transition.begin(h.old, h.new)
        h.switch(); h.transition.start()
        h.queue, h.active = 3, 1
        h.events.clear()
        with self.assertRaises(ContractError):
            h.transition.rollback(h.current)
        self.assertFalse(any(e[0] == 'stop' for e in h.events))
        self.assertEqual(h.current.resolve(), h.new)
        self.assertEqual(h.queue, 3)

    def test_queue_timeout_restores_admission_without_stopping_or_installing(self):
        h=self.h; h.queue=1
        with self.assertRaises(ContractError): h.transition.begin(h.old, h.new)
        self.assertTrue(h.maintenance)
        h.transition.rollback(h.current)
        self.assertFalse(h.maintenance)
        self.assertEqual(h.current.resolve(), h.old)
        self.assertFalse(any(item[0] in ('stop','install') for item in h.events))
        self.assertLessEqual(h.now, 510.1)

    def test_no_shared_configuration_refuses_before_mutation(self):
        h=self.h; h.config=None
        with self.assertRaises(ContractError): h.transition.begin(h.old, h.new)
        self.assertFalse(h.journal.exists())
        self.assertFalse(h.maintenance)
        self.assertFalse(any(item[0] in ('stop','install') for item in h.events))

    def test_legacy_web_cannot_jump_directly_to_external(self):
        h=self.h
        doc=json.loads((h.old/'RUNTIME_TOPOLOGY.json').read_text())
        doc['schema']=1; del doc['runtime_protocol']
        (h.old/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(doc))
        with self.assertRaises(ContractError): h.transition.begin(h.old, h.new)
        self.assertFalse(h.journal.exists())

    def test_worker_start_failure_restores_complete_previous_topology(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch(); h.fail_start=LABEL
        with self.assertRaises(ContractError): h.transition.start()
        h.fail_start=None; h.transition.rollback(h.current)
        self.assertEqual(h.current.resolve(),h.old)
        self.assertEqual(set(h.processes),{WEB})
        self.assertEqual(h.processes[WEB]['topology']['git_commit'],'a'*40)
        self.assertFalse(h.maintenance)
        self.assertIn(('restore',),h.events)

    def test_failed_candidate_stop_never_restarts_old_consumer(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
        h.fail_stop=True
        with self.assertRaises(ContractError): h.transition.rollback(h.current)
        self.assertEqual(h.current.resolve(),h.new)
        self.assertNotIn(('restore',),h.events)
        self.assertTrue(all(p['topology']['git_commit']=='b'*40 for p in h.processes.values()))

    def test_unavailable_database_never_stops_old_web(self):
        h=self.h; h.fail_status=True
        with self.assertRaises(ContractError): h.transition.begin(h.old,h.new)
        self.assertEqual(set(h.processes),{WEB})
        self.assertFalse(h.journal.exists())

    def test_wrong_build_or_stale_heartbeat_never_stops_old_web(self):
        h=self.h
        for field,value in (('git_commit','c'*40),('heartbeat',-100),('pid',456),('role','label')):
            with self.subTest(field=field):
                h.mutate=lambda service,d: {**d,field:value}
                with self.assertRaises(ContractError): h.transition.begin(h.old,h.new)
                self.assertFalse(h.journal.exists())
                self.assertEqual(set(h.processes),{WEB})

    def test_unknown_instance_during_pause_aborts_without_stopping(self):
        h=self.h
        h.mutate=lambda service,d: {**d,'instance':'f'*32} if h.maintenance else d
        with self.assertRaises(ContractError): h.transition.begin(h.old,h.new)
        self.assertFalse(any(item[0]=='stop' for item in h.events))
        self.assertTrue(h.maintenance)
        with self.assertRaises(ContractError): h.transition.rollback(h.current)
        self.assertTrue(h.maintenance)

    def test_preexisting_maintenance_is_preserved(self):
        h=self.h; h.maintenance=True
        h.transition.begin(h.old,h.new); h.switch(); h.transition.start(); h.transition.accept()
        self.assertTrue(h.maintenance)
        self.assertNotIn(('control',WEB,'open_admission'),h.events)

    def test_candidate_instance_change_before_accept_keeps_admission_closed(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
        h.processes[LABEL]['instance']='f'*32
        with self.assertRaises(ContractError): h.transition.accept()
        self.assertTrue(h.maintenance)

    def test_unfinished_journal_refuses_another_transition(self):
        h=self.h; h.journal.write_text('{}')
        with self.assertRaises(ContractError): h.transition.begin(h.old,h.new)
        self.assertEqual(h.events,[])

    def test_same_release_recovery_finishes_accept_before_success(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
        self.assertTrue(h.maintenance)
        h.transition.recover(h.new)
        self.assertFalse(h.maintenance)
        self.assertEqual(h.processes[LABEL]['state'],'ready')
        self.assertEqual(json.loads(h.journal.read_text())['phase'],'accepted')
        h.transition.recover(h.new)  # Idempotent after admission already reopened.
        self.assertFalse(h.maintenance)

    def test_recovery_completes_interrupted_resume_then_open(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
        original=h.transition.client
        def interrupted(service,command,*args,**kwargs):
            if command=='open_admission': raise ContractError('Synthetic interruption')
            return original(service,command,*args,**kwargs)
        h.transition.client=interrupted
        with self.assertRaises(ContractError): h.transition.accept()
        self.assertTrue(h.maintenance); self.assertEqual(h.processes[LABEL]['state'],'ready')
        h.transition.client=original; h.transition.recover(h.new)
        self.assertFalse(h.maintenance)

    def test_recovery_refuses_changed_instance(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
        h.processes[LABEL]['instance']='f'*32
        with self.assertRaises(ContractError): h.transition.recover(h.new)
        self.assertTrue(h.maintenance)

    def test_rollback_reuses_interrupted_pointer_creation(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
        saved=json.loads(h.journal.read_text())
        pointer=h.current.with_name('current.runtime-rollback.'+saved['revision'])
        pointer.symlink_to(h.old,target_is_directory=True)
        h.transition.rollback(h.current)
        self.assertEqual(h.current.resolve(),h.old)
        self.assertFalse(pointer.exists())
        self.assertEqual(set(h.processes),{WEB})

    def test_original_paused_state_survives_rollback(self):
        h=self.h; h.maintenance=True; h.processes[WEB]['state']='drained'
        h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
        h.transition.rollback(h.current)
        self.assertTrue(h.maintenance)
        self.assertEqual(h.processes[WEB]['state'],'drained')
        self.assertNotIn(('control',WEB,'resume'),h.events)

    def test_original_paused_state_survives_success(self):
        h=self.h; h.maintenance=True; h.processes[WEB]['state']='drained'
        h.transition.begin(h.old,h.new); h.switch(); h.transition.start(); h.transition.accept()
        self.assertTrue(h.maintenance)
        self.assertEqual(h.processes[LABEL]['state'],'drained')
        self.assertNotIn(('control',LABEL,'resume'),h.events)

    def test_stopped_before_pointer_switch_recovers_old_then_allows_new_attempt(self):
        h=self.h; h.transition.begin(h.old,h.new)
        self.assertEqual(h.processes,{})
        self.assertEqual(h.transition.recovery_mode(h.new,'b'*40,h.current),'rollback')
        h.transition.rollback(h.current)
        self.assertEqual(h.current.resolve(),h.old); self.assertEqual(set(h.processes),{WEB})
        self.assertFalse(h.maintenance)

    def test_switched_before_start_prepares_without_opening_admission(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch()
        self.assertEqual(h.processes,{})
        self.assertEqual(h.transition.recovery_mode(h.new,'b'*40,h.current),'prepare')
        h.transition.prepare_recovery(h.new)
        self.assertTrue(h.maintenance); self.assertEqual(set(h.processes),{WEB,LABEL})
        h.transition.recover(h.new); self.assertFalse(h.maintenance)

    def test_recovered_rollback_is_idempotent(self):
        h=self.h; h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
        h.transition.rollback(h.current)
        pid=h.processes[WEB]['pid']; h.events.clear()
        h.transition.rollback(h.current)
        self.assertEqual(h.processes[WEB]['pid'],pid)
        self.assertFalse(any(event[0] in ('stop','start','restore') for event in h.events))

    def test_rollback_interrupted_at_each_restoration_checkpoint_keeps_live_roles(self):
        for checkpoint in ('after_start', 'before_verified', 'after_resume', 'after_open', 'before_rolled_back'):
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory() as directory:
                h=Harness(Path(directory)); h.transition.begin(h.old,h.new); h.switch(); h.transition.start()
                original_save, original_client, original_run = h.transition.save, h.transition.client, h.run
                class Interrupted(BaseException): pass
                triggered=[False]
                def interrupt():
                    triggered[0]=True
                    raise Interrupted()
                def save():
                    phase=h.transition.data['phase']
                    if ((checkpoint=='before_verified' and phase=='rollback_verified')
                            or (checkpoint=='before_rolled_back' and phase=='rolled_back')):
                        interrupt()
                    return original_save()
                def client(service, command, *args, **kwargs):
                    value=original_client(service,command,*args,**kwargs)
                    if h.current.resolve()==h.old and ((checkpoint=='after_resume' and command=='resume')
                            or (checkpoint=='after_open' and command=='open_admission')):
                        interrupt()
                    return value
                def run(command, *services, **kwargs):
                    result=original_run(command,*services,**kwargs)
                    if checkpoint=='after_start' and command=='start' and h.current.resolve()==h.old:
                        interrupt()
                    return result
                h.transition.save=save; h.transition.client=client; h.run=run
                with self.assertRaises(Interrupted): h.transition.rollback(h.current)
                self.assertTrue(triggered[0]); pid=h.processes[WEB]['pid']
                h.transition.save=original_save; h.transition.client=original_client; h.run=original_run
                # Already reopened consumers may now own newly submitted work.
                if not h.maintenance: h.queue=h.active=1
                h.events.clear(); h.transition.rollback(h.current)
                self.assertEqual(h.processes[WEB]['pid'],pid)
                self.assertFalse(any(event[0] in ('stop','restore') for event in h.events))
                self.assertFalse(h.maintenance)
                self.assertEqual(json.loads(h.journal.read_text())['phase'],'rolled_back')

    def test_background_compatibility_repaired_before_old_restart(self):
        h=self.h; h.transition.backgrounds.mkdir()
        h.transition.begin(h.old,h.new); h.switch(); h.transition.start(); h.transition.rollback(h.current)
        self.assertEqual((h.old/'backgrounds').resolve(),h.transition.backgrounds)

    def test_external_cannot_downgrade_directly_to_unmanaged_embedded(self):
        h=self.h
        old=json.loads((h.old/'RUNTIME_TOPOLOGY.json').read_text())
        old.update(worker_mode='external',services=[WEB,LABEL])
        (h.old/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(old))
        new=json.loads((h.new/'RUNTIME_TOPOLOGY.json').read_text())
        new.update(schema=1,worker_mode='embedded',services=[WEB]); del new['runtime_protocol']
        (h.new/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(new))
        with self.assertRaises(ContractError): h.transition.begin(h.old,h.new)
        self.assertEqual(h.events,[])
        self.assertFalse(h.journal.exists())


if __name__ == '__main__': unittest.main()
