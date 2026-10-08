"""Compare retained HTTP behavior and compiled prefixes to frozen pre-cleanup bodies."""
import ast
import __future__
import copy
import dis
import hashlib
import inspect
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient


def main():
    frozen = (ROOT/'tests/backend_contract/retired_entry_baseline.py').read_bytes().replace(b'\r\n', b'\n')
    assert hashlib.sha256(frozen).hexdigest() == '8060e25e115ec936e9894af8c1e2d48a3694d3dc57704798212e92dd36af7eff'
    old_nodes = {n.name:n for n in ast.parse(frozen).body if isinstance(n,ast.FunctionDef)}
    source = ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'))
    new_nodes = {n.name:n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in old_nodes}
    assert len(old_nodes) == len(new_nodes) == 7
    def compile_nodes(nodes, namespace):
        nodes = copy.deepcopy(list(nodes.values()))
        for node in nodes:
            node.decorator_list = []
        body = 'from __future__ import annotations\n'+'\n'.join(ast.unparse(n) for n in nodes)
        exec(compile(body,'<retired-contract>','exec'), namespace)
        return {node.name:namespace[node.name] for node in nodes}
    with tempfile.TemporaryDirectory(prefix='retired-entry-') as temporary:
        root=Path(temporary); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          VANTALINE_LABEL_INSPECTION_ENABLED='false', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',
                          INSPECTION_ENABLE_LAN_CORS='0', INSPECTION_CORS_ORIGINS='')
        os.environ.pop('INSPECTION_CORS_ORIGIN_REGEX',None)
        from local_inspection_service import server
        previous = compile_nodes(old_nodes, dict(vars(server)))
        candidate = compile_nodes(new_nodes, dict(vars(server)))
        dead_calls=set()
        expected_cells = {'update_plc_config': ('full_replacement','request_payload'),
                          'update_ai_config': ('active_key_id','image_provider','item_id','key_provider','local'),
                          'delete_ai_config_key': ('active_key_id',),
                          'stream_plc_capture_events': ('clean_session_id','user_id')}
        if sys.version_info < (3, 11):
            expected_cells['delete_ai_config_key'] = ('active_key_id', 'provider')
        for name, original in old_nodes.items():
            stop=next(i for i,n in enumerate(original.body) if isinstance(n,(ast.Return,ast.Raise)))
            prefix=copy.deepcopy(original); prefix.body=prefix.body[:stop+1]; prefix.decorator_list=[]
            actual=copy.deepcopy(new_nodes[name]); actual.decorator_list=[]
            assert ast.dump(prefix)==ast.dump(actual), name
            for statement in original.body[stop+1:]:
                dead_calls.update(n.func.id for n in ast.walk(statement) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name))
            left,right=previous[name].__code__,candidate[name].__code__
            assert left.co_freevars == right.co_freevars == ()
            if sys.version_info < (3, 11):
                assert bool(left.co_flags & inspect.CO_NOFREE) == (not left.co_cellvars)
                assert right.co_flags & inspect.CO_NOFREE
                assert left.co_flags & ~inspect.CO_NOFREE == right.co_flags & ~inspect.CO_NOFREE
            else:
                assert left.co_flags == right.co_flags
            assert left.co_cellvars == expected_cells.get(name, ()) and right.co_cellvars == ()
            # Python 3.10 creates closure cells in the frame; 3.11+ emits MAKE_CELL
            # and exposes exception tables. Compare every executable instruction
            # on both versions, allowing only these known unused allocations.
            if sys.version_info >= (3, 11):
                assert left.co_exceptiontable == right.co_exceptiontable == b''
            else:
                assert not hasattr(left, 'co_exceptiontable') and not hasattr(right, 'co_exceptiontable')
            expected_allocations = list(expected_cells.get(name, ())) if sys.version_info >= (3, 11) else []
            assert [i.argval for i in dis.get_instructions(left) if i.opname=='MAKE_CELL'] == expected_allocations
            def instructions(code):
                return [(i.opname,i.argval) for i in dis.get_instructions(code) if i.opname!='MAKE_CELL']
            assert instructions(left)==instructions(right), name
            # The only compiler difference is allocating never-read closure cells.
            for code in (left,right):
                assert not any('DEREF' in i.opname or i.opname in {'LOAD_CLOSURE','MAKE_FUNCTION'} or (i.opname=='LOAD_GLOBAL' and i.argval in {'locals','globals','vars'}) for i in dis.get_instructions(code))
        assert server.stream_plc_capture_events.__code__.co_flags == (candidate['stream_plc_capture_events'].__code__.co_flags & ~__future__.annotations.compiler_flag)
        clients=[TestClient(server.app,base_url='https://testserver') for _ in range(3)]
        anonymous,admin,member=clients
        try:
            password='contract-password-only'
            assert admin.post('/api/auth/bootstrap',json={'username':'fixture-admin','password':password}).status_code==200
            assert admin.post('/api/auth/users',json={'username':'fixture-member','password':password,'role':'user','permissions':[]}).status_code==200
            assert member.post('/api/auth/login',json={'username':'fixture-member','password':password}).status_code==200
            routes=[r for r in server.app.routes if getattr(getattr(r,'endpoint',None),'__name__',None) in old_nodes]
            assert len(routes)==7
            events=[]
            def poison(*args,**kwargs):
                raise AssertionError('unreachable helper was invoked')
            # Retired helper functions are poisoned only in frozen endpoint globals;
            # real authentication middleware and current services keep their dependencies.
            for function in previous.values():
                for name in dead_calls:
                    if name not in {'HTTPException','require_admin_role','dict','str','bool','list','set','any','next','isinstance','getattr','len','float','int'}:
                        function.__globals__[name]=poison
            service=SimpleNamespace(update=lambda request: events.append(request.model_dump()) or {'forwarded':True})
            for functions in (previous,candidate):
                functions['update_plc_config'].__globals__['_plc_config_diagnostics']=service
            def responses(functions):
                captured={};saved=[]
                try:
                    for route in routes:
                        saved.append((route,route.dependant.call))
                        route.dependant.call=functions[route.endpoint.__name__]
                    for index,client in enumerate(clients):
                        for route in routes:
                            path=route.path.replace('{session_id}','missing')
                            method=sorted(route.methods)[0]
                            for body in ({}, {'session_id':'missing','camera_ready':True}, {'camera_ready':[]}, None):
                                options={'json':body} if method=='POST' else {}
                                response=client.request(method,path,params={'session_id':'missing'},**options)
                                captured[(index,route.path,repr(body))]=(response.status_code,response.json())
                    return captured
                finally:
                    for route,call in saved: route.dependant.call=call
            with patch.object(server,'_plc_config_diagnostics',service):
                before=responses(previous);old_events=list(events);events.clear()
                after=responses(candidate)
            assert before==after and old_events==events
            statuses={value[0] for value in after.values()}
            assert {401,403,409,410,422}.issubset(statuses), statuses
            print('PASS seven retained endpoints: anonymous/member/admin, validation/error order, poison helpers and compiler prefixes; only unused closure-cell allocations removed')
        finally:
            for client in clients: client.close()


if __name__=='__main__': main()
