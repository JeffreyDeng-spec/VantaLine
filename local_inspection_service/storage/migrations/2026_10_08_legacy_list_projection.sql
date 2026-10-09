BEGIN;
SET LOCAL lock_timeout='5s';

CREATE TABLE IF NOT EXISTS "vantaline".legacy_projection_epoch (
 owner_user_id TEXT PRIMARY KEY, sequence BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS "vantaline".legacy_projection_ready (
 owner_user_id TEXT PRIMARY KEY, sequence BIGINT NOT NULL, projection_version BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS "vantaline".legacy_projection_rows (
 owner_user_id TEXT NOT NULL, group_id TEXT NOT NULL, kind TEXT NOT NULL,
 ordinal BIGINT NOT NULL, raw_json JSONB NOT NULL,
 PRIMARY KEY(owner_user_id,group_id,kind,ordinal)
);
CREATE OR REPLACE FUNCTION "vantaline".invalidate_legacy_projection_v1()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $legacy_projection$
DECLARE identity TEXT;
BEGIN
 IF TG_TABLE_SCHEMA <> 'vantaline' OR TG_TABLE_NAME NOT IN ('text_inspection_standards','text_inspection_manual_sessions','text_inspection_manual_pages','text_inspection_records','text_inspection_assets') OR TG_WHEN <> 'AFTER' THEN
  RAISE EXCEPTION 'Invalid manual projection trigger source';
 END IF;
 IF TG_OP='TRUNCATE' AND TG_LEVEL='STATEMENT' THEN
  UPDATE "vantaline".legacy_projection_epoch SET sequence=sequence+1;
  DELETE FROM "vantaline".legacy_projection_ready;
  RETURN NULL;
 END IF;
 IF TG_LEVEL <> 'ROW' OR TG_OP NOT IN ('INSERT','UPDATE','DELETE') THEN
  RAISE EXCEPTION 'Invalid manual projection trigger operation';
 END IF;
 FOR identity IN SELECT DISTINCT value COLLATE "C" AS value FROM unnest(ARRAY[
  CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN OLD.owner_user_id END,
  CASE WHEN TG_OP IN ('UPDATE','INSERT') THEN NEW.owner_user_id END
 ]) value WHERE value IS NOT NULL ORDER BY value COLLATE "C" LOOP
  INSERT INTO "vantaline".legacy_projection_epoch(owner_user_id,sequence) VALUES(identity,1)
  ON CONFLICT(owner_user_id) DO UPDATE SET sequence="vantaline".legacy_projection_epoch.sequence+1;
  DELETE FROM "vantaline".legacy_projection_ready WHERE owner_user_id=identity;
 END LOOP;
 RETURN NULL;
END;
$legacy_projection$;
CREATE OR REPLACE TRIGGER invalidate_legacy_projection_v1
AFTER INSERT OR UPDATE OR DELETE ON "vantaline"."text_inspection_standards"
FOR EACH ROW EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER truncate_legacy_projection_v1 AFTER TRUNCATE ON "vantaline"."text_inspection_standards"
FOR EACH STATEMENT EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER invalidate_legacy_projection_v1
AFTER INSERT OR UPDATE OR DELETE ON "vantaline"."text_inspection_manual_sessions"
FOR EACH ROW EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER truncate_legacy_projection_v1 AFTER TRUNCATE ON "vantaline"."text_inspection_manual_sessions"
FOR EACH STATEMENT EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER invalidate_legacy_projection_v1
AFTER INSERT OR UPDATE OR DELETE ON "vantaline"."text_inspection_manual_pages"
FOR EACH ROW EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER truncate_legacy_projection_v1 AFTER TRUNCATE ON "vantaline"."text_inspection_manual_pages"
FOR EACH STATEMENT EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER invalidate_legacy_projection_v1
AFTER INSERT OR UPDATE OR DELETE ON "vantaline"."text_inspection_records"
FOR EACH ROW EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER truncate_legacy_projection_v1 AFTER TRUNCATE ON "vantaline"."text_inspection_records"
FOR EACH STATEMENT EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER invalidate_legacy_projection_v1
AFTER INSERT OR UPDATE OR DELETE ON "vantaline"."text_inspection_assets"
FOR EACH ROW EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
CREATE OR REPLACE TRIGGER truncate_legacy_projection_v1 AFTER TRUNCATE ON "vantaline"."text_inspection_assets"
FOR EACH STATEMENT EXECUTE FUNCTION "vantaline".invalidate_legacy_projection_v1();
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)
VALUES ('2026_10_08_legacy_list_projection',EXTRACT(EPOCH FROM NOW())::BIGINT,'{"strategy":"expand","derived_only":true}'::jsonb) ON CONFLICT(version) DO NOTHING;
COMMIT;
