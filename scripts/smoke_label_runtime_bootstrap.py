"""Private-file bootstrap wiring with no Web application import or external service."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.label_inspection import runtime
from local_inspection_service.runtime.configuration import ConfigurationSnapshot
from local_inspection_service.runtime.label_identity import RuntimeUnavailable


class Bootstrap(unittest.TestCase):
    def test_config_applied_before_independent_factories_and_no_web_import(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            root=Path(directory)
            snapshot=ConfigurationSnapshot.capture({'VANTALINE_DATA_STORE':'postgres','DATABASE_URL':'synthetic',
                'VANTALINE_LABEL_INSPECTION_ENABLED':'true'},root)
            config=root/'config.json';config.write_bytes(snapshot._payload);config.chmod(0o600)
            (root/'VERSION.json').write_text(json.dumps({'git_commit':'a'*40,'release':'v2026.10.1'}))
            manifest={'schema':2,'runtime_protocol':1,'git_commit':'a'*40,'worker_mode':'external',
                'services':['vantaline','vantaline-label-worker']}
            (root/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(manifest))
            actual=ConfigurationSnapshot.read_worker
            events=[]
            factory=SimpleNamespace(selection=lambda:SimpleNamespace(repository='control'),clear=lambda:None)
            def controls():
                assert os.environ['DATABASE_URL']=='synthetic'
                events.append('control factory')
                return factory
            with patch.object(runtime.ConfigurationSnapshot,'read_worker',side_effect=lambda path,**kw:actual(path,owner=os.getuid(),**kw)), \
                    patch.object(runtime,'create_control_factory',side_effect=controls), \
                    patch.object(runtime,'build_runtime_repository',return_value=SimpleNamespace(repository='business')) as build, \
                    patch.object(runtime,'LabelProcess',side_effect=lambda *args:args):
                args=runtime.bootstrap(config,root=root,current=root)
                identity,configuration,directory,business,control=args
                assert identity.mode=='external' and identity.config_revision==snapshot.revision
                assert directory==root and configuration==snapshot
                assert build.call_count==0
                assert business.repository()=='business' and control.repository()=='control'
                assert build.call_count==1 and events==['control factory']
                manifest.update(worker_mode='embedded',services=['vantaline'])
                (root/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(manifest))
                with self.assertRaises(RuntimeUnavailable):runtime.bootstrap(config,root=root,current=root)
            self.assertNotIn('local_inspection_service.server',sys.modules)


if __name__=='__main__':unittest.main()
