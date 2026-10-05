# Frozen from c798ac8f6acc439851421b2f2a1bc2296f99ca44 storage/label_inspection.py.
def list_run_payloads_for_tasks(self, owner, task_ids):
    """Return bounded list-only run payloads without fields public() discards."""
    if not task_ids:
        return {}
    if len(task_ids) > RUN_BATCH_SIZE:
        raise ValueError("run batch exceeds limit")
    discarded = ("model", "prompt_hash", "layout", "transformations", "profile_snapshot")
    with self.read_tx() as c:
        c.execute(
            f"SELECT task_id, CASE WHEN jsonb_typeof(raw_json)='object' "
            "AND raw_json->>'kind'='run' THEN raw_json - %s::text[] "
            f"ELSE raw_json END AS raw_json FROM {self.table} "
            "WHERE owner_user_id=%s AND kind='run' AND task_id=ANY(%s::text[]) "
            "ORDER BY created_at DESC,id DESC",
            (list(discarded), owner, list(task_ids)),
        )
        grouped = {task_id: [] for task_id in task_ids}
        for row in c.fetchall():
            value = self.repository._row_to_dict(c, row)
            grouped[value["task_id"]].append(value["raw_json"])
        return grouped
