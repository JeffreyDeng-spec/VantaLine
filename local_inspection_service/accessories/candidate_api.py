"""Single candidate route registered in the original application position."""
from collections.abc import Callable
from typing import Any
from fastapi import FastAPI
from .candidate_queries import CandidateQueries


def register_candidate_api(app: FastAPI, queries: CandidateQueries) -> Callable[[str], dict[str, Any]]:
    @app.get("/api/accessories/candidates/{candidate_id}")
    def get_accessory_candidate(candidate_id: str) -> dict[str, Any]:
        return queries.get_accessory_candidate(candidate_id)

    return get_accessory_candidate
