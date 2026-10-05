BEGIN;
SET LOCAL lock_timeout = '5s';
SET search_path TO vantaline, public;
CREATE TABLE IF NOT EXISTS label_run_projection (
 id TEXT PRIMARY KEY, projection_version BIGINT NOT NULL, raw_json JSONB NOT NULL
);
CREATE OR REPLACE FUNCTION "vantaline".invalidate_label_run_projection()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $label_projection$
BEGIN
    IF TG_TABLE_SCHEMA <> 'vantaline' OR TG_TABLE_NAME <> 'label_inspection_objects'
       OR TG_WHEN <> 'AFTER' OR TG_LEVEL <> 'ROW' THEN
        RAISE EXCEPTION 'Invalid label projection trigger source';
    END IF;
    IF TG_OP = 'DELETE' THEN
        DELETE FROM "vantaline".label_run_projection WHERE id = OLD.id;
        RETURN NULL;
    ELSIF TG_OP = 'INSERT' THEN
        DELETE FROM "vantaline".label_run_projection WHERE id = NEW.id;
        RETURN NULL;
    ELSIF TG_OP = 'UPDATE' THEN
        DELETE FROM "vantaline".label_run_projection WHERE id IN (OLD.id, NEW.id);
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'Invalid label projection trigger operation';
END;
$label_projection$;
CREATE OR REPLACE TRIGGER invalidate_label_run_projection
AFTER INSERT OR UPDATE OR DELETE ON "vantaline".label_inspection_objects
FOR EACH ROW EXECUTE FUNCTION "vantaline".invalidate_label_run_projection();
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)
VALUES ('2026_10_04_label_run_projection',EXTRACT(EPOCH FROM NOW())::BIGINT,'{"strategy":"expand","consumer":"label-run-projection-preparation"}'::jsonb)
ON CONFLICT(version) DO NOTHING;
COMMIT;
