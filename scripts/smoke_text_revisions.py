"""Revision publication, public projection and bounded diagnostic contracts."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from fastapi import HTTPException
from local_inspection_service.text_inspection.revisions import RevisionRecords, TextRevisions, expected_revision, confirmed_snapshot
from local_inspection_service.text_inspection.projection import public_record
from local_inspection_service.text_inspection import diagnostics
from local_inspection_service.text_inspection.preparation_policy import snapshot

ROOT='--root' in sys.argv
sys.argv=[arg for arg in sys.argv if arg!='--root']


class Fixture:
    def __init__(self):
        self.events=[];self.saved=[];self.existing=[];self.failure='';self.snapshot_value=[{'id':'new','sha256':'new'}]
        self.service=TextRevisions(RevisionRecords(self.load,self.save),self.snapshot)
        self.standard=dict(id='standard',owner_user_id='alice',status='confirmed',revision_number=0,confirmed_assets=[{'id':'old','nested':[]}])
    def snapshot(self,assets):self.events.append(('snapshot',assets));return self.snapshot_value
    def load(self,kind):self.events.append(('load',kind));return self.existing
    def save(self,kind,value,*,insert_only=False):
        self.events.append(('save',kind,value,insert_only))
        if self.failure==value['action']+'-false':return False
        if self.failure==value['action']+'-raise':raise RuntimeError('save failed')
        self.saved.append(copy.deepcopy(value));return True
    def apply(self,action='edit'):
        return self.service.apply(self.standard,[],action=action,asset_id='asset',now=123)


class RevisionContracts(unittest.TestCase):
    def test_baseline_publication_trace_and_shared_snapshot_lists(self):
        f=Fixture();result=f.apply()
        self.assertTrue(all(event[1] == 'revisions' and event[3] is True for event in f.events if event[0] == 'save'))
        self.assertEqual([e[0] for e in f.events],['snapshot','load','save','save'])
        self.assertEqual([r['action'] for r in f.saved],['baseline','edit'])
        baseline=f.events[2][2];self.assertEqual(baseline['id'],'rev_baseline_standard')
        self.assertEqual(baseline['confirmed_asset_ids'],['old']);self.assertEqual(result['revision_number'],2)
        self.assertIs(result,f.events[3][2]);self.assertIs(result['confirmed_assets'],f.snapshot_value)
        self.assertIs(f.standard['confirmed_assets'],result['confirmed_assets'])
        self.assertIs(f.standard['confirmed_asset_ids'],result['confirmed_asset_ids'])
        self.assertEqual(f.standard['asset_count'],1)
        for value,action,number in [('0','confirm',1),('-2','edit',-1),('4','edit',5)]:
            f=Fixture();f.standard['revision_number']=value;result=f.apply(action)
            self.assertEqual(result['revision_number'],number);self.assertEqual([e[0] for e in f.events],['snapshot','save'])

    def test_baseline_conflicts_and_partial_failure_are_not_new_transactions(self):
        for mode in ['different','baseline-false','baseline-raise']:
            f=Fixture();before=copy.deepcopy(f.standard)
            if mode=='different':f.existing=[dict(id='rev_baseline_standard',standard_id='standard',confirmed_assets=[])]
            else:f.failure=mode
            with self.assertRaises((HTTPException,RuntimeError)) as caught:f.apply()
            if isinstance(caught.exception,HTTPException):self.assertEqual(caught.exception.status_code,409)
            self.assertEqual(f.standard,before);self.assertEqual(f.saved,[])
            self.assertEqual([event[0] for event in f.events], ['snapshot','load'] if mode=='different' else ['snapshot','load','save'])
            self.assertTrue(all(event[1]=='revisions' and event[3] is True for event in f.events if event[0]=='save'))
        f=Fixture();f.existing=[dict(id='rev_baseline_standard',standard_id='standard',confirmed_assets=copy.deepcopy(f.standard['confirmed_assets']))]
        f.apply();self.assertEqual(len(f.saved),1);self.assertEqual(f.saved[0]['action'],'edit')
        f=Fixture();f.failure='edit-raise'
        with self.assertRaisesRegex(RuntimeError,'save failed'):f.apply()
        self.assertEqual(f.saved[0]['action'],'baseline');self.assertEqual(f.standard['revision_number'],2)
        self.assertEqual([e[0] for e in f.events],['snapshot','load','save','save'])
        self.assertTrue(all(e[1]=='revisions' and e[3] is True for e in f.events if e[0]=='save'))
        f=Fixture();f.failure='edit-false';result=f.apply()
        self.assertEqual(result['revision_number'],2);self.assertEqual(f.standard['current_revision_id'],result['id'])
        self.assertEqual([r['action'] for r in f.saved],['baseline'])
        self.assertEqual([e[0] for e in f.events],['snapshot','load','save','save'])
        self.assertTrue(all(e[1]=='revisions' and e[3] is True for e in f.events if e[0]=='save'))

    def test_expected_revision_and_confirmed_snapshot_contract(self):
        for value,result in [(None,None),('',None),(0,0),('0002',2),('2',2),(12,12)]:self.assertEqual(expected_revision(value),result)
        for value in [True,False,-1,'-1','1.0',1.0,' 1','1 ',[],{}]:
            with self.assertRaises(HTTPException) as caught:expected_revision(value)
            self.assertEqual(caught.exception.status_code,400)
        assets=[dict(id='asset',ordinal=1,status='candidate',sha256='source')]
        self.assertEqual(confirmed_snapshot(assets),snapshot(assets))

    def test_projection_private_fields_copy_and_legacy_url_rules(self):
        record=dict(id='asset/a b',asset_kind='label_candidate',standard_id='standard',model_profiles={'image':{'version':1}},
            source_path='/private',source_preview_path='/private',media_path='/private',annotated_path='/private',reference_overlay_path='/private',
            diagnostics={'model_audits':[{'files':{'request':{'path':'/private','sha256':'hash'}}}], 'rereads':[{'input_path':'/private','state':'unknown'}]})
        record['nested']={'secret_ref':'secret','proxy_ref':'proxy','profile_snapshot':{'secret_ref':'deep'},'items':[{'model_profiles':{'secret_ref':'hidden'},'secret_ref':'other','keep':'visible'}]}
        before=copy.deepcopy(record);result=public_record(record)
        self.assertEqual(result['nested'],{'items':[{'keep':'visible'}]})
        self.assertEqual(record,before);self.assertNotIn('/private',json.dumps(result));self.assertNotIn('model_profiles',result)
        self.assertEqual(result['content_url'],'/api/text-inspection/assets/asset/a%20b/content')
        record.update(preparation_required=True,preparation_previous_snapshot={'id':'previous'})
        self.assertTrue(public_record(record)['comparison_ready'])
        record['active_preparation']={'id':'raw/id','elements':[]}
        result=public_record(record);self.assertFalse(result['comparison_ready']);self.assertIn('/raw/id/clean',result['content_url'])
        self.assertIn('comparison_unavailable_reason',result)
        record['active_preparation']={'elements':[{'state':'keep','type':'text','text':'x'}]}
        with self.assertRaises(KeyError):public_record(record)

    def test_diagnostic_bounds_redaction_events_and_provider_values(self):
        value={'api-key':'secret','nested':{'custom_token':'secret','safe':'data:image/png;base64,abc'},'url':'data:private'}
        clean=diagnostics.diagnostic_value(value)
        self.assertEqual(clean['api-key'],'<redacted>');self.assertEqual(clean['nested']['custom_token'],'<redacted>')
        self.assertTrue(clean['nested']['safe'].startswith('<embedded-media:'));self.assertTrue(clean['url'].startswith('<embedded-media:'))
        self.assertEqual(diagnostics.diagnostic_value('kept',depth=6),'kept');self.assertEqual(diagnostics.diagnostic_value('lost',depth=7),'<depth-limit>')
        self.assertEqual(len(diagnostics.diagnostic_value('x'*9000)),8192)
        self.assertEqual(len(diagnostics.diagnostic_value(tuple(range(130)))),120)
        self.assertEqual(len(diagnostics.diagnostic_value({str(i):i for i in range(130)})),120)
        self.assertEqual(diagnostics.diagnostic_value({'x'*120+'_token':'kept'}),{'x'*120:'kept'})
        provider=diagnostics.provider_diagnostics({'ok':False,'latency_ms':0,'response_preview':'fixture','parsed':[]},{'model':'configured'})
        self.assertIs(provider['ok'],False);self.assertEqual(provider['latency_ms'],0);self.assertEqual(provider['parsed_response'],{})
        record={'request_received_at_ms':2000}
        with patch.object(diagnostics.time,'time',return_value=1):
            diagnostics.diagnostic_event(record,'stage','status',details={});diagnostics.diagnostic_event(record,'stage','status',details={'token':'secret'})
        self.assertEqual(record['events'][0]['elapsed_ms'],0);self.assertNotIn('details',record['events'][0]);self.assertEqual(record['events'][1]['details']['token'],'<redacted>')

    def test_image_diagnostics_and_late_logger_hash_only_error_message(self):
        logger=Mock();current=[logger];digest=lambda b:hashlib.sha256(b).hexdigest()
        service=diagnostics.TextDiagnostics(lambda:digest,lambda:current[0])
        stream=io.BytesIO();Image.new('RGB',(100,200),'white').save(stream,format='PNG');blob=stream.getvalue()
        metadata=service.image_diagnostics(blob,source_format='PNG',mime_type='image/png')
        self.assertEqual((metadata['width'],metadata['height'],metadata['sha256']),(100,200,digest(blob)))
        self.assertEqual(service.image_diagnostics(b'broken',source_format='unknown',mime_type='fixture')['width'],0)
        record={'id':'record','diagnostics':{'failure':{'message':'private customer text','stage':'model','error_type':'fixture'},'request_received_at_ms':1000}}
        current[0]=Mock()
        with patch.object(diagnostics.time,'time',return_value=2):service.write_server_diagnostic(record)
        logger.info.assert_not_called();current[0].info.assert_called_once()
        text=current[0].info.call_args.args[1];self.assertNotIn('private customer text',text)
        self.assertEqual(json.loads(text)['error_message_sha256'],digest(b'private customer text'))
        self.assertEqual(json.loads(text)['elapsed_ms'],1000)


    def test_revision_first_failure_preserves_exception_and_partial_state(self):
        for mode in ('load','baseline','edit'):
            with self.subTest(mode=mode):
                f=Fixture();before=copy.deepcopy(f.standard);events=[]
                error=RuntimeError('unknown '+mode+' outcome');failure=Mock(side_effect=[error,[] if mode=='load' else True])
                def load(kind):
                    events.append(('load',kind))
                    return failure() if mode=='load' else f.load(kind)
                def save(kind,value,*,insert_only=False):
                    events.append(('save',value['action'],value,insert_only))
                    return failure() if value['action']==mode else f.save(kind,value,insert_only=insert_only)
                f.service.records=RevisionRecords(load,save)
                with self.assertRaises(RuntimeError) as caught:f.apply()
                self.assertIs(caught.exception,error);failure.assert_called_once_with()
                self.assertEqual([e[:2] for e in events],[('load','revisions')]+([] if mode=='load' else [('save','baseline')])+([('save','edit')] if mode=='edit' else []))
                self.assertTrue(all(e[3] is True for e in events if e[0]=='save'))
                if mode!='edit':self.assertEqual(f.standard,before);self.assertEqual(f.saved,[])
                else:
                    failed_revision=events[-1][2]
                    self.assertEqual([value['action'] for value in f.saved],['baseline'])
                    self.assertEqual(f.standard['revision_number'],2)
                    self.assertEqual(f.standard['current_revision_id'],failed_revision['id'])
                    self.assertIs(f.standard['confirmed_assets'],failed_revision['confirmed_assets'])
                    self.assertIs(f.standard['confirmed_assets'],f.snapshot_value)
                    self.assertIs(f.standard['confirmed_asset_ids'],failed_revision['confirmed_asset_ids'])
                    self.assertNotIn(failed_revision,f.saved)

    def test_diagnostic_first_failure_has_no_retry_or_later_output(self):
        for mode in ('image-digest','failure-digest','logger','info'):
            with self.subTest(mode=mode):
                events=[];error=RuntimeError('unknown '+mode+' outcome');logger=Mock()
                failure=Mock(side_effect=[error,logger if mode=='logger' else 'hash' if mode.endswith('digest') else None])
                def digest(data):
                    events.append('digest')
                    return failure() if mode.endswith('digest') else 'hash'
                def get_logger():
                    events.append('logger');return failure() if mode=='logger' else logger
                def info(*args):events.append('info');return failure()
                logger.info.side_effect=info
                original=diagnostics.diagnostic_value
                def serialize(value,**kwargs):events.append('serialize');return original(value,**kwargs)
                def clock():events.append('clock');return 2
                service=diagnostics.TextDiagnostics(lambda:digest,get_logger)
                record={'id':'record','diagnostics':{'failure':{'message':'synthetic private text'},'request_received_at_ms':1000}}
                with patch.object(diagnostics.time,'time',side_effect=clock),patch.object(diagnostics,'diagnostic_value',side_effect=serialize):
                    with self.assertRaises(RuntimeError) as caught:
                        if mode=='image-digest':service.image_diagnostics(b'broken',source_format='unknown',mime_type='fixture')
                        else:service.write_server_diagnostic(record)
                self.assertIs(caught.exception,error);failure.assert_called_once_with()
                expected=['digest'] if mode.endswith('digest') else ['digest','clock','logger']
                if mode=='info':
                    # Redaction recursively visits payload values before one output.
                    self.assertEqual(events[:3],expected);self.assertTrue(all(e=='serialize' for e in events[3:-1]))
                    self.assertEqual(events[-1],'info');logger.info.assert_called_once()
                    payload=json.loads(logger.info.call_args.args[1])
                    self.assertEqual((payload['inspection_id'],payload['error_message_sha256'],payload['elapsed_ms']),('record','hash',1000))
                    self.assertNotIn('synthetic private text',logger.info.call_args.args[1])
                else:self.assertEqual(events,expected);logger.info.assert_not_called()
        untouched=Mock(side_effect=AssertionError('absent message must not resolve digest'))
        logger=Mock();diagnostics.TextDiagnostics(untouched,lambda:logger).write_server_diagnostic({})
        untouched.assert_not_called();logger.info.assert_called_once()

    @unittest.skipUnless(ROOT,'requires full application runtime')
    def test_application_digest_capture_and_missing_callback_order(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'local_inspection_service/static').mkdir(parents=True)
            os.environ.update(LOCAL_INSPECTION_ROOT=folder,VANTALINE_DATA_STORE='json',VANTALINE_LABEL_INSPECTION_ENABLED='false',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',YOLO_AUTOINSTALL='false')
            from local_inspection_service import server
            for mode in ('capture','missing'):
                events=[];logger=Mock()
                def digest_a(data):events.append('A');return 'hashA'
                def digest_b(data):events.append('B');return 'hashB'
                def digest_c(data):events.append('C');return 'hashC'
                class Message:
                    def __str__(self):events.append('argument');server.sha256_bytes=digest_c;return 'synthetic message'
                class Failure(dict):
                    def get(self,key,*args):
                        if key=='error_type':
                            events.append('before')
                            if events.count('before')==1:server.sha256_bytes=None if mode=='missing' else digest_b
                        return super().get(key,*args)
                record={'diagnostics':{'failure':Failure(message=Message(),error_type='synthetic')}}
                with patch.object(server,'sha256_bytes',digest_a),patch.object(server,'TEXT_INSPECTION_DIAGNOSTIC_LOGGER',logger):
                    for _ in range(1 if mode=='missing' else 2):
                        try:server._text_v2_write_server_diagnostic(record)
                        except TypeError:self.assertEqual(mode,'missing')
                        else:self.assertEqual(mode,'capture')
                self.assertEqual(events,['before','argument'] if mode=='missing' else ['before','argument','B','before','argument','C'])
                self.assertEqual(logger.info.call_count,0 if mode=='missing' else 2)
                self.assertTrue(all('synthetic message' not in str(call) for call in logger.info.call_args_list))


if __name__=='__main__':unittest.main(verbosity=2)
