"""List-only compaction of shallow Beta label evidence with unchanged JSON errors.

Unknown top-level fields and numeric/nested label entries stay intact. The caller
supplies a trusted qualified table; account identity remains a bound parameter.
"""

_QUERY = r'''
SELECT CASE WHEN jsonb_typeof(raw_json)='object' THEN
 CASE WHEN jsonb_typeof(raw_json->'labels')='object' THEN
  jsonb_set(raw_json,'{labels}',COALESCE((
   SELECT jsonb_object_agg(entry.key,
    CASE WHEN jsonb_typeof(entry.value)='object' THEN
     CASE WHEN NOT EXISTS (
      SELECT 1 FROM jsonb_each(entry.value) AS part
      WHERE jsonb_typeof(part.value) NOT IN ('string','boolean','null')
     ) THEN '{}'::jsonb ELSE entry.value END
    ELSE entry.value END)
   FROM jsonb_each(raw_json->'labels') AS entry
  ),'{}'::jsonb),false)
 ELSE raw_json END
ELSE raw_json END AS raw_json,
CASE jsonb_typeof(raw_json->'inputs'->'references')
 WHEN 'object' THEN (SELECT count(*) FROM jsonb_object_keys(raw_json->'inputs'->'references'))
 WHEN 'array' THEN jsonb_array_length(raw_json->'inputs'->'references')
END AS reference_count,
CASE jsonb_typeof(raw_json->'labels')
 WHEN 'object' THEN (SELECT count(*) FROM jsonb_object_keys(raw_json->'labels'))
 WHEN 'array' THEN jsonb_array_length(raw_json->'labels')
END AS label_count
FROM (
 SELECT CASE WHEN jsonb_typeof(raw_json)='object' THEN raw_json || '{}'::jsonb ELSE raw_json END AS raw_json
 FROM {table} WHERE owner_user_id=%s OFFSET 0
) decoded
'''


def beta_history_query(table: str) -> str:
    return _QUERY.replace("{table}", table)
