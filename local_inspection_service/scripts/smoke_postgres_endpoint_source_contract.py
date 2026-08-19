#!/usr/bin/env python3
"""Validate the server-side PostgreSQL endpoint integration source contract.

This smoke is static and read-only. It does not import the FastAPI app, open
network sockets, connect to PostgreSQL, or prove production cutover. Its job is
to keep the reviewed runtime repository seam from silently disappearing before
the deployed full-smoke gate runs.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "local_inspection_service" / "server.py"

REQUIRED_RUNTIME_ADAPTERS = frozenset(
    {
        "accessory_candidate_row",
        "accessory_row",
        "accessory_rows",
        "ai_detection_task_row",
        "app_config_rows",
        "auth_session_rows",
        "auth_store_from_rows",
        "auth_user_rows",
        "auto_optimize_state_row",
        "config_from_rows",
        "data_analysis_record_row",
        "pipeline_state_from_rows",
        "pipeline_state_rows",
        "pipeline_task_row",
        "row_raw_json_list",
        "training_task_row",
    }
)

REQUIRED_TABLE_REFERENCES = frozenset(
    {
        "users",
        "auth_sessions",
        "app_config",
        "accessories",
        "accessory_candidates",
        "ai_detection_tasks",
        "auto_optimize_states",
        "data_analysis_records",
        "training_tasks",
        "pipeline_tasks",
        "pipeline_state",
    }
)

REQUIRED_REPOSITORY_METHODS = frozenset(
    {
        "fetch_all",
        "replace_tables",
        "upsert_row",
        "delete_by_primary_key",
        "count_rows",
    }
)
MIN_RUNTIME_REPOSITORY_ENTRY_CALLS = 40

REQUIRED_RUNTIME_ENTRY_HELPERS = frozenset(
    {
        "load_auth_store",
        "save_auth_store",
        "save_auth_user",
        "delete_auth_user",
        "load_config",
        "save_config",
        "save_app_config",
        "save_accessory_item",
        "delete_accessory_item",
        "load_data_analysis_records",
        "save_data_analysis_record",
        "delete_data_analysis_record",
        "save_auto_optimize_state",
        "list_auto_optimize_states",
        "save_accessory_candidate",
        "delete_accessory_candidate",
        "list_accessory_candidate_records",
        "load_training_task_records",
        "save_training_task",
        "load_training_task",
        "load_ai_detection_tasks",
        "save_ai_detection_tasks",
        "save_ai_detection_task",
        "load_pipeline_tasks",
        "save_pipeline_tasks",
        "load_pipeline_task",
        "save_pipeline_task",
        "delete_pipeline_task_row",
        "load_pipeline_state",
        "save_pipeline_state",
        "save_pipeline_state_keys",
    }
)


class SourceContract(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imported_names: set[str] = set()
        self.called_attributes: set[str] = set()
        self.string_literals: set[str] = set()
        self.function_names: set[str] = set()
        self.runtime_repository_entry_call_count = 0
        self.functions_with_runtime_repository_entry: set[str] = set()
        self._function_stack: list[str] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.module.endswith("runtime_records"):
            for alias in node.names:
                self.imported_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_names.add(node.name)
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_names.add(node.name)
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            self.called_attributes.add(node.func.attr)
        if isinstance(node.func, ast.Name) and node.func.id == "runtime_postgres_repository_or_none":
            self.runtime_repository_entry_call_count += 1
            if self._function_stack:
                self.functions_with_runtime_repository_entry.add(self._function_stack[-1])
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.string_literals.add(node.value)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SERVER))
    contract = SourceContract()
    contract.visit(tree)

    missing_adapters = sorted(REQUIRED_RUNTIME_ADAPTERS - contract.imported_names)
    require(not missing_adapters, "server.py missing runtime record adapters: " + ",".join(missing_adapters))

    missing_methods = sorted(REQUIRED_REPOSITORY_METHODS - contract.called_attributes)
    require(not missing_methods, "server.py missing repository method calls: " + ",".join(missing_methods))

    missing_tables = sorted(REQUIRED_TABLE_REFERENCES - contract.string_literals)
    require(not missing_tables, "server.py missing runtime table references: " + ",".join(missing_tables))

    require("runtime_repository_selection" in contract.function_names, "server.py missing runtime_repository_selection")
    require("runtime_store_probe_payload" in contract.function_names, "server.py missing runtime_store_probe_payload")
    require("runtime_postgres_repository_or_none" in contract.function_names, "server.py missing runtime_postgres_repository_or_none")
    require(
        contract.runtime_repository_entry_call_count >= MIN_RUNTIME_REPOSITORY_ENTRY_CALLS,
        "server.py has too few runtime_postgres_repository_or_none calls: "
        f"{contract.runtime_repository_entry_call_count} < {MIN_RUNTIME_REPOSITORY_ENTRY_CALLS}",
    )

    missing_entry_helpers = sorted(REQUIRED_RUNTIME_ENTRY_HELPERS - contract.functions_with_runtime_repository_entry)
    require(
        not missing_entry_helpers,
        "server.py runtime repository entry missing from helpers: " + ",".join(missing_entry_helpers),
    )

    print("postgres endpoint source contract smoke passed")


if __name__ == "__main__":
    main()
