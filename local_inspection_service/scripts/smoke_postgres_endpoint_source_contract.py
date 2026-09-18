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
ANALYSIS_REPOSITORY = ROOT / "local_inspection_service" / "analytics" / "analysis_repository.py"

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
    def __init__(self, injected_repository: bool = False, repository_expression: str = "self.dependencies.runtime_repository") -> None:
        self.injected_repository = injected_repository
        self.repository_expression = repository_expression
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
        direct = isinstance(node.func, ast.Name) and node.func.id == "runtime_postgres_repository_or_none"
        injected = self.injected_repository and ast.dump(node.func) == ast.dump(
            ast.parse(self.repository_expression, mode="eval").body
        )
        if direct or injected:
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

    # Verify the actual extracted repository and its explicit composition import;
    # do not retain dead table-name strings in server.py just to pass this gate.
    require(any(isinstance(node, ast.ImportFrom) and node.module == "analytics.analysis_repository"
                and any(alias.name == "AnalysisRepository" for alias in node.names)
                for node in ast.walk(tree)), "server.py missing AnalysisRepository composition import")
    analysis = SourceContract(injected_repository=True)
    analysis.visit(ast.parse(ANALYSIS_REPOSITORY.read_text(encoding="utf-8"), filename=str(ANALYSIS_REPOSITORY)))
    migrated_helpers = {"load_data_analysis_records", "save_data_analysis_records", "load_data_analysis_record",
                        "save_data_analysis_record", "delete_data_analysis_record"}
    require(migrated_helpers <= analysis.functions_with_runtime_repository_entry,
            "extracted analysis helpers must use the injected runtime repository factory")
    require("data_analysis_records" in analysis.string_literals, "analysis repository missing real table access")
    # The public compatibility export must never bypass owner authorization by
    # pointing directly at the identically named persistence method.
    require(any(isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "delete_data_analysis_record" for target in node.targets)
                and ast.dump(node.value) == ast.dump(ast.parse("_analysis_records.delete_data_analysis_record", mode="eval").body)
                for node in tree.body), "public analysis delete must bind the authorized service")
    service_path = ANALYSIS_REPOSITORY.with_name("analysis_service.py")
    service_tree = ast.parse(service_path.read_text(encoding="utf-8"))
    service_methods = {node.name: node for node in ast.walk(service_tree) if isinstance(node, ast.FunctionDef)}
    delete_method = service_methods["delete_data_analysis_record"]
    ordered_calls = sorted((node for node in ast.walk(delete_method) if isinstance(node, ast.Call)), key=lambda node: node.lineno)
    expected_calls = [ast.dump(ast.parse(value, mode="eval").body) for value in (
        "self.find_data_analysis_record", "self.repository.delete_data_analysis_record")]
    relevant_calls = [node for node in ordered_calls if ast.dump(node.func) in expected_calls]
    require([ast.dump(node.func) for node in relevant_calls] == expected_calls,
            "analysis delete must authorize through find before persistence")
    require(any(keyword.arg == "write" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
                for keyword in relevant_calls[0].keywords), "analysis delete requires write authorization")
    require(any(isinstance(node, ast.Call) and ast.dump(node.func) == ast.dump(
                ast.parse("self.access.require_access", mode="eval").body)
                for node in ast.walk(service_methods["find_data_analysis_record"])),
            "analysis find must enforce record access")
    api_tree = ast.parse(ANALYSIS_REPOSITORY.with_name("analysis_api.py").read_text(encoding="utf-8"))
    route = next(node for node in ast.walk(api_tree) if isinstance(node, ast.FunctionDef) and node.name == "delete_data_analysis_record_api")
    require(any(isinstance(node, ast.Call) and ast.dump(node.func) == ast.dump(
                ast.parse("queries.records.delete_data_analysis_record", mode="eval").body) for node in ast.walk(route)),
            "analysis HTTP delete must use the authorized service")
    for attribute in ("imported_names", "called_attributes", "string_literals", "function_names",
                      "functions_with_runtime_repository_entry"):
        getattr(contract, attribute).update(getattr(analysis, attribute))
    contract.runtime_repository_entry_call_count += analysis.runtime_repository_entry_call_count

    auth_path = ROOT / "local_inspection_service" / "auth" / "repository.py"
    require(any(isinstance(node, ast.ImportFrom) and node.module == "auth.repository"
                and any(alias.name == "AuthRepository" for alias in node.names)
                for node in ast.walk(tree)), "server.py missing AuthRepository composition import")
    auth = SourceContract(injected_repository=True)
    auth.visit(ast.parse(auth_path.read_text(encoding="utf-8"), filename=str(auth_path)))
    auth_helpers = {"load_auth_store", "save_auth_store", "save_auth_user", "delete_auth_user",
                    "save_auth_session", "delete_auth_session", "delete_expired_auth_sessions",
                    "delete_auth_sessions_for_user", "save_login_session", "save_auth_session_touch_or_prune"}
    require(auth_helpers <= auth.functions_with_runtime_repository_entry,
            "authentication persistence helpers must use the injected runtime repository")
    for name in auth_helpers:
        require(any(isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
                    and ast.dump(node.value) == ast.dump(ast.parse("_auth_repository." + name, mode="eval").body)
                    for node in tree.body), "authentication compatibility export is not bound to repository: " + name)
    require({"users", "auth_sessions"} <= auth.string_literals, "authentication repository missing actual table access")
    for attribute in ("imported_names", "called_attributes", "string_literals", "function_names",
                      "functions_with_runtime_repository_entry"):
        getattr(contract, attribute).update(getattr(auth, attribute))
    contract.runtime_repository_entry_call_count += auth.runtime_repository_entry_call_count

    accessory_path = ROOT / "local_inspection_service" / "accessories" / "repository.py"
    require(any(isinstance(node, ast.ImportFrom) and node.module == "accessories.repository"
                and any(alias.name == "AccessoryRepository" for alias in node.names)
                for node in ast.walk(tree)), "server.py missing AccessoryRepository composition import")
    accessory = SourceContract(injected_repository=True)
    accessory.visit(ast.parse(accessory_path.read_text(encoding="utf-8"), filename=str(accessory_path)))
    accessory_helpers = {"save_accessory_item", "delete_accessory_item"}
    require(accessory_helpers <= accessory.functions_with_runtime_repository_entry,
            "accessory persistence helpers must use the injected runtime repository")
    for name in accessory_helpers:
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        expected = ast.parse("_accessory_repository." + name +
                             ("(item, config)" if name == "save_accessory_item" else "(accessory_id, config)"), mode="eval").body
        require(len(function.body) == 1 and isinstance(function.body[0], ast.Return)
                and ast.dump(function.body[0].value) == ast.dump(expected),
                "accessory compatibility function is not bound to repository: " + name)
    require("accessories" in accessory.string_literals, "accessory repository missing actual table access")
    for attribute in ("imported_names", "called_attributes", "string_literals", "function_names",
                      "functions_with_runtime_repository_entry"):
        getattr(contract, attribute).update(getattr(accessory, attribute))
    contract.runtime_repository_entry_call_count += accessory.runtime_repository_entry_call_count

    candidate_path = accessory_path.with_name("candidate_repository.py")
    require(any(isinstance(node, ast.ImportFrom) and node.module == "accessories.candidate_repository"
                and any(alias.name == "CandidateRepository" for alias in node.names)
                for node in ast.walk(tree)), "server.py missing CandidateRepository composition import")
    candidates = SourceContract(injected_repository=True)
    candidates.visit(ast.parse(candidate_path.read_text(encoding="utf-8"), filename=str(candidate_path)))
    candidate_helpers = {"load_accessory_candidate", "save_accessory_candidate", "delete_accessory_candidate", "list_accessory_candidate_records"}
    require(candidate_helpers <= candidates.functions_with_runtime_repository_entry,
            "candidate helpers must use the injected runtime repository")
    for name, arguments in {"load_accessory_candidate": "candidate_id", "save_accessory_candidate": "path, candidate",
                            "delete_accessory_candidate": "candidate_id, path", "list_accessory_candidate_records": "reverse=reverse",
                            "accessory_candidate_record_path": "candidate, fallback_id", "write_accessory_candidate_file": "path, candidate"}.items():
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        expected = ast.parse("_candidate_repository." + name + "(" + arguments + ")", mode="eval").body
        require(len(function.body) == 1 and isinstance(function.body[0], ast.Return)
                and ast.dump(function.body[0].value) == ast.dump(expected), "candidate helper is not bound to repository: " + name)
    require("accessory_candidates" in candidates.string_literals, "candidate repository missing actual table access")
    for attribute in ("imported_names", "called_attributes", "string_literals", "function_names",
                      "functions_with_runtime_repository_entry"):
        getattr(contract, attribute).update(getattr(candidates, attribute))
    contract.runtime_repository_entry_call_count += candidates.runtime_repository_entry_call_count
    text_path = ROOT / "local_inspection_service" / "text_inspection" / "record_store.py"
    require(any(isinstance(node, ast.ImportFrom) and node.module == "local_inspection_service.text_inspection.record_store"
                and any(alias.name == "TextRecordStore" for alias in node.names)
                and any(alias.name == "record_row" and alias.asname == "_text_v2_row" for alias in node.names)
                for node in ast.walk(tree)), "server.py missing text record store and row composition imports")
    text_records = SourceContract(injected_repository=True)
    text_records.visit(ast.parse(text_path.read_text(encoding="utf-8"), filename=str(text_path)))
    require({"load", "save", "owned", "update_attempt"} <= text_records.functions_with_runtime_repository_entry,
            "text record methods must obtain their runtime repository lazily")
    for name, arguments in {"json_path": "kind", "load": "kind", "save": "kind, value, insert_only=insert_only",
                            "owned": "kind, record_id, owner_user_id", "update_attempt": "kind, value, expected_status"}.items():
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_text_v2_" + name)
        expected = ast.parse("_text_records." + name + "(" + arguments + ")", mode="eval").body
        require(len(function.body) == 1 and isinstance(function.body[0], ast.Return)
                and ast.dump(function.body[0].value) == ast.dump(expected), "text helper is not bound to record store: " + name)
    require({"text_inspection_records", "text_ocr_evidence"} <= text_records.string_literals,
            "text record store missing actual table mappings")
    for attribute in ("imported_names", "called_attributes", "string_literals", "function_names",
                      "functions_with_runtime_repository_entry"):
        getattr(contract, attribute).update(getattr(text_records, attribute))
    contract.runtime_repository_entry_call_count += text_records.runtime_repository_entry_call_count
    edits_path = text_path.with_name("standard_edits.py")
    edits = SourceContract(injected_repository=True, repository_expression="self.writes.repository")
    edits.visit(ast.parse(edits_path.read_text(encoding="utf-8"), filename=str(edits_path)))
    require(edits.runtime_repository_entry_call_count == 3, "standard edits must retain three actual lazy repository entries")
    require(edits.functions_with_runtime_repository_entry == {
        "add_text_inspection_standard_asset", "patch_text_inspection_asset", "confirm_text_inspection_standard"
    }, "each standard write workflow must obtain its own thread repository")
    require(any(isinstance(node, ast.ImportFrom) and node.module == "text_inspection.standard_edits"
                and any(alias.name == "StandardEdits" for alias in node.names)
                for node in tree.body), "server missing standard edit service composition")
    writes = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "StandardWrites"]
    require(len(writes) == 1, "expected one standard write-capability composition")
    repository = next(keyword.value for keyword in writes[0].keywords if keyword.arg == "repository")
    require(isinstance(repository, ast.Lambda) and ast.dump(repository.body) == ast.dump(
                ast.parse("runtime_postgres_repository_or_none()", mode="eval").body),
            "standard edit composition must supply the thread repository lazily")
    # Count actual workflow entries, not the forwarding lambda a second time.
    contract.runtime_repository_entry_call_count -= 1
    contract.runtime_repository_entry_call_count += edits.runtime_repository_entry_call_count
    incoming_path = text_path.with_name("incoming_store.py")
    incoming = SourceContract(injected_repository=True, repository_expression="self.repository")
    incoming.visit(ast.parse(incoming_path.read_text(encoding="utf-8"), filename=str(incoming_path)))
    incoming_arguments = {
        "load_incoming_text_references": "", "load_incoming_text_inspections": "",
        "load_incoming_text_reference": "reference_id", "load_incoming_text_inspection": "inspection_id",
        "save_incoming_text_reference": "reference, insert_only=insert_only",
        "save_incoming_text_inspection": "inspection, insert_only=insert_only", "append_incoming_text_audit": "event",
    }
    require(incoming.runtime_repository_entry_call_count == 7
            and incoming.functions_with_runtime_repository_entry == set(incoming_arguments),
            "incoming text store must retain its seven real lazy repository entries")
    for name, arguments in incoming_arguments.items():
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        expected = ast.parse("_incoming_text_store." + name + "(" + arguments + ")", mode="eval").body
        require(len(function.body) == 1 and isinstance(function.body[0], ast.Return)
                and ast.dump(function.body[0].value) == ast.dump(expected), "incoming store forward changed: " + name)
    require(any(isinstance(node, ast.ImportFrom) and node.module == "text_inspection.incoming_store"
                and any(alias.name == "IncomingTextStore" for alias in node.names)
                for node in tree.body), "server missing incoming store composition")
    compositions = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == "IncomingTextStore"]
    require(len(compositions) == 1, "expected one incoming text store composition")
    repository = next(keyword.value for keyword in compositions[0].keywords if keyword.arg == "repository")
    require(isinstance(repository, ast.Lambda) and ast.dump(repository.body) == ast.dump(
                ast.parse("runtime_postgres_repository_or_none()", mode="eval").body),
            "incoming store must obtain its thread repository lazily")
    contract.runtime_repository_entry_call_count += incoming.runtime_repository_entry_call_count - 1
    for attribute in ("imported_names", "called_attributes", "string_literals", "function_names",
                      "functions_with_runtime_repository_entry"):
        getattr(contract, attribute).update(getattr(incoming, attribute))

    for attribute in ("imported_names", "called_attributes", "string_literals", "function_names",
                      "functions_with_runtime_repository_entry"):
        getattr(contract, attribute).update(getattr(edits, attribute))

    # Legacy workflows retain five real repository entries after extraction.
    for filename, expected in {
        "incoming_catalog.py": {"update_incoming_text_reference_rules"},
        "incoming_reviews.py": {"duplicate", "review_incoming_text_inspection", "list_incoming_text_inspections"},
        "incoming_retention.py": {"purge"},
    }.items():
        path = text_path.with_name(filename)
        workflow = SourceContract(injected_repository=True, repository_expression="self.writes.repository")
        workflow.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        require(workflow.runtime_repository_entry_call_count == len(expected)
                and workflow.functions_with_runtime_repository_entry == expected,
                "legacy incoming workflow repository entries changed: " + filename)
        contract.runtime_repository_entry_call_count += workflow.runtime_repository_entry_call_count
        for attribute in ("imported_names", "called_attributes", "string_literals", "function_names",
                          "functions_with_runtime_repository_entry"):
            getattr(contract, attribute).update(getattr(workflow, attribute))
    compositions = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == "IncomingWrites"]
    require(len(compositions) == 1, "expected one shared incoming write-capability composition")
    repository = next(keyword.value for keyword in compositions[0].keywords if keyword.arg == "repository")
    require(isinstance(repository, ast.Lambda) and ast.dump(repository.body) == ast.dump(
                ast.parse("runtime_postgres_repository_or_none()", mode="eval").body),
            "incoming workflows must resolve their thread repository lazily")
    contract.runtime_repository_entry_call_count -= 1

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
