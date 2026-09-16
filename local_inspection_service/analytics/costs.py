"""Cost aggregation independent of HTTP, filesystem and database connections."""
from collections.abc import Callable, Iterable
import hashlib
import time
from pathlib import Path
from typing import Any, Protocol

from .cost_pricing import (
    API_COST_CATEGORY_LABELS, api_cost_classify, api_cost_day,
    api_cost_from_usage, runpod_gpu_usd_per_second,
)


class CostSource(Protocol):
    def store_payloads(self) -> Iterable[tuple[Path, Any]]: ...
    def metadata_payloads(self) -> Iterable[tuple[Path, Any]]: ...
    def training_tasks(self) -> list[dict[str, Any]]: ...
    def auto_states(self) -> list[dict[str, Any]]: ...


class CostLedger:
    def __init__(self, repository: CostSource, timestamp: Callable[[Any], int]):
        self.repository = repository
        self.timestamp = timestamp

    def walk_usage(self, payload: Any, path: Path, pointer: str = "") -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            usage = payload.get("usage_metadata")
            if isinstance(usage, dict) and usage:
                model = str(
                    payload.get("model")
                    or payload.get("provider_model")
                    or payload.get("image_model")
                    or payload.get("fallback_model")
                    or ""
                )
                if not model:
                    parent = payload.get("ai") if isinstance(payload.get("ai"), dict) else {}
                    model = str(parent.get("provider_model") or "")
                category, subcategory = api_cost_classify(path, payload)
                created_at = payload.get("created_at") or payload.get("completed_at") or payload.get("updated_at") or payload.get("timestamp")
                cost, tokens, priced = api_cost_from_usage(model, usage)
                records.append(
                    {
                        "id": hashlib.sha1(f"{path}:{pointer}".encode("utf-8")).hexdigest()[:16],
                        "path": str(path),
                        "pointer": pointer,
                        "category": category,
                        "subcategory": subcategory,
                        "model": model or "unknown",
                        "created_at": self.timestamp(created_at) or 0,
                        "day": api_cost_day(created_at),
                        "usage_metadata": usage,
                        "tokens": tokens,
                        "cost_usd": cost,
                        "priced": priced,
                        "estimated": False,
                    }
                )
            for key, value in payload.items():
                if key in {"bytes", "image_bytes", "api_key", "image_api_key"}:
                    continue
                next_pointer = f"{pointer}/{key}" if pointer else str(key)
                records.extend(self.walk_usage(value, path, next_pointer))
        elif isinstance(payload, list):
            for index, value in enumerate(payload):
                records.extend(self.walk_usage(value, path, f"{pointer}/{index}" if pointer else str(index)))
        return records


    def training_records(self) -> list[dict[str, Any]]:
        """RunPod training runs billed per GPU-second of worker execution time.

        RunPod's status responses expose `executionTime` in milliseconds; runs
        without it (failed before start, legacy Windows-worker records) are listed
        as unpriced calls instead of being silently dropped."""
        records: list[dict[str, Any]] = []
        rate = runpod_gpu_usd_per_second()
        for task in self.repository.training_tasks():
            if str(task.get("training_executor") or "").strip().lower() != "runpod":
                continue
            response = task.get("remote_training_response") if isinstance(task.get("remote_training_response"), dict) else {}
            job_id = str(task.get("job_id") or task.get("task_id") or "").strip() or "unknown"
            created_at = self.timestamp(
                task.get("completed_at") or task.get("updated_at") or task.get("created_at")
            )
            try:
                execution_seconds = max(0.0, float(response.get("executionTime") or 0) / 1000.0)
            except (TypeError, ValueError):
                execution_seconds = 0.0
            priced = execution_seconds > 0
            records.append(
                {
                    "id": hashlib.sha1(f"runpod_training:{job_id}".encode("utf-8")).hexdigest()[:16],
                    "path": f"training_tasks/{job_id}",
                    "pointer": "remote_training_response/executionTime",
                    "category": "training",
                    "subcategory": "RunPod YOLO 训练",
                    "model": "runpod-a5000-flex",
                    "created_at": created_at,
                    "day": api_cost_day(created_at),
                    "usage_metadata": {
                        "execution_seconds": round(execution_seconds, 3),
                        "delay_ms": response.get("delayTime") or 0,
                        "status": str(task.get("status") or ""),
                    },
                    "tokens": {},
                    "cost_usd": round(execution_seconds * rate, 6),
                    "priced": priced,
                    "estimated": False,
                }
            )
        return records


    def collect_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        # Store-backed sources first: since the Postgres cutover these tables are
        # the live data; their legacy JSON files are stale snapshots and are no
        # longer read directly (that also avoids double counting).
        for path, payload in self.repository.store_payloads():
            for record in self.walk_usage(payload, path):
                if record["id"] in seen_ids:
                    continue
                seen_ids.add(record["id"])
                records.append(record)
        for path, payload in self.repository.metadata_payloads():
            for record in self.walk_usage(payload, path):
                if record["id"] in seen_ids:
                    continue
                seen_ids.add(record["id"])
                records.append(record)
        for record in self.training_records():
            if record["id"] in seen_ids:
                continue
            seen_ids.add(record["id"])
            records.append(record)
        records.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
        return records


    def summary(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        records = [record for record in records if not record.get("estimated")]
        categories: dict[str, dict[str, Any]] = {}
        daily: dict[str, dict[str, Any]] = {}
        for key, label in API_COST_CATEGORY_LABELS.items():
            categories[key] = {
                "key": key,
                "label": label,
                "call_count": 0,
                "priced_call_count": 0,
                "estimated_call_count": 0,
                "unpriced_call_count": 0,
                "cost_usd": 0.0,
                "subcategories": {},
            }
        for record in records:
            category_key = str(record.get("category") or "structured_output")
            category = categories.setdefault(
                category_key,
                {
                    "key": category_key,
                    "label": API_COST_CATEGORY_LABELS.get(category_key, category_key),
                    "call_count": 0,
                    "priced_call_count": 0,
                    "estimated_call_count": 0,
                    "unpriced_call_count": 0,
                    "cost_usd": 0.0,
                    "subcategories": {},
                },
            )
            cost = float(record.get("cost_usd") or 0.0)
            category["call_count"] += 1
            category["cost_usd"] += cost
            if record.get("estimated"):
                category["estimated_call_count"] += 1
            if record.get("priced"):
                category["priced_call_count"] += 1
            else:
                category["unpriced_call_count"] += 1
            sub_key = str(record.get("subcategory") or "其他")
            sub = category["subcategories"].setdefault(sub_key, {"label": sub_key, "call_count": 0, "cost_usd": 0.0})
            sub["call_count"] += 1
            sub["cost_usd"] += cost
            day = str(record.get("day") or api_cost_day(record.get("created_at")))
            day_row = daily.setdefault(day, {"date": day, "total_cost_usd": 0.0, "call_count": 0})
            day_row["total_cost_usd"] += cost
            day_row["call_count"] += 1
            day_row[category_key] = float(day_row.get(category_key) or 0.0) + cost
        category_rows = []
        for category in categories.values():
            call_count = max(1, int(category["call_count"]))
            sub_rows = list(category["subcategories"].values())
            sub_rows.sort(key=lambda item: float(item.get("cost_usd") or 0.0), reverse=True)
            category_rows.append(
                {
                    **{key: value for key, value in category.items() if key != "subcategories"},
                    "cost_usd": round(float(category["cost_usd"]), 6),
                    "avg_cost_usd": round(float(category["cost_usd"]) / call_count, 6) if category["call_count"] else 0.0,
                    "subcategories": [
                        {**sub, "cost_usd": round(float(sub.get("cost_usd") or 0.0), 6)}
                        for sub in sub_rows
                    ],
                }
            )
        category_rows.sort(key=lambda item: float(item.get("cost_usd") or 0.0), reverse=True)
        total_cost = sum(float(record.get("cost_usd") or 0.0) for record in records)
        known_records = [record for record in records if not record.get("estimated")]
        estimated_records = [record for record in records if record.get("estimated")]
        image_records = [record for record in records if record.get("category") == "image_generation"]
        training_sample_count = 0
        for payload in self.repository.auto_states():
            samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
            training_sample_count += len([sample for sample in samples if isinstance(sample, dict) and sample.get("label_status") in {"trainable", "negative"}])
        return {
            "currency": "USD",
            "updated_at": int(time.time()),
            "pricing_source": "Configured from Gemini API public pricing, Alibaba Cloud Model Studio Qwen international first-tier token pricing, and RunPod serverless per-GPU-second pricing (A5000 flex); calls without provider-returned usage metadata are not estimated.",
            "summary": {
                "total_cost_usd": round(total_cost, 6),
                "known_cost_usd": round(sum(float(record.get("cost_usd") or 0.0) for record in known_records), 6),
                "estimated_cost_usd": round(sum(float(record.get("cost_usd") or 0.0) for record in estimated_records), 6),
                "call_count": len(records),
                "priced_call_count": len([record for record in records if record.get("priced")]),
                "estimated_call_count": len(estimated_records),
                "unpriced_call_count": len([record for record in records if not record.get("priced")]),
                "avg_cost_per_call_usd": round(total_cost / len(records), 6) if records else 0.0,
                "avg_image_generation_cost_usd": round(
                    sum(float(record.get("cost_usd") or 0.0) for record in image_records) / len(image_records),
                    6,
                )
                if image_records
                else 0.0,
                "training_sample_count": training_sample_count,
                "avg_cost_per_training_sample_usd": round(total_cost / training_sample_count, 6) if training_sample_count else 0.0,
            },
            "categories": category_rows,
            "daily": [
                {
                    **row,
                    "total_cost_usd": round(float(row.get("total_cost_usd") or 0.0), 6),
                    "image_generation": round(float(row.get("image_generation") or 0.0), 6),
                    "structured_output": round(float(row.get("structured_output") or 0.0), 6),
                    "agent": round(float(row.get("agent") or 0.0), 6),
                    "training": round(float(row.get("training") or 0.0), 6),
                }
                for row in sorted(daily.values(), key=lambda item: item["date"])[-30:]
            ],
            "recent_calls": [
                {
                    "id": record.get("id"),
                    "day": record.get("day"),
                    "category": record.get("category"),
                    "subcategory": record.get("subcategory"),
                    "model": record.get("model"),
                    "cost_usd": round(float(record.get("cost_usd") or 0.0), 6),
                    "priced": bool(record.get("priced")),
                    "estimated": bool(record.get("estimated")),
                }
                for record in records[:80]
            ],
        }

