"""Real PostgreSQL review transitions in a disposable schema, never business rows."""
import os
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import psycopg
from psycopg import sql
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository, PostgresRuntimeRepositoryError


def main():
    dsn = os.environ['VANTALINE_POSTGRES_DSN']
    schema = 'doc_review_test_' + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as control:
        control.execute(postgres_ddl(schema))
        try:
            with psycopg.connect(dsn) as conn:
                repo = PostgresRuntimeRepository(conn, 'test', schema)
                standard = dict(id='std', owner_user_id='owner', status='draft', revision_number=0)
                asset = dict(id='asset', standard_id='std', owner_user_id='owner', ordinal=1,
                             status='needs_confirmation', classification_source='unclassified', sha256='a'*64)
                repo.upsert_row('text_inspection_standards', dict(id='std', owner_user_id='owner', name='test',
                    material_code='test', version_label='1', standard_type='label', status='draft',
                    source_sha256='b'*64, created_at=1, updated_at=1, raw_json=standard))
                repo.upsert_row('text_inspection_assets', dict(id='asset', standard_id='std', owner_user_id='owner',
                    asset_kind='label_candidate', ordinal=1, status='needs_confirmation', sha256='a'*64,
                    created_at=1, updated_at=1, raw_json=asset))
                for owner in ['owner', 'other']:
                    try:
                        repo.confirm_text_inspection_standard('std', owner, 2, revision_id='blocked')
                        raise AssertionError('pending or cross-owner confirmation accepted')
                    except PostgresRuntimeRepositoryError:
                        pass
                repo.patch_text_inspection_asset('std', 'asset', 'owner', 'confirm', 3, revision_id='draft')
                result = repo.confirm_text_inspection_standard('std', 'owner', 4, revision_id='rev1')
                assert result['confirmed_asset_ids'] == ['asset']
                for index, action in enumerate(['review', 'remove', 'confirm'], 2):
                    edited, result = repo.patch_text_inspection_asset('std', 'asset', 'owner', action, 4+index,
                        revision_id=f'rev{index}', expected_revision=index-1)
                    assert result['revision_number'] == index
                    assert edited['original_classification']['status'] == 'needs_confirmation'
                    assert result['confirmed_asset_ids'] == (['asset'] if action == 'confirm' else [])
                old = repo.fetch_by_primary_key('text_inspection_standard_revisions', {'id': 'rev1'})
                assert old['raw_json']['confirmed_asset_ids'] == ['asset']
        finally:
            control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    print('document review real PostgreSQL: PASS')


if __name__ == '__main__':
    main()
