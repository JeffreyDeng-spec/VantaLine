"""Root-only immutable-release observer. Output contains no configuration or media."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import time

from .configuration import private_bytes
from .configuration_contract import CONFIGURATION_LIMIT, CONFIGURATION_ENVIRONMENT, configuration_validate
from .label_identity import read_identity, RuntimeUnavailable
from .label_observation import read_observation, observe_progress
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository


@contextmanager
def application_database_identity():
    """Peer authentication uses the Web account; this single-process CLI restores root."""
    import pwd
    account = pwd.getpwnam("vantaline")
    uid, gid, groups = os.geteuid(), os.getegid(), os.getgroups()
    if uid != 0 or account.pw_uid == 0:
        raise RuntimeUnavailable("Runtime database identity unavailable")
    try:
        os.setgroups(os.getgrouplist(account.pw_name, account.pw_gid))
        os.setegid(account.pw_gid)
        os.seteuid(account.pw_uid)
        yield
    finally:
        # Regain the saved effective root identity before restoring groups.
        os.seteuid(uid)
        os.setegid(gid)
        os.setgroups(groups)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--release", required=True)
    args = parser.parse_args(argv)
    stage = "root"
    try:
        deadline = time.monotonic() + 30
        if os.geteuid() != 0:
            raise RuntimeUnavailable("Root observation required")
        root = Path(__file__).resolve().parents[2]
        stage = "configuration_read"
        config = json.loads(private_bytes(Path("/etc/vantaline/runtime/current/config.json"),
                           owner=0, maximum=CONFIGURATION_LIMIT, group_read=True))
        stage = "configuration_validate"
        revision = configuration_validate(config)
        stage = "identity"
        identity = read_identity(root, current=Path("/opt/vantaline/current"),
                                 configuration_revision=lambda: revision)
        if identity is None or identity.commit != args.commit or identity.release != args.release:
            raise RuntimeUnavailable("Runtime observation identity mismatch")
        # This short-lived process consumes captured libpq defaults, never Web globals.
        for key in CONFIGURATION_ENVIRONMENT:
            value = config["environment"][key]
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        stage = "database_driver"
        import psycopg
        stage = "database_identity"
        with application_database_identity():
            stage = "database_connect"
            connection = psycopg.connect(config["environment"]["DATABASE_URL"], connect_timeout=2,
                options="-c default_transaction_read_only=on -c default_transaction_isolation=repeatable\\ read -c statement_timeout=2000")
        with connection:
            stage = "database_progress"
            repository = PostgresRuntimeRepository(connection, "redacted")
            progress = observe_progress(lambda: read_observation(repository, identity),
                                      timeout=deadline - time.monotonic())
        stage = "final_configuration_read"
        final_config = json.loads(private_bytes(Path("/etc/vantaline/runtime/current/config.json"),
                                 owner=0, maximum=CONFIGURATION_LIMIT, group_read=True))
        stage = "final_identity"
        final_identity = read_identity(root, current=Path("/opt/vantaline/current"),
                                       configuration_revision=lambda: configuration_validate(final_config))
        if final_identity != identity or time.monotonic() >= deadline:
            raise RuntimeUnavailable("Runtime observation generation changed")
        result = progress.after
        print(json.dumps({"schema": 1, "git_commit": identity.commit, "release": identity.release,
            "worker_mode": identity.mode, "config_revision": identity.config_revision,
            "maintenance": result.maintenance, "paused": result.paused,
            "queued_runs": result.queued, "active_runs": result.active,
            "roles": [{"role": role, "instance": instance, "pid": pid, "sampled_at": sampled}
                      for role, instance, pid, sampled in result.roles],
            "samples_before": [{"role": role, "instance": instance, "pid": pid, "sampled_at": sampled}
                      for role, instance, pid, sampled in progress.before.roles], "periodic_progress": True}))
        return 0
    except Exception as error:
        # Emit only fixed classifications, never exception text or configuration.
        reason = {"28000": "database_authentication", "28P01": "database_authentication",
                  "3D000": "database_missing", "42501": "database_permission"}.get(
                      getattr(error, "sqlstate", None), "unavailable")
        # libpq connection failures may omit SQLSTATE. Match fixed tokens only;
        # the message itself must never reach stdout/stderr.
        if stage == "database_connect" and error.args and isinstance(error.args[0], str):
            for token, category in (("Peer authentication failed", "database_peer_authentication"),
                                    ("password authentication failed", "database_authentication"),
                                    ("no password supplied", "database_password_missing")):
                if token in error.args[0]:
                    reason = category
                    break
        print(f"Runtime database observation stage={stage} reason={reason}", file=sys.stderr)
        # Driver/configuration exceptions can contain passwords and private paths.
        print("Runtime database observation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
