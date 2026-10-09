"""Explicit derived publication and one-statement legacy-list aggregation.

Unsupported cohorts never publish. Request reads never backfill or change data.
Previously observed legacy data and native extensions retain the original path.
"""
import json
import math
from ..label_inspection import manual_history
from ..comparison_history import project, state
from .legacy_projection_schema import TABLES

VERSION = 2


def _safe_tokens(text):
    # Check the complete token stream, including overwritten duplicate keys.
    # A proof produced by a newer Python must not hide an older decoder error.
    if type(text) is not str or len(text) > 4 * 1024 * 1024:
        return False
    depth = index = 0
    while index < len(text):
        character = text[index]
        if character == '"':
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    break
                index += 1
            if index >= len(text):
                return False
        elif character in "{[":
            depth += 1
            if depth > 32:
                return False
        elif character in "}]":
            depth -= 1
            if depth < 0:
                return False
        elif character in "-0123456789":
            end = index + 1
            while end < len(text) and text[end] in "0123456789.eE+-":
                end += 1
            token = text[index:end]
            if sum(c.isdigit() for c in token) > 128:
                return False
            try:
                number = float(token)
                if not math.isfinite(number) or (number == 0 and token.startswith("-")):
                    return False
            except ValueError:
                return False
            index = end - 1
        elif character.isalpha():
            end = index + 1
            while end < len(text) and text[end].isalpha():
                end += 1
            if text[index:end] not in ("null", "true", "false"):
                return False
            index = end - 1
        index += 1
    return depth == 0


def _decode_source(text):
    if not _safe_tokens(text):
        return None
    try:
        value = json.loads(text)
        if isinstance(value, str):
            if not _safe_tokens(value):
                return None
            value = json.loads(value)
        return value
    except (ValueError, TypeError, RecursionError, OverflowError):
        return None


def _safe_json(value):
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            return False
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                return False
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is int:
            if item.bit_length() > 512:
                return False
        elif type(item) is float:
            if not math.isfinite(item) or (item == 0 and math.copysign(1, item) < 0):
                return False
        elif type(item) not in (str, bool, type(None)):
            return False
    return True


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) <= 2**53


class _ObservedSources:
    def __init__(self, sources):
        self.sources = sources

    def legacy(self, owner, kind):
        return self.sources[kind]


def normalize(sources):
    """Prove the complete decoder input and original manual projection first."""
    for kind in TABLES:
        for row in sources[kind]:
            if not _safe_json(row) or type(row) is not dict or type(row.get("id")) is not str:
                return None
            if any(row.get(key) is not None and type(row[key]) is not str
                   for key in ("standard_id", "session_id")):
                return None
            if not _number(row.get("created_at", 0)) or not _number(row.get("updated_at", row.get("created_at", 0))):
                return None
    if any(not _number(row.get("ordinal", 0)) for row in sources["assets"]):
        return None
    standards = {row["id"]: row for row in sources["standards"]
                 if row.get("standard_type") == "manual"}
    try:
        tasks = manual_history.rows(_ObservedSources(sources), "unused", indexed=True)
        result = []
        for task in tasks:
            if type(task["name"]) is not str:
                return None
            group = task["id"]
            history = task["manual_history"]
            pages = history["pages"]
            # The original source SELECTs are unordered. Physical reordering or
            # a different plan must not change the visible winner of a proof.
            if pages:
                latest_time = max(page.get("created_at", 0) for page in pages)
                winners = [page.get("decision", "REVIEW_REQUIRED") for page in pages
                           if page.get("created_at", 0) == latest_time]
                if len({json.dumps(value, sort_keys=True) for value in winners}) != 1:
                    return None
            result.append((group, "group", 0, {"id": group, "name": task["name"], "source": "legacy_manual", "status": "read_only", "decision": "REVIEW_REQUIRED"}))
            clocks = [standards.get(group.removeprefix(manual_history.PREFIX), {}).get("updated_at", 0)]
            clocks += [row.get("updated_at", row.get("created_at", 0))
                       for row in history["sessions"] + pages]
            highest = max(clocks)
            if len({json.dumps(value) for value in clocks if value == highest}) != 1:
                return None
            for index, stamp in enumerate(clocks):
                result.append((group, "clock", index, {"updated_at": stamp}))
            for index, page in enumerate(pages):
                decision = page.get("decision", "REVIEW_REQUIRED")
                if type(decision) not in (str, type(None)):
                    return None
                result.append((group, "page", index,
                               {"created_at": page.get("created_at", 0), "decision": decision}))
            for index, asset in enumerate(history["standards"]):
                result.append((group, "asset", index, {"id": asset["id"]}))
        label_rows = _normalize_labels(sources)
        return result + label_rows if label_rows is not None else None
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError, OverflowError):
        return None


