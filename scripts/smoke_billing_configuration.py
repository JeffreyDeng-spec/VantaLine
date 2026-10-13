"""Private operator configuration; synthetic keys and no supplier/network I/O."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.analytics.billing.configuration import ACCOUNT_ENV, BillingConfiguration
from local_inspection_service.analytics.billing.service import BillingService
from local_inspection_service.analytics.billing.types import BillingError


class ConfigurationContracts(unittest.TestCase):
    def setUp(self):
        self.home=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.values={};self.secret=Mock(return_value='')
        self.configuration=BillingConfiguration(self.values,self.home,self.secret)
        self.accounts=[{'provider':'runpod','payer_id':'synthetic-payer','key_ref':'RUNPOD_API_KEY','currency':'USD'}]

    def write(self,value):
        self.configuration.path.write_text(json.dumps(value))
        self.configuration.path.chmod(0o600)

    def test_explicit_environment_priority_live_private_file_and_no_work(self):
        self.assertEqual(self.configuration.environment(),{})
        self.write(self.accounts)
        repository=Mock();repository.latest.return_value=None;repository.sync.return_value=None
        reader=Mock()
        service=BillingService({},repository,self.configuration.secret,reader=reader,account_environment=self.configuration.environment)
        self.assertTrue(any(p.payer_id=='synthetic-payer' for p in service.configured()))
        service.overview();self.assertFalse(repository.request.called);self.assertEqual(reader.mock_calls,[])
        self.secret.assert_not_called()
        self.write([{**self.accounts[0],'payer_id':'replacement-payer'}])
        self.assertTrue(any(p.payer_id=='replacement-payer' for p in service.configured()))
        self.values[ACCOUNT_ENV]='[]'
        self.assertTrue(all(p.pending for p in service.configured()))
        self.values[ACCOUNT_ENV]=''
        with self.assertRaises(BillingError):service.configured()

    def test_public_symlink_hardlink_fifo_oversize_and_duplicate_rejection(self):
        for mode in ('public','symlink','hardlink','fifo','oversize','duplicate'):
            self.write(self.accounts)
            path=self.configuration.path
            if mode=='public':path.chmod(0o644)
            elif mode=='symlink':
                target=self.home/'symlink-target';path.replace(target);path.symlink_to(target)
            elif mode=='hardlink':os.link(path,self.home/'hardlink-copy')
            elif mode=='fifo':path.unlink();os.mkfifo(path,0o600)
            elif mode=='oversize':path.write_text(' '*65537)
            else:path.write_text('[{"provider":"runpod","provider":"ali"}]')
            with self.subTest(mode=mode),self.assertRaises(BillingError):self.configuration.environment()
            path.unlink()

    def test_cos_references_are_explicit_private_and_tencent_only(self):
        self.values['CREDENTIALS_DIRECTORY']=str(self.home)
        cos=self.home/'cos-credentials.json'
        cos.write_text(json.dumps({'COS_SECRET_ID':'synthetic-id','COS_SECRET_KEY':'synthetic-key'}));cos.chmod(0o600)
        self.assertEqual(self.configuration.secret('unrelated-reference'),'')
        self.assertEqual(self.configuration.secret('VANTALINE_BILLING_COS_SECRET_ID'),'synthetic-id')
        self.assertEqual(self.configuration.secret('VANTALINE_BILLING_COS_SECRET_KEY'),'synthetic-key')
        candidate={'provider':'tencent','payer_id':'synthetic-payer','key_ref':'VANTALINE_BILLING_COS_SECRET_ID','secret_ref':'VANTALINE_BILLING_COS_SECRET_KEY'}
        self.write([candidate]);self.configuration.environment()
        self.write([{**candidate,'provider':'ali'}])
        with self.assertRaises(BillingError):self.configuration.environment()
        cos.write_text(json.dumps({'COS_SECRET_ID':'synthetic-id','COS_SECRET_KEY':'synthetic-key','COS_SESSION_TOKEN':'temporary'}))
        with self.assertRaises(BillingError) as exc:self.configuration.secret('VANTALINE_BILLING_COS_SECRET_ID')
        self.assertEqual(exc.exception.code,'billing_temporary_credential_unsupported')
        cos.chmod(0o644)
        with self.assertRaises(BillingError):self.configuration.secret('VANTALINE_BILLING_COS_SECRET_ID')


if __name__=='__main__':unittest.main()
