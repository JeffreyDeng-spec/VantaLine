"""Reversible runtime transition, invoked only by the installed root controller.

The caller owns the production release lock and immutable package verification.
This module owns service identity, admission/drain fencing and unit rollback.
"""
from dataclasses import asdict
import json
import os
from pathlib import Path
import pwd
import tempfile
import time
import uuid

from release_runtime_contract import ContractError, ConsumerState, Topology, WEB, LABEL, read_object, sync_directory
from release_runtime_client import request
from release_services import ServiceCommands, UnitChanges, SYSTEMD


class RuntimeTransition:
    def __init__(self, journal: Path, *, commands=None, units=None, client=request,
                 clock=time.monotonic, sleep=time.sleep, uid=None,
                 backgrounds=Path('/opt/vantaline/shared/data/backgrounds')):
        self.journal = journal
        self.commands = commands or ServiceCommands()
        self.units = units or UnitChanges(SYSTEMD, self.commands)
        self.client = client
        self.clock = clock
        self.sleep = sleep
        self.uid = pwd.getpwnam('vantaline').pw_uid if uid is None else uid
        self.data = None
        self.backgrounds = backgrounds

    def save(self):
        descriptor, temporary = tempfile.mkstemp(prefix='.runtime-', dir=self.journal.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                json.dump(self.data, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.journal)
            sync_directory(self.journal.parent)
        finally:
            if os.path.lexists(temporary):
                os.unlink(temporary)

    def load(self):
        self.data = read_object(self.journal, limit=65536)

    @staticmethod
    def identity(directory: Path):
        version = read_object(directory / 'VERSION.json')
        commit, release = version.get('git_commit'), version.get('release')
        manifest = directory / 'RUNTIME_TOPOLOGY.json'
        value = read_object(manifest) if manifest.exists() else {
            'schema': 1, 'git_commit': commit, 'worker_mode': 'embedded', 'services': [WEB]}
        topology = Topology.parse(value, commit)
        if not isinstance(release, str) or directory.name != release:
            raise ContractError('Release directory identity mismatch')
        return {'directory': str(directory), 'release': release, 'topology': asdict(topology)}

    def state(self, identity, service, command='status', *, expected=None, revision=None, deadline=None):
        topology = Topology(**identity['topology'])
        def remaining_budget():
            remaining = 5 if deadline is None else min(5, deadline-self.clock())
            if remaining <= 0:
                raise ContractError('Runtime transition budget expired')
            return remaining
        pid_text = self.commands.property(service, 'MainPID', timeout=remaining_budget())
        if not pid_text.isdecimal() or int(pid_text) <= 0:
            raise ContractError('Runtime service is unavailable')
        pid = int(pid_text)
        remaining = remaining_budget()
        value = self.client(service, command, self.data['revision'], uid=self.uid,
                            pid=pid, timeout=remaining)
        if self.commands.property(service, 'MainPID', timeout=remaining_budget()) != pid_text:
            raise ContractError('Runtime process changed during transition')
        return ConsumerState.verify(value, topology=topology, release=identity['release'],
                                    service=service, pid=pid, now=self.clock(),
                                    expected_instance=expected, control_revision=revision)

    def ready(self, identity, *, previous_instances=None, deadline=None, require_paused=False):
        topology = Topology(**identity['topology'])
        if not topology.runtime_protocol:
            return {}
        instances, revisions = {}, set()
        for service in topology.services:
            state = self.state(identity, service, deadline=deadline)
            state.require_available()
            expected_config = self.data.get('expected_config')
            if expected_config is not None and state.config_revision != expected_config:
                raise ContractError('Runtime configuration changed during transition')
            if require_paused and topology.runtime_protocol:
                if not state.maintenance or (service == topology.consumer_service and state.state != 'drained'):
                    raise ContractError('Candidate consumer activated before acceptance')
            if previous_instances and state.instance == previous_instances.get(service):
                raise ContractError('Previous process still owns the runtime')
            instances[service] = state.instance
            revisions.add(state.config_revision)
        if len(revisions) != 1:
            raise ContractError('Web and worker runtime configuration mismatch')
        return instances

    def pause(self, identity, instances, *, deadline, drain_queue=True):
        topology = Topology(**identity['topology'])
        web = self.state(identity, WEB, 'close_admission', expected=instances[WEB],
                         revision=self.data['revision'], deadline=deadline)
        if not web.maintenance:
            raise ContractError('Label admission is not fenced')
        if drain_queue:
            # Normal forward switches finish the accepted queue before pausing.
            while True:
                web = self.state(identity, WEB, expected=instances[WEB],
                                 revision=self.data['revision'], deadline=deadline)
                if not web.maintenance:
                    raise ContractError('Label admission fence changed')
                if web.queued_runs == 0 and web.active_runs == 0:
                    break
                if deadline-self.clock() <= 0:
                    raise ContractError('Label queue did not drain')
                self.sleep(min(.25, max(0, deadline-self.clock())))
        consumer = topology.consumer_service
        state = self.state(identity, consumer, 'pause', expected=instances[consumer],
                           revision=self.data['revision'], deadline=deadline)
        # Rollback and an already-paused predecessor retain queued rows. Never
        # resume an unaccepted candidate merely to execute its paid backlog.
        while state.state == 'draining' or (state.state == 'drained' and state.active_runs):
            self.sleep(min(.1, max(0, deadline-self.clock())))
            state = self.state(identity, consumer, expected=instances[consumer],
                               revision=self.data['revision'], deadline=deadline)
        state.require_drained()
        if not state.maintenance or state.active_runs or (drain_queue and state.queued_runs):
            raise ContractError('Label work appeared after drain acknowledgement')

    def restore_admission(self, identity, instances, *, deadline):
        topology = Topology(**identity['topology'])
        consumer = topology.consumer_service
        command = 'pause' if self.data['previous_paused'] else 'resume'
        state = self.state(identity, consumer, command, expected=instances[consumer],
                           revision=self.data['revision'], deadline=deadline)
        if self.data['previous_paused']:
            state.require_drained()
        else:
            state.require_ready()
        if not self.data['previous_maintenance']:
            state = self.state(identity, WEB, 'open_admission', expected=instances[WEB],
                               revision=self.data['revision'], deadline=deadline)
            state.require_available()
            if state.maintenance:
                raise ContractError('Label admission did not reopen')

    def begin(self, previous: Path, target: Path):
        if self.journal.exists():
            raise ContractError('Unfinished runtime transition requires recovery')
        old, new = self.identity(previous), self.identity(target)
        old_topology, new_topology = Topology(**old['topology']), Topology(**new['topology'])
        if old_topology.mode == 'external' and not new_topology.runtime_protocol:
            raise ContractError('External runtime downgrade requires a managed embedded bridge')
        if new_topology.mode == 'external' and not old_topology.runtime_protocol:
            raise ContractError('Embedded runtime bridge must be installed first')
        if old_topology.mode == 'embedded' and self.commands.property(LABEL, 'MainPID') != '0':
            raise ContractError('Unexpected separate worker is running')
        self.data = {'schema': 1, 'revision': uuid.uuid4().hex, 'old': old, 'new': new,
                     'units': self.units.capture(), 'units_changed': False, 'stop_started': False,
                     'previous_maintenance': False, 'previous_paused': False, 'old_instances': {},
                     'new_instances': {}, 'expected_config': None, 'phase': 'prepared'}
        deadline = self.clock()+500
        if old_topology.runtime_protocol:
            self.data['old_instances'] = self.ready(old, deadline=deadline)
            old_state = self.state(old, WEB, deadline=deadline)
            self.data['previous_maintenance'] = old_state.maintenance
            self.data['expected_config'] = old_state.config_revision
            self.data['previous_paused'] = self.state(old, old_topology.consumer_service, deadline=deadline).state == 'drained'
        if new_topology.mode == 'external':
            old_state = self.state(old, WEB, deadline=deadline)
            if old_state.config_revision is None:
                raise ContractError('Shared runtime configuration must be activated first')
        # Persist recovery evidence before admission, units, or services change.
        self.save()
        if old_topology.runtime_protocol:
            self.pause(old, self.data['old_instances'], deadline=deadline,
                       drain_queue=not self.data['previous_paused'])
        self.data['units_changed'] = True
        self.save()
        self.units.install(new_topology, deadline=deadline, stopping_services=old_topology.services)
        self.data['stop_started'] = True
        self.data['phase'] = 'stopping'
        self.save()
        self.commands.stop_all(old_topology.services, deadline=deadline)
        self.data['phase'] = 'stopped'
        self.save()
        if new_topology.mode == 'embedded' and self.commands.property(LABEL, 'LoadState') == 'loaded':
            self.commands.run('disable', LABEL)

    def start(self):
        self.load()
        identity = self.data['new']
        topology = Topology(**identity['topology'])
        self.data['phase'] = 'starting'
        self.save()
        self.commands.run('start', WEB)
        deadline = self.clock()+60
        if topology.mode == 'external':
            while True:
                try:
                    state = self.state(identity, WEB, deadline=deadline)
                    state.require_available()
                    if state.config_revision != self.data['expected_config'] or not state.maintenance:
                        raise ContractError('Candidate Web configuration/admission mismatch')
                    break
                except ContractError:
                    if self.clock() >= deadline:
                        raise ContractError('Candidate Web did not become ready') from None
                    self.sleep(min(.25, max(0, deadline-self.clock())))
            self.commands.run('start', LABEL)
        while True:
            try:
                instances = self.ready(identity, previous_instances=self.data['old_instances'], deadline=deadline, require_paused=True)
                break
            except ContractError:
                if self.clock() >= deadline:
                    raise ContractError('Candidate runtime did not become ready') from None
                self.sleep(min(.25, max(0, deadline-self.clock())))
        self.data['new_instances'] = instances
        self.data['phase'] = 'verified'
        self.save()
        # Admission opens only after the shell's public HTTP/assets checks.

    def accept(self):
        self.load()
        topology = Topology(**self.data['new']['topology'])
        if topology.runtime_protocol:
            instances = self.ready(self.data['new'], deadline=self.clock()+15)
            if instances != self.data['new_instances']:
                raise ContractError('Candidate runtime changed before acceptance')
            self.restore_admission(self.data['new'], instances, deadline=self.clock()+15)
        self.data['phase'] = 'accepted'
        self.save()

    def recovery_mode(self, target: Path, commit: str, current=Path('/opt/vantaline/current')):
        self.load()
        if self.data['new']['directory'] != str(target) or self.data['new']['topology']['commit'] != commit:
            raise ContractError('Recovery request differs from journal')
        if (self.data['phase'] in ('rolling_back', 'rollback_starting', 'rollback_verified', 'rolled_back', 'prepared', 'stopping')
                or current.resolve() != target):
            return 'rollback'
        if self.data['phase'] in ('stopped', 'starting', 'verified', 'accepted'):
            return 'prepare'
        raise ContractError('Unknown runtime recovery phase')

    def prepare_recovery(self, target: Path):
        self.load()
        if self.identity(target) != self.data['new']:
            raise ContractError('Recovery package differs from journal')
        if self.data['phase'] in ('stopped', 'starting'):
            self.start()
        elif self.data['phase'] not in ('verified', 'accepted'):
            raise ContractError('Transition cannot be resumed from this phase')
        # No admission change here. Public HTTP acceptance still belongs to
        # the installed shell and precedes recover()/accept().

    def recover(self, target: Path):
        self.load()
        if self.identity(target) != self.data['new']:
            raise ContractError('Recovery package differs from journal')
        if self.data['phase'] in ('stopped', 'starting'):
            self.start()
        elif self.data['phase'] not in ('verified', 'accepted'):
            raise ContractError('Transition cannot be committed from this phase')
        # Repeating accept is intentional: it validates journal-bound instances
        # and finishes a resume/open that was interrupted before journal save.
        self.accept()

    def rollback(self, current: Path):
        self.load()
        old, new = self.data['old'], self.data['new']
        if current.resolve() not in (Path(old['directory']), Path(new['directory'])):
            raise ContractError('Release pointer changed outside this transition')
        old_topology, new_topology = Topology(**old['topology']), Topology(**new['topology'])
        deadline = self.clock()+500
        if self.data['phase'] in ('rollback_starting', 'rollback_verified', 'rolled_back'):
            self.finish_rollback(current, deadline=deadline)
            return
        self.data['phase'] = 'rolling_back'
        self.save()
        if not self.data['stop_started']:
            if self.data['units_changed']:
                self.units.restore(self.data['units'])
            self.data['phase'] = 'rollback_verified'
            self.data['recovered_instances'] = self.data['old_instances']
            self.save()  # Bind live roles before restoring any admission.
            self.finish_rollback(current, deadline=deadline)
            return
        if current.resolve() == Path(new['directory']):
            if new_topology.runtime_protocol:
                live = [service for service in new_topology.services
                        if self.commands.property(service, 'MainPID') != '0']
                if new_topology.consumer_service in live:
                    instances = {service: self.state(new, service, deadline=deadline).instance for service in live}
                    self.pause(new, instances, deadline=deadline, drain_queue=False)
            self.commands.stop_all(new_topology.services, deadline=deadline)
        else:
            self.commands.stop_all(old_topology.services, deadline=deadline)
        # Preserve the original installer's legacy background compatibility
        # repair, after all candidate processes stop and before old startup.
        legacy_backgrounds = Path(old['directory'])/'backgrounds'
        if self.backgrounds.is_dir() and not self.backgrounds.is_symlink():
            if not os.path.lexists(legacy_backgrounds):
                try:
                    legacy_backgrounds.symlink_to(self.backgrounds, target_is_directory=True)
                except OSError:
                    os.rename(self.backgrounds, legacy_backgrounds)
            if not legacy_backgrounds.is_dir():
                raise ContractError('Previous background storage is unavailable')
        self.units.restore(self.data['units'])
        temporary = current.with_name('current.runtime-rollback.'+self.data['revision'])
        try:
            temporary.symlink_to(old['directory'], target_is_directory=True)
        except FileExistsError:
            if not temporary.is_symlink() or os.readlink(temporary) != old['directory']:
                raise ContractError('Unexpected rollback pointer state') from None
        os.replace(temporary, current)
        sync_directory(current.parent)
        # Record the restored pointer/units BEFORE starting an old process. A
        # retry can repeat systemctl start without stopping an already-live role.
        self.data['phase'] = 'rollback_starting'
        self.save()
        self.finish_rollback(current, deadline=deadline)

    def finish_rollback(self, current: Path, *, deadline):
        old = self.data['old']
        topology = Topology(**old['topology'])
        if current.resolve() != Path(old['directory']):
            raise ContractError('Recovered release pointer changed')
        if self.data['phase'] == 'rollback_starting':
            for service in topology.services:
                self.commands.run('start', service)
            while True:
                try:
                    instances = self.ready(old, previous_instances=self.data['old_instances'], deadline=deadline)
                    break
                except ContractError:
                    if self.clock() >= deadline:
                        raise ContractError('Previous runtime did not recover') from None
                    self.sleep(min(.25, max(0, deadline-self.clock())))
            self.data['recovered_instances'] = instances
            self.data['phase'] = 'rollback_verified'
            self.save()  # Resume/open may now be retried without stopping roles.
        if self.data['phase'] not in ('rollback_verified', 'rolled_back'):
            raise ContractError('Rollback cannot finish from this phase')
        instances = self.ready(old, deadline=deadline)
        if instances != self.data.get('recovered_instances', {}):
            raise ContractError('Recovered runtime instance changed')
        if topology.runtime_protocol:
            self.restore_admission(old, instances, deadline=deadline)
        self.data['phase'] = 'rolled_back'
        self.save()
