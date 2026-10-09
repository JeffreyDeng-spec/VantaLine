"""Owner/task/capture duplicate lookup shared by inspection admission and reviews."""
from collections.abc import Callable

from .incoming_ports import IncomingWrites, Record


def lookup_duplicate(
    writes: IncomingWrites,
    decode_rows: Callable[[], Callable[[list[Record]], list[Record]]],
    all_records: Callable[[], list[Record]],
    owner_user_id: str, task_id: str, capture_id: str,
) -> Record | None:
    repository = writes.repository()
    if repository is not None:
        row = repository.fetch_one_by_columns(
            "incoming_text_inspections",
            {"owner_user_id": owner_user_id, "task_id": task_id, "capture_id": capture_id},
        )
        values = decode_rows()([row]) if row else []
        return values[0] if values else None
    return next(
        (
            item
            for item in all_records()
            if str(item.get("owner_user_id")) == owner_user_id
            and str(item.get("task_id")) == task_id
            and str(item.get("capture_id")) == capture_id
        ),
        None,
    )
