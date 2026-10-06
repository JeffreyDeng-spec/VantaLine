"""Compose the two rule routes with an explicit application-owned service."""
from fastapi import FastAPI
from .rule_request_ports import RulePolicy, RuleStore, RuleAccess
from .rule_requests import DetectionRules


RULE_PATHS = ("/api/config/rules", "/api/config/task-rules/{task_id}")


def compose_detection_rule_api(app: FastAPI, *, policy: RulePolicy,
                               store: RuleStore, access: RuleAccess) -> DetectionRules:
    # Fail before adding either route if this domain was already installed.
    for route in app.routes:
        if getattr(route, "path", None) in RULE_PATHS and "POST" in (getattr(route, "methods", None) or ()):
            raise ValueError("Detection rule routes are already registered")
    service = DetectionRules(policy=policy, store=store, access=access)
    app.post(RULE_PATHS[0])(service.update_rules)
    app.post(RULE_PATHS[1])(service.update_task_rules)
    return service
