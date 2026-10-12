"""Synthetic post-accept expiry installation; never touches host systemd or PLC."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'scripts/install_release.template.sh').read_text()
function=source.split('install_diagnostic_expiry() {',1)[1].split('\n}\n',1)[0]
assert source.count('\n  install_diagnostic_expiry\n')==1
assert source.count('\ninstall_diagnostic_expiry\n')==1
accepted=source.index('  deployment_committed=1')
assert accepted < source.index('  install_diagnostic_expiry',accepted) < source.index('already-installed=true',accepted)
for mode in ['absent','managed','unmanaged','old-package']:
 with tempfile.TemporaryDirectory(prefix='plc-expiry-install-') as temporary:
  home=Path(temporary);units=home/'systemd';units.mkdir();target=home/'release';(target/'deploy').mkdir(parents=True)
  bin=home/'bin';bin.mkdir();calls=home/'calls'
  systemctl=bin/'systemctl';systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n');systemctl.chmod(0o755)
  names=['vantaline-plc-diagnostics-cleanup.service','vantaline-plc-diagnostics-cleanup.timer']
  if mode!='old-package':
   for name in names:(target/'deploy'/name).write_bytes((ROOT/'deploy'/name).read_bytes())
  if mode=='managed':
   for name in names:(units/name).write_text('# VantaLine managed PLC diagnostic expiry v1\nold\n')
  if mode=='unmanaged':(units/names[0]).write_text('unmanaged must remain\n')
  scoped=function.replace('/etc/systemd/system',str(units))
  script='install_diagnostic_expiry() {'+scoped+'\n}\ninstall_diagnostic_expiry\n'
  result=subprocess.run(['bash','-euo','pipefail','-c',script],env={**os.environ,'PATH':str(bin)+':'+os.environ['PATH'],'CALLS':str(calls),'target':str(target)},capture_output=True,text=True)
  assert result.returncode==0,(mode,result.stderr)
  observed=calls.read_text() if calls.exists() else ''
  if mode in ['absent','managed']:
   for name in names:assert (units/name).read_bytes()==(target/'deploy'/name).read_bytes()
   assert 'enable --now vantaline-plc-diagnostics-cleanup.timer' in observed
   assert 'vantaline.service' not in observed and 'restart' not in observed
  elif mode=='unmanaged':
   assert (units/names[0]).read_text()=='unmanaged must remain\n' and not (units/names[1]).exists() and not observed
  else:assert not list(units.iterdir()) and not observed
print('PASS expiry post-accept/same-release paths, managed activation, unmanaged retention and old-package no-op; no production restart')
