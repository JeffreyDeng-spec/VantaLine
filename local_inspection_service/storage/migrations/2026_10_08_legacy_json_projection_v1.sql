BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE FUNCTION vantaline.legacy_json_projection_v1(raw_json jsonb, fields text[])
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE STRICT SECURITY INVOKER
SET search_path = pg_catalog
AS $legacy_json_projection$
DECLARE
    encoded boolean;
    source_text text;
    document json;
    checked_document jsonb;
    projected json;
BEGIN
    encoded := jsonb_typeof(raw_json) = 'string';
    source_text := CASE WHEN encoded THEN raw_json #>> '{}' ELSE raw_json::text END;
    -- Count original tokens conservatively, including overwritten duplicate members.
    -- Brackets in strings only exclude additional inputs from this optional path.
    IF length(source_text) - length(replace(replace(source_text, '[', ''), '{', '')) > 16
       OR source_text ~ '[0-9]{255}[0-9]{255}[0-9]{3}' THEN
        RETURN raw_json;
    END IF;
    -- Only source conversion errors may select the unchanged original payload.
    -- Connection, cancellation, permissions, resource and query errors still surface.
    BEGIN
        document := source_text::json;
        IF json_typeof(document) <> 'object' THEN
            RETURN raw_json;
        END IF;
        checked_document := document::jsonb;
    EXCEPTION
        WHEN invalid_text_representation OR numeric_value_out_of_range
             OR untranslatable_character THEN
            RETURN raw_json;
    END;
    SELECT COALESCE(json_object_agg(member.key, member.value ORDER BY member.position), '{}'::json)
    INTO projected
    FROM json_each(document) WITH ORDINALITY AS member(key, value, position)
    WHERE member.key = ANY(fields);
    RETURN CASE WHEN encoded THEN to_jsonb(projected::text) ELSE projected::jsonb END;
END;
$legacy_json_projection$;
INSERT INTO vantaline.feature_migrations(version, applied_at, metadata_json)
VALUES ('2026_10_08_legacy_json_projection_v1', EXTRACT(EPOCH FROM NOW())::BIGINT,
        '{"strategy":"expand","consumer":"legacy-json-projection-preparation"}'::jsonb)
ON CONFLICT(version) DO NOTHING;
COMMIT;
