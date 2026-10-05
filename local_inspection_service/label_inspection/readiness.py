"""Check list-reader prerequisites on the Web's actual database selection."""
from .dependencies import RepositoryLifecycle
from ..runtime.label_identity import RuntimeUnavailable


def verify_summary_reads(repositories: RepositoryLifecycle, *, required: bool) -> None:
    """No row scan or grants; SQL limits do not bound network connection time."""
    try:
        try:
            repository = repositories.repository()
            if repository is None:
                if required:
                    raise RuntimeUnavailable("Label list database is required")
                return  # Existing unmanaged JSON development mode has no reader.
            connection = repository.connection
            if connection.autocommit or connection.info.transaction_status != 0:
                raise RuntimeUnavailable("Label list preflight requires an idle connection")
            source = repository._qualified_table("label_inspection_objects")
            proof = repository._qualified_table("label_run_projection")
            # Always roll back this read-only transaction; never commit a caller's work.
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute("SET LOCAL lock_timeout='1000ms'")
                    cursor.execute("SET LOCAL statement_timeout='1500ms'")
                    cursor.execute(
                        "SELECT source.id,source.owner_user_id,source.task_id,source.kind,"
                        "source.created_at,source.raw_json,proof.id,proof.projection_version,proof.raw_json "
                        f"FROM {source} source LEFT JOIN {proof} proof ON proof.id=source.id LIMIT 0"
                    )
            finally:
                connection.rollback()
        finally:
            repositories.clear()
    except Exception:
        # Neither connection errors nor PostgreSQL identifiers/DSNs enter logs.
        raise RuntimeUnavailable("Label list database preflight failed") from None