def _normalize_labels(sources):
    # Same standard visibility and orphan grouping as the original first page.
    known = {row["id"] for row in sources["standards"]}
    referenced = {row.get("standard_id") for row in sources["records"]}
    standards = {row["id"]: row for row in sources["standards"]
                 if row.get("standard_type") == "label" and
                 (row.get("import_source") != "label-batch-v3" or row["id"] in referenced)}
    records = [row for row in sources["records"] if row.get("standard_id") in standards or
               (row.get("standard_id") not in known and row.get("standard_type", "label") == "label")]
    grouped = {}
    for row in records:
        grouped.setdefault(row.get("standard_id") or "orphan-" + row["id"], []).append(row)
    assets = {}
    for row in sources["assets"]:
        assets.setdefault(row.get("standard_id"), []).append(row)
    output = []
    for key in set(standards) | set(grouped):
        standard = standards.get(key, {})
        name = standard.get("name") or "原订单已缺失"
        if type(name) is not str:
            return None
        group = "legacy:" + key
        output.append((group, "group", 0, {"id": group, "name": name, "source": "legacy",
                                           "status": "ready", "decision": "REVIEW_REQUIRED"}))
        clocks = [standard.get("updated_at", 0)]
        for index, record in enumerate(grouped.get(key, [])):
            # The original status changes with wall time without a source write.
            if record.get("status") == "attempting":
                return None
            visible = project(record)
            status = state(visible)
            (visible.get("elapsed_ms") or 0) / 1000
            if not _number(visible["created_at"]) or type(visible["decision"]) not in (str, type(None)):
                return None
            output.append((group, "page", index, {"created_at": visible["created_at"],
                           "sort_id": "legacy:" + record["id"], "decision": visible["decision"], "status": status}))
            clocks.append(record.get("created_at", 0))
        highest = max(clocks)
        if len({json.dumps(value) for value in clocks if value == highest}) != 1:
            return None
        for index, stamp in enumerate(clocks):
            output.append((group, "clock", index, {"updated_at": stamp}))
        if standard:
            for index, asset in enumerate(assets.get(key, [])):
                output.append((group, "asset", index, {"id": asset["id"]}))
    return output


