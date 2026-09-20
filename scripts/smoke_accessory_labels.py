"""Offline original contracts for accessory display labels."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch,call
sys.path.insert(0,str(Path.cwd()))
class AccessoryLabelsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='accessory-labels-')))
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        for name in ('DATABASE_URL','VANTALINE_POSTGRES_DSN','PGDSN'):os.environ.pop(name,None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false',YOLO_AUTOINSTALL='false')
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            cls.lifetime.enter_context(patch(name,side_effect=AssertionError('External operation forbidden')))
        from types import SimpleNamespace
        cls.import_factory=Mock(side_effect=AssertionError('Eager model load forbidden'));cls.import_remove=Mock(side_effect=AssertionError('Eager inference forbidden'))
        cls.lifetime.enter_context(patch.dict(sys.modules,{'rembg':SimpleNamespace(new_session=cls.import_factory,remove=cls.import_remove)}))
        from local_inspection_service import server
        cls.import_factory.assert_not_called();cls.import_remove.assert_not_called()
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.lifetime.close()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
    def replace(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
    def image(self):
        import numpy as np
        return np.zeros((3, 5, 3), dtype=np.uint8)

    def asset_path(self, name='sample.PNG'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic')
        return path

    def decoder(self, **kwargs):
        import cv2
        return self.stack.enter_context(patch.object(cv2, 'imread', **kwargs))

    def test_compact_tokens_filter_case_and_word_cap(self):
        self.replace('GENERIC_ENGLISH_NAME_TOKENS',new={'the','and'})
        bounded=self.replace('bounded_text',side_effect=lambda value,limit:value)
        self.assertEqual(self.api.compact_english_accessory_name('the BLUE-green and USB2 foo bar baz qux seventh'),'Blue-green Usb2 Foo Bar Baz Qux')
        bounded.assert_called_once_with('the BLUE-green and USB2 foo bar baz qux seventh',120)
        self.assertEqual(self.api.compact_english_accessory_name('one two three',max_words=0),'One Two')
        self.assertEqual(self.api.compact_english_accessory_name('one two',max_words=-4),'One')
        self.assertEqual(self.api.compact_english_accessory_name('one two three four five six seven',max_words=100),'One Two Three Four Five Six')

    def test_compact_invalid_unknown_and_empty(self):
        for text in ('','???','Known unknown WORD','not-a-word?','中文'):
            self.assertEqual(self.api.compact_english_accessory_name(text),'')
        self.assertEqual(self.api.compact_english_accessory_name('accessory the target'),'')

    def test_compact_bound_length_before_regex(self):
        self.replace('GENERIC_ENGLISH_NAME_TOKENS',new=set())
        bounded=self.replace('bounded_text',return_value='foo')
        self.assertEqual(self.api.compact_english_accessory_name(object(),max_words=2),'Foo')
        self.assertEqual(bounded.call_args.args[1],120)

    def test_compact_invalid_cap_error_propagates(self):
        self.replace('GENERIC_ENGLISH_NAME_TOKENS',new=set())
        with self.assertRaises(ValueError):self.api.compact_english_accessory_name('word',max_words='invalid')

    def test_preferred_explicit_item_before_profile(self):
        self.replace('ACCESSORY_ENGLISH_NAME_FIELDS',new=('english_name','display_label'))
        compact=self.replace('compact_english_accessory_name',side_effect=lambda value,**kw: str(value or ''))
        item={'display_label':'item','ai_profile':{'english_name':'profile'}}
        self.assertEqual(self.api.preferred_english_accessory_name(item),'item')
        self.assertEqual(compact.call_args_list,[call(None,max_words=6),call('item',max_words=6)])

    def test_preferred_explicit_profile_before_native_name(self):
        self.replace('ACCESSORY_ENGLISH_NAME_FIELDS',new=('english_name',))
        compact=self.replace('compact_english_accessory_name',side_effect=lambda value,**kw:str(value or ''))
        self.assertEqual(self.api.preferred_english_accessory_name({'name':'native','ai_profile':{'english_name':'profile'}}),'profile')
        self.assertEqual(compact.call_args_list,[call(None,max_words=6),call('profile',max_words=6)])

    def test_preferred_name_then_label_item_before_profile(self):
        self.replace('ACCESSORY_ENGLISH_NAME_FIELDS',new=())
        compact=self.replace('compact_english_accessory_name',side_effect=lambda value,**kw:str(value or ''))
        self.assertEqual(self.api.preferred_english_accessory_name({'label':'item-label','ai_profile':{'name':'profile'}}),'item-label')
        self.assertEqual(compact.call_args_list,[call(None,max_words=2),call('item-label',max_words=2)])

    def test_preferred_native_fallback_insertion_order(self):
        self.replace('ACCESSORY_ENGLISH_NAME_FIELDS',new=())
        self.replace('compact_english_accessory_name',return_value='')
        self.replace('ACCESSORY_ENGLISH_NAME_FALLBACKS',new={'':'invalid','瓶':'Bottle','玻璃瓶':'Glass Bottle'})
        self.assertEqual(self.api.preferred_english_accessory_name({'name':' 玻璃瓶 '}),'Bottle')
        self.assertEqual(self.api.preferred_english_accessory_name({'label':'瓶'}),'Bottle')

    def test_preferred_phrase_order_over_text_order(self):
        self.replace('ACCESSORY_ENGLISH_NAME_FIELDS',new=());self.replace('ACCESSORY_ENGLISH_NAME_FALLBACKS',new={})
        self.replace('compact_english_accessory_name',return_value='')
        self.replace('ACCESSORY_ENGLISH_PHRASES',new=(('beta','Beta'),('alpha','Alpha')))
        self.assertEqual(self.api.preferred_english_accessory_name({'description':'ALPHA before BETA'}),'Beta')

    def test_preferred_search_fallback_and_list_limits(self):
        self.replace('ACCESSORY_ENGLISH_NAME_FIELDS',new=());self.replace('ACCESSORY_ENGLISH_NAME_FALLBACKS',new={});self.replace('ACCESSORY_ENGLISH_PHRASES',new=())
        compact=self.replace('compact_english_accessory_name',side_effect=lambda value,**kw:'Selected' if value=='target' else '')
        lists=self.replace('string_list',side_effect=lambda value,**kw:value or [])
        item={'description':'empty','tags':['target'],'ai_profile':{'distinguishing_text':['profile']}}
        self.assertEqual(self.api.preferred_english_accessory_name(item),'Selected')
        self.assertEqual(lists.call_args_list,[call(['target'],max_items=8),call(None,max_items=8),call(None,max_items=8),call(['profile'],max_items=8)])
        self.assertEqual(compact.call_args_list[-2:],[call('empty',max_words=2),call('target',max_words=2)])

    def test_preferred_empty_and_invalid_profile_fallback(self):
        self.assertEqual(self.api.preferred_english_accessory_name({}),'Accessory')
        self.assertEqual(self.api.preferred_english_accessory_name({'ai_profile':'invalid'}),'Accessory')

    def test_ensure_updates_item_and_existing_profile_only(self):
        preferred=self.replace('preferred_english_accessory_name',return_value='Fresh')
        profile={}; item={'english_name':'Old','ai_profile':profile}
        self.assertTrue(self.api.ensure_accessory_english_name(item))
        self.assertEqual(item['english_name'],'Fresh');self.assertIs(item['ai_profile'],profile);self.assertEqual(profile['english_name'],'Fresh')
        self.assertFalse(self.api.ensure_accessory_english_name(item));self.assertEqual(preferred.call_count,2)

    def test_ensure_profile_difference_and_invalid_profile(self):
        self.replace('preferred_english_accessory_name',return_value='Fresh')
        item={'english_name':'Fresh','ai_profile':{'english_name':'Old'}}
        self.assertTrue(self.api.ensure_accessory_english_name(item));self.assertEqual(item['ai_profile']['english_name'],'Fresh')
        item={'english_name':'Fresh','ai_profile':['invalid']}
        self.assertFalse(self.api.ensure_accessory_english_name(item));self.assertEqual(item['ai_profile'],['invalid'])
        item={};self.assertTrue(self.api.ensure_accessory_english_name(item));self.assertNotIn('ai_profile',item)

    def test_display_label_forwarding(self):
        item={}; preferred=self.replace('preferred_english_accessory_name',return_value='Shown')
        self.assertEqual(self.api.accessory_display_label(item),'Shown');preferred.assert_called_once_with(item)

    def test_profile_size_projection_defaults_and_kinds(self):
        self.assertEqual(self.api.profile_size_text(None),'size=unknown')
        self.assertEqual(self.api.profile_size_text([]),'size=unknown')
        self.assertEqual(self.api.profile_size_text({'kind':'other'}),'size=unknown')
        self.assertEqual(self.api.profile_size_text({'kind':'paper'}),'paper custom ?x?mm')
        self.assertEqual(self.api.profile_size_text({'kind':'paper','preset':'A4','width_mm':0,'height_mm':None}),'paper A4 0xNonemm')
        self.assertEqual(self.api.profile_size_text({'kind':'object','length_mm':12,'width_mm':3,'height_mm':4}),'object 12x3x4mm')

    def test_compact_token_policy_read_after_bounded_callback(self):
        api=self.api; self.replace('GENERIC_ENGLISH_NAME_TOKENS',new=set())
        def bounded(value,limit):
            api.GENERIC_ENGLISH_NAME_TOKENS={'skip'}
            return 'skip keep'
        self.replace('bounded_text',side_effect=bounded)
        self.assertEqual(self.api.compact_english_accessory_name('raw'),'Keep')

    def test_preferred_compact_selected_before_item_get(self):
        api=self.api;late=Mock(return_value='Late')
        class Item(dict):
            def get(self,key,default=None):
                if key=='english_name':api.compact_english_accessory_name=late
                return super().get(key,default)
        self.replace('ACCESSORY_ENGLISH_NAME_FIELDS',new=('english_name',))
        early=self.replace('compact_english_accessory_name',return_value='Early')
        self.assertEqual(self.api.preferred_english_accessory_name(Item(english_name='raw')),'Early')
        early.assert_called_once_with('raw',max_words=6);late.assert_not_called()

    def test_ensure_profile_read_after_preferred_callback(self):
        previous={'english_name':'Previous'};current={};item={'ai_profile':previous}
        def preferred(value):
            value['ai_profile']=current
            return 'Fresh'
        self.replace('preferred_english_accessory_name',side_effect=preferred)
        self.assertTrue(self.api.ensure_accessory_english_name(item))
        self.assertEqual(previous,{'english_name':'Previous'});self.assertEqual(current,{'english_name':'Fresh'})
        self.assertIs(item['ai_profile'],current)

    def test_ensure_retains_item_update_when_profile_read_raises(self):
        error=ValueError('profile read')
        class Profile(dict):
            def get(self,key,default=None):
                raise error
        profile=Profile(english_name='Old');item={'english_name':'Old','ai_profile':profile}
        self.replace('preferred_english_accessory_name',return_value='Fresh')
        with self.assertRaises(ValueError) as caught:self.api.ensure_accessory_english_name(item)
        self.assertIs(caught.exception,error);self.assertEqual(item['english_name'],'Fresh')
        self.assertIs(item['ai_profile'],profile);self.assertEqual(dict(profile),{'english_name':'Old'})

    def test_preferred_field_policy_refreshes_between_sources(self):
        api=self.api;self.replace('ACCESSORY_ENGLISH_NAME_FIELDS',new=('old',))
        def compact(value,**kwargs):
            if value=='refresh':
                api.ACCESSORY_ENGLISH_NAME_FIELDS=('fresh',)
                return ''
            return str(value or '')
        callback=self.replace('compact_english_accessory_name',side_effect=compact)
        item={'old':'refresh','ai_profile':{'old':'stale','fresh':'New profile'}}
        self.assertEqual(self.api.preferred_english_accessory_name(item),'New profile')
        self.assertEqual(callback.call_args_list,[call('refresh',max_words=6),call('New profile',max_words=6)])

    def test_two_label_services_keep_dependencies_separate(self):
        from local_inspection_service.accessories.display_labels import AccessoryLabels
        from local_inspection_service.accessories.display_label_ports import DisplayLabelPolicy,DisplayLabelText
        names=['GENERIC_ENGLISH_NAME_TOKENS','ACCESSORY_ENGLISH_NAME_FIELDS','ACCESSORY_ENGLISH_NAME_FALLBACKS','ACCESSORY_ENGLISH_PHRASES','bounded_text','string_list','compact_english_accessory_name','preferred_english_accessory_name']
        poisons={name:self.replace(name,new=Mock(side_effect=AssertionError('root '+name))) for name in names}
        def build(tag):
            ops={'bounded':Mock(return_value='skip '+tag),'strings':Mock(return_value=[]),'compact':Mock(side_effect=lambda value,**kw:tag+' compact' if value=='chosen' else ''),'preferred':Mock(return_value=tag+' preferred')}
            values={'generic_tokens':{'skip'},'fields':('english_name',),'fallbacks':{'native':tag+' native'},'phrases':(('beta',tag+' phrase'),),**ops}
            getters={name:Mock(return_value=value) for name,value in values.items()}
            service=AccessoryLabels(DisplayLabelPolicy(*(getters[n] for n in ['generic_tokens','fields','fallbacks','phrases'])),DisplayLabelText(*(getters[n] for n in ['bounded','strings','compact','preferred'])))
            for getter in getters.values():getter.assert_not_called()
            return service,ops,tag
        a=build('first');b=build('second')
        for service,ops,tag in (a,b,a):
            self.assertEqual(service.compact_english_accessory_name('raw'),tag.title())
            self.assertEqual(service.preferred_english_accessory_name({'english_name':'chosen'}),tag+' compact')
            self.assertEqual(service.preferred_english_accessory_name({'description':'beta'}),tag+' phrase')
            item={'ai_profile':{}}
            self.assertTrue(service.ensure_accessory_english_name(item))
            self.assertEqual(item,{'english_name':tag+' preferred','ai_profile':{'english_name':tag+' preferred'}})
            self.assertEqual(service.accessory_display_label({}),tag+' preferred')
        self.assertEqual([a[1]['bounded'].call_count,b[1]['bounded'].call_count],[2,1])
        self.assertEqual([a[1]['strings'].call_count,b[1]['strings'].call_count],[8,4])
        self.assertEqual([a[1]['compact'].call_count,b[1]['compact'].call_count],[14,7])
        self.assertEqual([a[1]['preferred'].call_count,b[1]['preferred'].call_count],[4,2])
        for poison in poisons.values():poison.assert_not_called()

if __name__=='__main__':unittest.main()
