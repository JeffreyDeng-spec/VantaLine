"""Synthetic PostgreSQL decoder contracts for the unused versioned helper."""
import ast
import json
import os
from pathlib import Path
import random
import sys
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.storage.runtime_selector import default_postgres_connector

MIGRATION = ROOT / 'local_inspection_service/storage/migrations/2026_10_08_legacy_json_projection_v1.sql'


def outcome(raw):
    # Execute the actual original reader's extra decoding, including its errors.
    namespace = {'json': json}
    source = ast.parse((ROOT / 'local_inspection_service/storage/label_inspection.py').read_text())
    owner = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'LabelRepository')
    method = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == 'rows')
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<actual LabelRepository.rows>', 'exec'), namespace)
    reader = types.SimpleNamespace(repository=types.SimpleNamespace(_row_to_dict=lambda c, row: row))
    cursor = types.SimpleNamespace(fetchall=lambda: [{'raw_json': raw}])
    try:
        value = namespace['rows'](reader, cursor)[0]
        if isinstance(value, dict):
            value = {k: value[k] for k in ('id', 'value') if k in value}
        return ('value', json.dumps(value, sort_keys=True, ensure_ascii=True))
    except Exception as error:
        return ('error', type(error).__name__, str(error))


def main():
    import psycopg
    schema = 'legacy_projection_' + uuid.uuid4().hex[:12]
    connection = default_postgres_connector(os.environ['VANTALINE_POSTGRES_DSN'])
    source = MIGRATION.read_text()
    assert 'CREATE OR REPLACE' not in source and 'SECURITY DEFINER' not in source
    sql = source.replace('vantaline.', f'"{schema}".')
    count = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA "{schema}"')
            cursor.execute(f'CREATE TABLE "{schema}".feature_migrations(version text PRIMARY KEY, applied_at bigint, metadata_json jsonb)')
            connection.commit()
            cursor.execute(sql)
            # The installer records/checks the migration once; the function is not replaced.
            cursor.execute(f'SELECT count(*) FROM "{schema}".feature_migrations WHERE version=%s', ('2026_10_08_legacy_json_projection_v1',))
            assert cursor.fetchone() == (1,)
            cursor.execute('SELECT provolatile, proisstrict, prosecdef, proconfig FROM pg_proc WHERE oid=%s::regprocedure', (f'{schema}.legacy_json_projection_v1(jsonb,text[])',))
            assert cursor.fetchone() == ('i', True, False, ['search_path=pg_catalog'])
            cursor.execute('SELECT prosrc FROM pg_proc WHERE oid=%s::regprocedure', (f'{schema}.legacy_json_projection_v1(jsonb,text[])',))
            assert cursor.fetchone()[0] == source.split('$legacy_json_projection$')[1]
            # Existing installer skips an already recorded version; direct replay must fail closed.
            connection.commit()
            try:
                cursor.execute(sql)
            except psycopg.errors.DuplicateFunction:
                connection.rollback()
            else:
                raise AssertionError('versioned function was silently replaced')
            # Caller collation cannot alter token checks or exact Python key selection.
            cursor.execute(f'CREATE COLLATION "{schema}".synthetic_ci (provider=icu, locale=\'und-u-ks-level1\', deterministic=false)')
            for fields, expected in ((['id'], {'id': 'lower'}), (['e'], {'e': 1})):
                encoded = json.dumps(json.dumps({'ID': 'upper', 'id': 'lower', 'é': 2, 'e': 1, 'unused': 'synthetic'}))
                cursor.execute(f'SELECT "{schema}".legacy_json_projection_v1(%s::jsonb,%s::text[] COLLATE "{schema}".synthetic_ci)', (encoded, fields))
                assert json.loads(cursor.fetchone()[0]) == expected
                count += 1
            cases = [
                '{bad', 'null', '[1,2]', json.dumps(json.dumps({'id': 'layered'})),
                '{"id":"a","value":NaN}', '{"id":"a","value":Infinity}',
                '{"id":"a","value":"\\u0000"}', '{"id":"a","value":"\\ud800"}',
                '{"id":"a","value":"\\udc00"}', '{"id":"a","value":"\\ud83d\\ude00"}',
                '{"id":"first","\\u0069d":"last","value":1,"value":2}',
                '{"id":"a","value":1,"unknown":' + '9'*5000 + '}',
                '{"id":"a","value":1,"unknown":' + '['*1200 + '0' + ']'*1200 + '}',
                '{"id":"a","unknown":' + '['*1200 + '0' + ']'*1200 + ',"unknown":0,"value":1}',
            ]
            for number in ('1', '1.0', '-0', '-0.0', '1e2', '1e-400', '1e300', '1e400', '-1e400', '9'*1000):
                cases.append('{"id":"number","value":' + number + ',"unused":"synthetic"}')
            rng = random.Random(20261008)
            for _ in range(200):
                value = rng.choice([None, True, False, rng.randrange(-100000, 100000), rng.uniform(-1e30, 1e30), '括号[{]🙂', ['a', {'k': 1.0}]])
                cases.append(json.dumps({'id': 'synthetic', 'value': value, 'unused': {'deep': [1, 2, 3]}}, ensure_ascii=True))
            # Preserve the original-token boundary, including brackets inside strings.
            boundaries = [
                ('{"id":"a","value":1,"unknown":' + '['*15 + '0' + ']'*15 + '}', False),
                ('{"id":"a","value":1,"unknown":' + '['*16 + '0' + ']'*16 + '}', True),
                ('{"id":"a","value":1,"unknown":' + '9'*512 + '}', False),
                ('{"id":"a","value":1,"unknown":' + '9'*513 + '}', True),
                (json.dumps({'id': 'a', 'value': 1, 'unknown': '['*17}), True),
                ('{"id":"a","value":1,"unknown":"\\u005b\\u007b"}', False),
            ]
            for text, unchanged in boundaries:
                cursor.execute(f'SELECT %s::jsonb, "{schema}".legacy_json_projection_v1(%s::jsonb,%s)', (json.dumps(text), json.dumps(text), ['id', 'value']))
                raw, compact = cursor.fetchone()
                assert (raw == compact) is unchanged
                assert outcome(raw) == outcome(compact)
                count += 1
            for text in cases:
                cursor.execute(f'SELECT %s::jsonb, "{schema}".legacy_json_projection_v1(%s::jsonb,%s)', (json.dumps(text), json.dumps(text), ['id', 'value']))
                raw, compact = cursor.fetchone()
                assert type(raw) is type(compact), ('outer type', text[:80])
                assert outcome(raw) == outcome(compact), (text[:80], outcome(raw), outcome(compact))
                count += 1
            for value in ({'id': 'object', 'value': 1.0, 'unused': 'synthetic'}, {'id': 'object', 'value': -0.0}, {'id': 'object', 'value': True}, {'id': 'object', 'unused': {'deep': [1]}}):
                cursor.execute(f'SELECT %s::jsonb, "{schema}".legacy_json_projection_v1(%s::jsonb,%s)', (json.dumps(value), json.dumps(value), ['id', 'value']))
                raw, compact = cursor.fetchone()
                assert type(raw) is type(compact) and outcome(raw) == outcome(compact)
                count += 1
            cursor.execute(f'SELECT "{schema}".legacy_json_projection_v1(NULL,%s), "{schema}".legacy_json_projection_v1(%s::jsonb,NULL)', (['id'], '{}'))
            assert cursor.fetchone() == (None, None)
            cursor.execute(f'SELECT "{schema}".legacy_json_projection_v1(%s::jsonb,%s)', (json.dumps('{"id":"a","value":1}'), []))
            assert json.loads(cursor.fetchone()[0]) == {}
            for fields in ([None], ['id', None, 'id'], [['id'], ['value']]):
                cursor.execute(f'SELECT \"{schema}\".legacy_json_projection_v1(%s::jsonb,%s::text[])', (json.dumps('{\"id\":\"a\",\"value\":1}'), fields))
                selected = json.loads(cursor.fetchone()[0])
                assert selected == ({} if fields == [None] else {'id': 'a'} if fields == ['id', None, 'id'] else {'id': 'a', 'value': 1})
            # A query failure is not converted into a successful old-path result.
            connection.commit()
            try:
                cursor.execute(f'SELECT "{schema}".legacy_json_projection_v1(%s::jsonb,%s::text[])', ('{}', '{invalid'))
            except psycopg.errors.InvalidTextRepresentation:
                connection.rollback()
            else:
                raise AssertionError('invalid query argument was hidden')
        # DDL and its feature marker share one transaction, including installer failures.
        for suffix, conflict in (('_rollback', False), ('_conflict', True)):
            target = schema + suffix
            with connection.cursor() as cursor:
                cursor.execute(f'CREATE SCHEMA "{target}"')
                cursor.execute(f'CREATE TABLE "{target}".feature_migrations(version text PRIMARY KEY, applied_at bigint, metadata_json jsonb)')
                if conflict:
                    cursor.execute(f'CREATE FUNCTION "{target}".legacy_json_projection_v1(raw_json jsonb, fields text[]) RETURNS jsonb LANGUAGE sql AS \'SELECT raw_json\'')
                connection.commit()
                candidate = source.replace('vantaline.', f'"{target}".')
                if not conflict:
                    candidate = candidate.replace('version, applied_at, metadata_json', 'version, applied_at, missing_column')
                try:
                    cursor.execute(candidate)
                except (psycopg.errors.DuplicateFunction, psycopg.errors.UndefinedColumn) as error:
                    assert isinstance(error, psycopg.errors.DuplicateFunction if conflict else psycopg.errors.UndefinedColumn)
                    connection.rollback()
                else:
                    raise AssertionError('conflicting/failed migration succeeded')
                cursor.execute(f'SELECT count(*) FROM "{target}".feature_migrations')
                assert cursor.fetchone() == (0,)
                cursor.execute('SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname=%s', (target, 'legacy_json_projection_v1'))
                assert cursor.fetchall() == ([('SELECT raw_json',)] if conflict else [])
                connection.commit()
        print(json.dumps({'suites': [{'name': 'legacy-json-projection-preparation', 'tests': count + 11, 'passed': count + 11, 'skipped': 0}], 'python': sys.version, 'consumer_enabled': False}))
    finally:
        connection.rollback()
        with connection.cursor() as cursor:
            for target in (schema, schema + '_rollback', schema + '_conflict'):
                cursor.execute(f'DROP SCHEMA IF EXISTS "{target}" CASCADE')
        connection.commit()
        connection.close()
        print('PASS synthetic helper schema removed and connection closed')


if __name__ == '__main__':
    main()
