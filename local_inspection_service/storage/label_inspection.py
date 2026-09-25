"""Durable Word tasks, immutable revisions, and globally bounded paid-call claims."""

import copy
import json
import time
import uuid
from contextlib import contextmanager
from ..codex_compare.contracts import digest, encode
from .agent_operations import OperationConflict

TABLE = "label_inspection_objects"
ACTIVE = {"queued", "running"}
RUN_BATCH_SIZE = 64


class LabelRepository:
    def __init__(self, repository):
        self.repository = repository
        self._legacy_cache = {}
        self.table = repository._qualified_table(TABLE)

    @contextmanager
    def tx(self):
        c = self.repository._cursor()
        try:
            c.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('label-inspection-v1',0))"
            )
            yield c
            self.repository.connection.commit()
        except Exception:
            self.repository.connection.rollback()
            raise
        finally:
            c.close()

    @contextmanager
    def read_tx(self):
        """Short PostgreSQL read transaction without the global write fence."""
        c = self.repository._cursor()
        try:
            yield c
            self.repository.connection.commit()
        except Exception:
            self.repository.connection.rollback()
            raise
        finally:
            c.close()

    def rows(self, c):
        rows = []
        for row in c.fetchall():
            v = self.repository._row_to_dict(c, row)["raw_json"]
            if isinstance(v, str):
                v = json.loads(v)
            rows.append(v)
        return rows

    def read(self, c, owner, identity, kind=None):
        c.execute(
            f"SELECT raw_json FROM {self.table} WHERE owner_user_id=%s AND id=%s",
            (owner, identity),
        )
        values = self.rows(c)
        v = values[0] if values else None
        return v if v and (not kind or v["kind"] == kind) else None

    def get(self, owner, identity, kind=None):
        with self.tx() as c:
            return self.read(c, owner, identity, kind)

    def put(self, c, value, insert=False):
        fields = (
            "id",
            "owner_user_id",
            "task_id",
            "kind",
            "status",
            "created_at",
            "updated_at",
            "idempotency_key",
        )
        value["updated_at"] = time.time()
        sql = f"INSERT INTO {self.table} ({','.join(fields)},raw_json) VALUES ({','.join(['%s']*len(fields))},%s::jsonb)"
        if not insert:
            sql += " ON CONFLICT(id) DO UPDATE SET status=EXCLUDED.status, updated_at=EXCLUDED.updated_at, raw_json=EXCLUDED.raw_json"
        c.execute(
            sql,
            tuple(int(value[k]) if k.endswith("_at") else value[k] for k in fields)
            + (encode(value),),
        )

    def new(self, owner, task, kind, key, **fields):
        now = time.time()
        return {
            "id": "li_" + uuid.uuid4().hex,
            "owner_user_id": owner,
            "task_id": task,
            "kind": kind,
            "status": "ready",
            "created_at": now,
            "updated_at": now,
            "idempotency_key": key,
            **fields,
        }

    def prior(self, c, owner, kind, key, parameters):
        c.execute(
            f"SELECT raw_json FROM {self.table} WHERE owner_user_id=%s AND kind=%s AND idempotency_key=%s",
            (owner, kind, key),
        )
        rows = self.rows(c)
        if rows and rows[0].get("parameters") != digest(parameters):
            raise OperationConflict("同一请求标识对应不同内容，请重新操作")
        return rows[0] if rows else None

    def page(self, owner, rows, filters, limit, cursor=""):
        """Stable cross-source traversal even when a task moves during pagination."""
        with self.tx() as c:
            offset = 0
            if cursor:
                try:
                    identity, raw_offset = cursor.rsplit(".", 1)
                    offset = int(raw_offset)
                    if offset < 0:
                        raise ValueError()
                except Exception:
                    raise ValueError("分页位置无效") from None
                snapshot = self.read(c, owner, identity, "page")
                if not snapshot:
                    raise KeyError(identity)
                if snapshot["filters"] != digest(filters):
                    raise ValueError("分页筛选条件已变化，请刷新列表")
                if snapshot["created_at"] + 900 < time.time():
                    raise ValueError("分页已过期，请刷新列表")
                rows = snapshot["items"]
            elif len(rows) > limit:
                c.execute(
                    f"DELETE FROM {self.table} WHERE kind='page' AND created_at < %s",
                    (int(time.time()) - 900,),
                )
                snapshot = self.new(
                    owner,
                    "",
                    "page",
                    uuid.uuid4().hex,
                    filters=digest(filters),
                    items=rows,
                )
                self.put(c, snapshot, True)
            else:
                return {"items": rows, "next_cursor": None}
            selected = rows[offset : offset + limit]
            next_offset = offset + len(selected)
            return {
                "items": selected,
                "next_cursor": (
                    f"{snapshot['id']}.{next_offset}"
                    if next_offset < len(rows)
                    else None
                ),
            }

    def request_run(self, owner, key):
        with self.tx() as c:
            c.execute(
                f"SELECT raw_json FROM {self.table} WHERE owner_user_id=%s AND kind='run' AND idempotency_key=%s",
                (owner, key),
            )
            rows = self.rows(c)
            return rows[0] if rows else None

    def lookup(self, owner, kind, key, parameters):
        with self.tx() as c:
            return self.prior(c, owner, kind, key, parameters)

    def create(self, owner, key, name, assets, source=None, legacy_id=""):
        parameters = {
            "name": name,
            "assets": assets,
            "source": source,
            "legacy_id": legacy_id,
        }
        with self.tx() as c:
            old = self.prior(c, owner, "task", key, parameters)
            if old:
                return self.read(c, owner, old["id"])
            task = self.new(
                owner,
                "",
                "task",
                key,
                name=name,
                source=source,
                legacy_id=legacy_id,
                revision=1,
                parameters=digest(parameters),
                assets=assets,
            )
            task["task_id"] = task["id"]
            self.put(c, task, True)
            self.revision(c, task)
            return task

    def create_pdf(self, owner, key, name, source, entries, version):
        parameters = {
            "name": name,
            "source": source,
            "entries": entries,
            "version": version,
        }
        with self.tx() as c:
            old = self.prior(c, owner, "task", key, parameters)
            if old:
                return old
            task = self.new(
                owner,
                "",
                "task",
                key,
                name=name,
                source=source,
                revision=0,
                assets=[],
                parameters=digest(parameters),
                status="import_queued",
                **{
                    "import": {
                        "version": version,
                        "entries": entries,
                        "assets": [],
                        "completed": 0,
                        "total": len(entries),
                    }
                },
            )
            task["task_id"] = task["id"]
            self.put(c, task, True)
            return task

    def claim_pdf(self, token):
        with self.tx() as c:
            c.execute(
                f"SELECT raw_json FROM {self.table} WHERE kind='task' AND status IN ('import_queued','import_running') ORDER BY created_at,id"
            )
            tasks = self.rows(c)
            if any(
                t["status"] == "import_running"
                and t["import"].get("lease_until", 0) > time.time()
                for t in tasks
            ):
                return None
            if not tasks:
                return None
            task = tasks[0]
            task["status"] = "import_running"
            task["import"].update(token=token, lease_until=time.time() + 300)
            self.put(c, task)
            return task

    def pdf_progress(self, owner, identity, token, assets, complete=False, error=None):
        with self.tx() as c:
            task = self.read(c, owner, identity, "task")
            if (
                not task
                or task["status"] != "import_running"
                or task["import"].get("token") != token
            ):
                return False
            if error:
                task.update(status="import_failed")
                task["import"]["error"] = error
            else:
                task["import"].update(
                    assets=assets, completed=len(assets), lease_until=time.time() + 300
                )
                if complete:
                    if len(assets) != task["import"]["total"]:
                        raise ValueError("PDF 页面尚未全部完成")
                    task.update(status="ready", assets=assets, revision=1)
                    self.revision(c, task)
                    task["import"].pop("assets", None)
            self.put(c, task)
            return True

    def revision(self, c, task):
        value = self.new(
            task["owner_user_id"],
            task["id"],
            "revision",
            f"{task['id']}:{task['revision']}",
            revision=task["revision"],
            assets=copy.deepcopy(task["assets"]),
        )
        self.put(c, value, True)

    def edit(self, owner, identity, key, expected, operation, parameters, change):
        params = {
            "task": identity,
            "expected": expected,
            "operation": operation,
            "value": parameters,
        }
        with self.tx() as c:
            old = self.prior(c, owner, "edit", key, params)
            task = self.read(c, owner, identity, "task")
            if not task:
                raise KeyError(identity)
            if old:
                return task
            if task.get("status", "ready") != "ready":
                raise OperationConflict("PDF 尚未完成导入，不能修改标准")
            if task["revision"] != expected:
                raise OperationConflict("标准版本已更新，请刷新后操作")
            change(task)
            if operation != "name":
                task["revision"] += 1
                self.revision(c, task)
            self.put(c, task)
            self.put(
                c,
                self.new(
                    owner,
                    identity,
                    "edit",
                    key,
                    parameters=digest(params),
                    operation=operation,
                ),
                True,
            )
            return task

    def list(self, owner, kind, task=None):
        with self.read_tx() as c:
            c.execute(
                f"SELECT raw_json FROM {self.table} WHERE owner_user_id=%s AND kind=%s"
                + (" AND task_id=%s" if task else "")
                + " ORDER BY created_at DESC,id DESC",
                (owner, kind, task) if task else (owner, kind),
            )
            return self.rows(c)

    def runs_for_tasks(self, owner, task_ids):
        """Read one bounded page of owned runs for task-list projection."""
        if not task_ids:
            return {}
        if len(task_ids) > RUN_BATCH_SIZE:
            raise ValueError("run batch exceeds limit")
        with self.read_tx() as c:
            c.execute(
                f"SELECT task_id,raw_json FROM {self.table} "
                "WHERE owner_user_id=%s AND kind='run' AND task_id=ANY(%s::text[]) "
                "ORDER BY created_at DESC,id DESC",
                (owner, list(task_ids)),
            )
            grouped = {task_id: [] for task_id in task_ids}
            for row in c.fetchall():
                value = self.repository._row_to_dict(c, row)
                grouped[value["task_id"]].append(value["raw_json"])
            return grouped

    def legacy(self, owner, kind):
        if (owner, kind) in self._legacy_cache:
            return self._legacy_cache[(owner, kind)]
        tables = {
            "standards": "text_inspection_standards",
            "records": "text_inspection_records",
            "beta": "codex_comparison_tasks",
            "assets": "text_inspection_assets",
            "sessions": "text_inspection_manual_sessions",
            "pages": "text_inspection_manual_pages",
        }
        table = self.repository._qualified_table(tables[kind])
        with self.read_tx() as c:
            c.execute(f"SELECT raw_json FROM {table} WHERE owner_user_id=%s", (owner,))
            values = self.rows(c)
            self._legacy_cache[(owner, kind)] = values
            return values

    def expire(self, c):
        c.execute(
            f"SELECT raw_json FROM {self.table} WHERE kind='run' AND status='running'"
        )
        for row in self.rows(c):
            if time.time() > row["deadline"]:
                row.update(
                    status="interrupted",
                    decision="REVIEW_REQUIRED",
                    error="检测超时或服务中断；未自动重试",
                    finished_at=time.time(),
                )
                self.put(c, row)
                task = self.read(c, row["owner_user_id"], row["task_id"], "task")
                if task:
                    self.put(c, task)
                c.execute(
                    f"SELECT raw_json FROM {self.table} WHERE kind='call' AND status='running' AND task_id=%s",
                    (row["task_id"],),
                )
                for call in self.rows(c):
                    if call["run_id"] == row["id"]:
                        call.update(
                            status="unknown",
                            error="检测期限已过，调用结果未知；未自动重试",
                        )
                        self.put(c, call)

    def submit(
        self,
        owner,
        identity,
        key,
        revision,
        asset_id,
        actual,
        model,
        prompt_hash,
        parent="",
        profile_snapshot=None,
    ):
        from ..label_inspection.quality import POLICY

        parameters = {
            "task": identity,
            "revision": revision,
            "asset": asset_id,
            "actual": actual,
            "model": model,
            "prompt_hash": prompt_hash,
            "parent": parent,
        }
        with self.tx() as c:
            old = self.prior(c, owner, "run", key, parameters)
            if old:
                return old
            task = self.read(c, owner, identity, "task")
            if not task:
                raise KeyError(identity)
            if task.get("status", "ready") != "ready":
                raise OperationConflict("PDF 尚未完成导入，不能检测")
            if task["revision"] != revision:
                raise OperationConflict("标准版本已更新，请重新选择")
            ref = next(
                (
                    a
                    for a in task["assets"]
                    if a["id"] == asset_id and a.get("enabled") and a.get("media")
                ),
                None,
            )
            if not ref:
                raise ValueError("请选择有效且未隐藏的标准图片")
            self.expire(c)
            c.execute(
                f"SELECT id FROM {self.table} WHERE task_id=%s AND kind='run' AND status IN ('queued','running')",
                (identity,),
            )
            if c.fetchone():
                raise OperationConflict("这个任务已有检测排队或进行中")
            if parent:
                previous = self.read(c, owner, parent, "run")
                if not previous or previous["task_id"] != identity:
                    raise KeyError(parent)
            from ..label_inspection import manual

            is_pdf = (task.get("source") or {}).get("type") == "pdf"
            run = self.new(
                owner,
                identity,
                "run",
                key,
                status="queued",
                parameters=digest(parameters),
                revision=revision,
                reference=copy.deepcopy(ref),
                actual=actual,
                model=model,
                profile_snapshot=copy.deepcopy(profile_snapshot),
                prompt_hash=prompt_hash,
                parent_id=parent,
                decision="REVIEW_REQUIRED",
                phase="queued",
                strategy=manual.VERSION if is_pdf else "label",
                quality={"policy": copy.deepcopy(manual.POLICY if is_pdf else POLICY)},
            )
            self.put(c, run, True)
            self.put(c, task)
            return run

    def claim(self):
        with self.tx() as c:
            self.expire(c)
            c.execute(
                f"SELECT count(*) FROM {self.table} WHERE kind='run' AND status='running'"
            )
            if c.fetchone()[0] >= 2:
                return None
            c.execute(
                f"SELECT raw_json FROM {self.table} WHERE kind='run' AND status='queued' ORDER BY created_at,id LIMIT 1"
            )
            rows = self.rows(c)
            if not rows:
                return None
            run = rows[0]
            run.update(
                status="running",
                phase="quality",
                started_at=time.time(),
                deadline=time.time() + 420,
            )
            self.put(c, run)
            return run

    def active(self, c, owner, identity):
        run = self.read(c, owner, identity, "run")
        if not run or run["status"] != "running" or time.time() > run["deadline"]:
            raise OperationConflict("检测已结束或中断，拒绝迟到结果")
        return run

    def update_run(self, owner, identity, **values):
        with self.tx() as c:
            run = self.active(c, owner, identity)
            run.update(values)
            self.put(c, run)
            task = self.read(c, owner, run["task_id"], "task")
            self.put(c, task)
            return run

    def begin_call(self, owner, identity, stage, audit, images):
        with self.tx() as c:
            run = self.active(c, owner, identity)
            key = f"{identity}:{stage}"
            c.execute(
                f"SELECT id FROM {self.table} WHERE owner_user_id=%s AND kind='call' AND idempotency_key=%s",
                (owner, key),
            )
            if c.fetchone():
                raise OperationConflict("该阶段已调用或结果未知，不允许自动重试")
            value = self.new(
                owner,
                run["task_id"],
                "call",
                key,
                run_id=identity,
                stage=stage,
                status="running",
                request=audit,
                images=images,
            )
            self.put(c, value, True)
            return value

    def finish_call(self, owner, identity, **values):
        with self.tx() as c:
            call = self.read(c, owner, identity, "call")
            if not call or call["status"] != "running":
                raise OperationConflict("调用证据已完成")
            call.update(values)
            self.put(c, call)
            return call
