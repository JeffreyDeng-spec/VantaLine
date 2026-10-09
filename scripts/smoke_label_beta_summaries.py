"""Real PostgreSQL Beta SQL summaries versus the frozen original list endpoint."""
import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch
from psycopg.pq import TransactionStatus
from smoke_label_history_statistics import StatisticsFixture
from local_inspection_service.label_inspection.api import PREFIX
from local_inspection_service.storage.label_inspection import LabelRepository


def beta(identity, **fields):
    value=dict(id=identity,owner_user_id='alice',created_at=7,updated_at=0,status='succeeded',
        report_version='label-batch-v3',inputs={'standard_name':'Beta '+identity,'references':{'one':{'text':'reference'}}},
        labels={'one':{'text':'synthetic'*1024}},summary={'decision':'MATCH'})
    value.update(fields)
    return value


def replace_rows(f, values):
    table=f.writer._qualified_table('codex_comparison_tasks')
    f.writer.connection.execute(f'TRUNCATE {table}');f.writer.connection.commit()
    f.repo._legacy_cache.clear()
    for i,value in enumerate(values):
        identity='stored-'+str(i)
        f.insert('codex_comparison_tasks',[beta(identity)])
        f.writer.connection.execute(f'UPDATE {table} SET raw_json=%s::jsonb WHERE id=%s',
            (json.dumps(value,ensure_ascii=False),identity))
    f.writer.connection.commit()


def outcome(f, baseline):
    try:return ('ok',f.traverse(baseline))
    except BaseException as error:
        return (type(error).__name__,str(error),getattr(error,'status_code',None),
                getattr(error,'detail',None),type(error.__cause__).__name__ if error.__cause__ else None)