class LegacyListProjection:
    def __init__(self, repository):
        self.repository = repository
        self.epoch = repository._qualified_table("legacy_projection_epoch")
        self.ready = repository._qualified_table("legacy_projection_ready")
        self.rows = repository._qualified_table("legacy_projection_rows")

    def publish(self, owner):
        connection = self.repository.connection
        if connection.autocommit or connection.info.transaction_status != 0:
            raise RuntimeError("Legacy publication requires an idle transaction owner")
        cursor = self.repository._cursor()
        try:
            cursor.execute("SET LOCAL lock_timeout='100ms'")
            cursor.execute(f"INSERT INTO {self.epoch}(owner_user_id,sequence) VALUES(%s,0) ON CONFLICT DO NOTHING", (owner,))
            connection.commit()
            cursor.execute(f"SELECT sequence FROM {self.epoch} WHERE owner_user_id=%s", (owner,))
            initial = self.repository._row_to_dict(cursor, cursor.fetchone())["sequence"]
            sources = {}
            for kind, name in TABLES.items():
                table = self.repository._qualified_table(name)
                cursor.execute(f"SELECT id,raw_json::text AS raw_text FROM {table} WHERE owner_user_id=%s", (owner,))
                values = []
                for row in cursor.fetchall():
                    value = self.repository._row_to_dict(cursor, row)
                    identity, payload = value["id"], _decode_source(value["raw_text"])
                    if type(payload) is not dict or payload.get("id") != identity:
                        connection.rollback()
                        return False
                    values.append(payload)
                sources[kind] = values
            normalized = normalize(sources)
            if normalized is None:
                connection.rollback()
                return False
            cursor.execute("SET LOCAL lock_timeout='100ms'")
            cursor.execute(f"SELECT sequence FROM {self.epoch} WHERE owner_user_id=%s FOR UPDATE", (owner,))
            if self.repository._row_to_dict(cursor, cursor.fetchone())["sequence"] != initial:
                connection.rollback()
                return False
            cursor.execute(f"DELETE FROM {self.rows} WHERE owner_user_id=%s", (owner,))
            cursor.executemany(f"INSERT INTO {self.rows}(owner_user_id,group_id,kind,ordinal,raw_json) VALUES(%s,%s,%s,%s,%s::jsonb)",
                               [(owner, group, kind, ordinal, json.dumps(payload, ensure_ascii=False))
                                for group, kind, ordinal, payload in normalized])
            cursor.execute(f"INSERT INTO {self.ready}(owner_user_id,sequence,projection_version) VALUES(%s,%s,%s) "
                           "ON CONFLICT(owner_user_id) DO UPDATE SET sequence=EXCLUDED.sequence,projection_version=EXCLUDED.projection_version",
                           (owner, initial, VERSION))
            connection.commit()
            return True
        except BaseException:
            connection.rollback()
            raise
        finally:
            cursor.close()

    def read(self, cursor, owner):
        cursor.execute(f'''WITH eligible AS MATERIALIZED (
 SELECT ready.owner_user_id FROM {self.ready} ready JOIN {self.epoch} epoch USING(owner_user_id)
 WHERE ready.owner_user_id=%s AND ready.sequence=epoch.sequence AND ready.projection_version=%s
), selected AS MATERIALIZED (
 SELECT source.* FROM {self.rows} source JOIN eligible USING(owner_user_id)
), output AS (
 SELECT (array_agg(raw_json) FILTER(WHERE kind='group'))[1] || jsonb_build_object(
 'status',CASE WHEN (array_agg(raw_json->>'source') FILTER(WHERE kind='group'))[1]='legacy_manual'
 THEN '"read_only"'::jsonb WHEN count(*) FILTER(WHERE kind='page')=0 THEN '"ready"'::jsonb ELSE
 (array_agg(raw_json->'status' ORDER BY (raw_json->>'created_at')::double precision DESC,(raw_json->>'sort_id') COLLATE "C" DESC,ordinal) FILTER(WHERE kind='page'))[1] END,
 'updated_at',(array_agg(raw_json->'updated_at' ORDER BY (raw_json->>'updated_at')::double precision DESC,ordinal) FILTER(WHERE kind='clock'))[1],
 'run_count',count(*) FILTER(WHERE kind='page'),'standard_count',count(*) FILTER(WHERE kind='asset'),
 'decision',CASE WHEN count(*) FILTER(WHERE kind='page')=0 THEN '"REVIEW_REQUIRED"'::jsonb ELSE
 (array_agg(raw_json->'decision' ORDER BY (raw_json->>'created_at')::double precision DESC,(raw_json->>'sort_id') COLLATE "C" DESC,ordinal) FILTER(WHERE kind='page'))[1] END) AS raw_json
 FROM selected GROUP BY group_id
) SELECT COALESCE((SELECT jsonb_agg(raw_json) FROM output),'[]'::jsonb) AS raw_json FROM eligible''',
                       (owner, VERSION))
        row = cursor.fetchone()
        return self.repository._row_to_dict(cursor, row)["raw_json"] if row is not None else None
