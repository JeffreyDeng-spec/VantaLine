"""Publish optional legacy list proofs using an explicit account selection."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.runtime_selector import build_runtime_repository
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.legacy_list_projection import LegacyListProjection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    args = parser.parse_args()
    try:
        selection = build_runtime_repository()
    except Exception as error:
        raise SystemExit("Legacy projection initialization failed: " + type(error).__name__) from None
    if not isinstance(selection.repository, PostgresRuntimeRepository):
        parser.error('Explicit PostgreSQL runtime is required')
    repository = selection.repository
    try:
        try:
            accepted = LegacyListProjection(repository).publish(args.owner)
        except Exception as error:
            raise SystemExit('Legacy projection publication failed: ' + type(error).__name__) from None
        print('Legacy projection published' if accepted else 'Original reader retained: cohort not proven or source changed')
    finally:
        repository.connection.close()


if __name__ == '__main__':
    main()
