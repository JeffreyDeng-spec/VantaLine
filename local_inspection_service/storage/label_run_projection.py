"""Optional derived-state publication after the business transaction commits.

Owns one short row-lock transaction, never the label global advisory lock. No
business mutation, history rewrite, read-time backfill or retry is performed.
"""
from ..label_inspection.run_summary import DISCARDED, MAX_BYTES, VERSION, project
from ..codex_compare.contracts import encode


class LabelRunProjection:
    def __init__(self, repository):
        self.repository = repository
        self.source = repository._qualified_table("label_inspection_objects")
        self.target = repository._qualified_table("label_run_projection")

    def publish(self, owner, identity):
        connection = self.repository.connection
        # Refuse to commit another operation's work or publish after an
        # autocommit SELECT released its source lock. Only psycopg IDLE is 0.
        if connection.autocommit or connection.info.transaction_status != 0:
            raise RuntimeError("Summary publication requires an idle transaction owner")
        cursor = self.repository._cursor()
        try:
            cursor.execute("SET LOCAL lock_timeout='100ms'")
            cursor.execute("SET LOCAL statement_timeout='500ms'")
            cursor.execute(
                "WITH locked AS MATERIALIZED ("
                "SELECT id,owner_user_id,task_id,CASE WHEN jsonb_typeof(raw_json)='object' "
                "AND raw_json->>'kind'='run' THEN (raw_json - %s::text[])::text ELSE NULL END AS payload "
                f"FROM {self.source} WHERE id=%s AND owner_user_id=%s AND kind='run' "
                "AND status IN ('completed','failed','interrupted') FOR UPDATE SKIP LOCKED) "
                "SELECT id,owner_user_id,task_id,CASE WHEN octet_length(payload)<=%s THEN payload ELSE NULL END "
                "FROM locked", (list(DISCARDED), identity, owner, MAX_BYTES))
            row = cursor.fetchone()
            summary = project(row[3], row[0], row[1], row[2]) if row else None
            if summary is not None:
                cursor.execute(
                    f"INSERT INTO {self.target} (id,projection_version,raw_json) VALUES (%s,%s,%s::jsonb) "
                    "ON CONFLICT(id) DO UPDATE SET projection_version=EXCLUDED.projection_version,raw_json=EXCLUDED.raw_json",
                    (row[0], VERSION, encode(summary)))
            connection.commit()
            return summary is not None
        except BaseException:
            connection.rollback()
            raise
        finally:
            cursor.close()