def main():
    with StatisticsFixture() as f:
        ordinary=[beta('one'),beta('two',updated_at=0,created_at=15,status=None,summary={'decision':None}),
            beta('three',inputs={'standard_name':'中😀','references':[]},labels=[]),
            beta('four',inputs={'references':{}},labels={},unused={'proof':'x'*8192}),
            beta('five',report_version='old',inputs={'standard_name':''},labels=None),
            beta('small',labels={},inputs={}),beta('negative',updated_at=-5,created_at=-10),
            beta('null-update',updated_at=None),beta('same'),beta('same',summary={'decision':'DIFFERENCES'})]
        for field in ('inputs','summary','status','updated_at','created_at','report_version'):
            value=beta('missing-'+field);value.pop(field);ordinary.append(value)
        replace_rows(f,ordinary)
        assert f.traverse()==f.traverse(True)
        tagged=[x.payload for x in f.repo.list_beta_history('alice')]
        assert sum(x.get('labels')=={'one':{}} for x in tagged)>=10
        assert any(x['id']=='small' and x['labels']=={} for x in tagged)
        assert f.repo.legacy('alice','beta')==ordinary  # detail reads preserve all evidence/order
        assert f.reader.connection.info.transaction_status==TransactionStatus.IDLE
        from psycopg.rows import dict_row
        prior_factory=f.reader.connection.row_factory
        try:
            f.reader.connection.row_factory=dict_row
            assert [x.payload for x in f.repo.list_beta_history('alice')]==tagged
        finally:f.reader.connection.row_factory=prior_factory
        for filters in ({'q':'中'},{'source':'beta'},{'source':'word'},{'result':'MATCH'},{'result':'REVIEW_REQUIRED'}):
            assert f.traverse(**filters)==f.traverse(True,**filters)
        # Cursor produced by the parent remains fixed after rename and an additional Beta record.
        original=f.traverse(True);page=f.page(True,limit=2);items=page['items'][:]
        f.insert('codex_comparison_tasks',[beta('new',updated_at=99)])
        table=f.writer._qualified_table('codex_comparison_tasks')
        f.writer.connection.execute(f"UPDATE {table} SET raw_json=jsonb_set(raw_json,'{{inputs,standard_name}}','\"renamed\"') WHERE id='stored-0'")
        f.writer.connection.commit()
        while page['next_cursor']:
            page=f.page(cursor=page['next_cursor'],limit=2);items+=page['items']
        assert items==original
        # Account predicates bind typed owner columns, including raw-owner disagreement.
        foreign=beta('foreign',owner_user_id='bob');f.insert('codex_comparison_tasks',[foreign])
        f.writer.connection.execute(f"UPDATE {table} SET raw_json=jsonb_set(raw_json,'{{owner_user_id}}','\"alice\"') WHERE id='foreign'");f.writer.connection.commit()
        assert all(not x['id'].endswith('foreign') for x in [r.payload for r in f.repo.list_beta_history('alice')])
        f.owner='bob';assert f.traverse()==f.traverse(True) and len(f.traverse())==1;f.owner='alice'
        # New SQL projection is read-only and does not wait on the label write fence.
        f.writer.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('label-inspection-v1',0))")
        try:assert f.repo.list_beta_history('alice')
        finally:f.writer.connection.rollback()
        assert f.reader.connection.info.transaction_status==TransactionStatus.IDLE
        print('PASS Beta summaries, small fallback, typed owner, full detail, filters and parent snapshot',flush=True)

        shapes=[]
        for value in (None,False,0,'',[],{},True,1,'wrong',[1]):
            for field in ('inputs','summary','status','created_at','updated_at','labels'):
                shapes.append(beta('shape',**{field:value}))
            shapes.append(beta('shape',inputs={'references':value}))
            shapes.append(beta('shape',inputs={'standard_name':value}))
            shapes.append(beta('shape',summary={'decision':value}))
        for row in shapes:
            replace_rows(f,[row])
            assert outcome(f,False)==outcome(f,True),row
            # Filtering must not hide an error in a source that would not match.
            before=f.parent_client.get(PREFIX+'/tasks?source=word')
            after=f.client.get(PREFIX+'/tasks?source=word')
            assert before.status_code==after.status_code
            if before.status_code!=200:assert before.content==after.content
        print('PASS 90 missing/falsey/wrong-shape and pre-filter failure cases',flush=True)

        # Compact only independently safe entry objects, preserving all other JSON.
        mixed={'text':{'text':'证据😀'*4096,'flag':False,'nothing':None},'empty':{},
               'numeric':{'number':1},'nested':{'value':{'text':'keep'}},'array':{'value':['keep']},
               'scalar':False,'null':None,'list':[]}
        rows=[beta('mixed',labels=mixed,unknown={'nested':{'keep':True}}),
              beta('many',labels={str(i):{'text':'keep length'} for i in range(2000)})]
        replace_rows(f,rows);assert outcome(f,False)==outcome(f,True)
        compacted=[x.payload for x in f.repo.list_beta_history('alice')]
        expected=copy.deepcopy(rows);expected[0]['labels']['text']={}
        expected[1]['labels']={str(i):{} for i in range(2000)}
        assert compacted==expected;assert f.repo.legacy('alice','beta')==rows
        print('PASS mixed safe/unsafe label entries, unchanged unknown fields and 2000 label keys',flush=True)

        # Nullable SQL counts must preserve zero and never hide original JSON errors.
        from local_inspection_service.label_inspection.history_summary import count_or_length
        class MustNotCount:
            def __len__(self):raise AssertionError('SQL zero incorrectly fell back to Python len')
        assert count_or_length(MustNotCount(),0)==0
        for refs in ({},[],{'a':1,'b':2},[1,2],None,'abc',False,3):
            for labels in ({},[],{'a':{}},[1],None,'abc',False,3):
                row=beta('counts',inputs={'references':refs},labels=labels)
                replace_rows(f,[row]);read=f.repo.list_beta_history('alice')[0]
                assert read.reference_count==(len(refs) if isinstance(refs,(dict,list)) else None)
                assert read.label_count==(len(labels) if isinstance(labels,(dict,list)) else None)
                assert outcome(f,False)==outcome(f,True)
                row['report_version']='legacy';replace_rows(f,[row])
                assert outcome(f,False)==outcome(f,True)  # nonbatch must not call len on null/scalars
        for field in ('inputs','labels'):
            row=beta('explicit-null',**({field:{'references':None}} if field=='inputs' else {field:None}))
            replace_rows(f,[row]);before=outcome(f,True);after=outcome(f,False)
            assert before==after and before[0]=='TypeError' and "NoneType" in before[1], (field,before,after)
        encoded=beta('encoded-counts',inputs={'references':[]},labels=[])
        replace_rows(f,[json.dumps(encoded)])
        read=f.repo.list_beta_history('alice')[0]
        assert read.payload==encoded and read.reference_count is None and read.label_count is None
        assert outcome(f,False)==outcome(f,True)
        print('PASS nullable SQL counts, explicit zero, scalar/null errors, nonbatch and encoded fallback',flush=True)

        # Preserve errors from unused evidence, string-encoded raw objects and deep JSON.
        nested='x'
        for _ in range(40):nested={'nested':nested}
        for row in (beta('deep',unused=nested),json.dumps(beta('encoded')),['array'],None):
            replace_rows(f,[row]);assert outcome(f,False)==outcome(f,True)
            projected=[x.payload for x in f.repo.list_beta_history('alice')]
            if isinstance(row,dict):assert projected[0]['unused']==row['unused']
        previous=sys.get_int_max_str_digits();sys.set_int_max_str_digits(640)
        try:
            for field in ('unused','labels','inputs'):
                # Encode before lowering the integer limit through an explicitly supplied JSON number.
                raw=json.dumps(beta('large'))[:-1]+',"'+field+'":'+('1'+'0'*700)+'}'
                replace_rows(f,[beta('large')]);f.writer.connection.execute(f'UPDATE {table} SET raw_json=%s::jsonb',(raw,));f.writer.connection.commit()
                before=outcome(f,True);after=outcome(f,False)
                assert before==after and before[0]=='HTTPException' and before[2]==422,(before,after)
                assert f.reader.connection.info.transaction_status==TransactionStatus.IDLE
        finally:sys.set_int_max_str_digits(previous)
        print('PASS full fallback decode errors, unused 700-digit integer and transaction cleanup',flush=True)


if __name__=='__main__':main()
