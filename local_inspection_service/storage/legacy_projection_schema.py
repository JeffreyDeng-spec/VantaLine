"""Canonical optional derived manual-list schema, compatible with old writers."""
import re

TABLES = {
    "standards": "text_inspection_standards",
    "sessions": "text_inspection_manual_sessions",
    "pages": "text_inspection_manual_pages",
    "records": "text_inspection_records",
    "assets": "text_inspection_assets",
}
VERSION = "2026_10_08_legacy_list_projection"


def derived_ddl(schema_name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema_name):
        raise ValueError("Unsafe manual projection schema")
    schema = '"' + schema_name + '"'
    tables = ",".join("'" + name + "'" for name in TABLES.values())
    sql = f'''
CREATE TABLE IF NOT EXISTS {schema}.legacy_projection_epoch (
 owner_user_id TEXT PRIMARY KEY, sequence BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS {schema}.legacy_projection_ready (
 owner_user_id TEXT PRIMARY KEY, sequence BIGINT NOT NULL, projection_version BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS {schema}.legacy_projection_rows (
 owner_user_id TEXT NOT NULL, group_id TEXT NOT NULL, kind TEXT NOT NULL,
 ordinal BIGINT NOT NULL, raw_json JSONB NOT NULL,
 PRIMARY KEY(owner_user_id,group_id,kind,ordinal)
);
CREATE OR REPLACE FUNCTION {schema}.invalidate_legacy_projection_v1()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $legacy_projection$
DECLARE identity TEXT;
BEGIN
 IF TG_TABLE_SCHEMA <> '{schema_name}' OR TG_TABLE_NAME NOT IN ({tables}) OR TG_WHEN <> 'AFTER' THEN
  RAISE EXCEPTION 'Invalid manual projection trigger source';
 END IF;
 IF TG_OP='TRUNCATE' AND TG_LEVEL='STATEMENT' THEN
  UPDATE {schema}.legacy_projection_epoch SET sequence=sequence+1;
  DELETE FROM {schema}.legacy_projection_ready;
  RETURN NULL;
 END IF;
 IF TG_LEVEL <> 'ROW' OR TG_OP NOT IN ('INSERT','UPDATE','DELETE') THEN
  RAISE EXCEPTION 'Invalid manual projection trigger operation';
 END IF;
 FOR identity IN SELECT DISTINCT value COLLATE "C" AS value FROM unnest(ARRAY[
  CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN OLD.owner_user_id END,
  CASE WHEN TG_OP IN ('UPDATE','INSERT') THEN NEW.owner_user_id END
 ]) value WHERE value IS NOT NULL ORDER BY value COLLATE "C" LOOP
  INSERT INTO {schema}.legacy_projection_epoch(owner_user_id,sequence) VALUES(identity,1)
  ON CONFLICT(owner_user_id) DO UPDATE SET sequence={schema}.legacy_projection_epoch.sequence+1;
  DELETE FROM {schema}.legacy_projection_ready WHERE owner_user_id=identity;
 END LOOP;
 RETURN NULL;
END;
$legacy_projection$;
'''
    for table in TABLES.values():
        sql += f'''CREATE OR REPLACE TRIGGER invalidate_legacy_projection_v1
AFTER INSERT OR UPDATE OR DELETE ON {schema}."{table}"
FOR EACH ROW EXECUTE FUNCTION {schema}.invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER truncate_legacy_projection_v1 AFTER TRUNCATE ON {schema}."{table}"
FOR EACH STATEMENT EXECUTE FUNCTION {schema}.invalidate_legacy_projection_v1();
'''
    return sql


def migration_sql():
    return ("BEGIN;\nSET LOCAL lock_timeout='5s';\n" + derived_ddl("vantaline") +
            "INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)\n"
            f"VALUES ('{VERSION}',EXTRACT(EPOCH FROM NOW())::BIGINT,"
            "'{\"strategy\":\"expand\",\"derived_only\":true}'::jsonb) ON CONFLICT(version) DO NOTHING;\nCOMMIT;\n")
