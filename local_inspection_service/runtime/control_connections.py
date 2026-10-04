"""Dedicated control connections; normal requests and paid tasks keep their settings."""
import os
from collections.abc import Mapping

from .connections import ThreadRepositoryFactory
from .label_identity import RuntimeUnavailable
from ..storage.runtime_selector import build_runtime_repository


def control_connector(dsn: str):
    import psycopg
    # libpq connect_timeout applies per host. TCP liveness and SQL timeouts
    # improve failure detection, but are not a total Python-thread deadline.
    # The root client owns the bounded acknowledgement deadline.
    return psycopg.connect(dsn, connect_timeout=2, tcp_user_timeout=2000,
                           keepalives=1, keepalives_idle=1,
                           keepalives_interval=1, keepalives_count=2)


def create_control_factory(env: Mapping[str, str] | None = None) -> ThreadRepositoryFactory:
    source = os.environ if env is None else env
    selected = {name: source.get(name, "") for name in ("VANTALINE_DATA_STORE", "DATABASE_URL")}
    if selected["VANTALINE_DATA_STORE"].strip().lower() != "postgres" or not selected["DATABASE_URL"].strip():
        raise RuntimeUnavailable("Managed label control requires PostgreSQL")
    return ThreadRepositoryFactory(
        lambda: build_runtime_repository(env=selected, postgres_connector=control_connector),
        lambda: 0,
    )
