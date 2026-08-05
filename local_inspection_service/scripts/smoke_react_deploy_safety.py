#!/usr/bin/env python3
"""Static safety contract for the React deployment helper."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile


SCRIPT = Path(__file__).with_name("deploy_react_preview.sh")
TRANSACTION = Path(__file__).with_name("react_release_transaction.sh")


def write_release(path: Path, marker: str) -> None:
    path.mkdir(parents=True)
    (path / "marker.txt").write_text(marker, encoding="utf-8")


def transaction_env(fail_at: str = "") -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "VANTALINE_DEPLOY_TEST_MODE": "1",
            "VANTALINE_DEPLOY_SYSTEMCTL": "true",
            "VANTALINE_DEPLOY_FAIL_AT": fail_at,
        }
    )
    return env


def assert_marker(path: Path, expected: str, label: str) -> None:
    actual = (path / "marker.txt").read_text(encoding="utf-8")
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def verify_failure_injection() -> None:
    with tempfile.TemporaryDirectory(prefix="vantaline_release_transaction_", dir="/tmp") as tmp_raw:
        root = Path(tmp_raw)
        lock_dir = root / "production-release.lock"
        winner_helper = root / "transaction-owner-one.sh"
        loser_helper = root / "transaction-owner-two.sh"
        shutil.copy2(TRANSACTION, winner_helper)
        shutil.copy2(TRANSACTION, loser_helper)
        subprocess.run(
            ["bash", str(winner_helper), "acquire-lock", str(lock_dir), "owner-one"],
            env=transaction_env(),
            check=True,
        )
        contender = subprocess.run(
            ["bash", str(loser_helper), "acquire-lock", str(lock_dir), "owner-two"],
            env=transaction_env(),
            check=False,
        )
        if contender.returncode == 0:
            raise AssertionError("concurrent release lock acquisition unexpectedly succeeded")
        loser_helper.unlink()
        if not winner_helper.is_file():
            raise AssertionError("losing wrapper cleanup removed the lock owner's unique helper")
        wrong_release = subprocess.run(
            ["bash", str(winner_helper), "release-lock", str(lock_dir), "owner-two"],
            env=transaction_env(),
            check=False,
        )
        if wrong_release.returncode == 0 or not lock_dir.exists():
            raise AssertionError("non-owner released the production release lock")
        subprocess.run(
            ["bash", str(winner_helper), "release-lock", str(lock_dir), "owner-one"],
            env=transaction_env(),
            check=True,
        )

        stale_case = root / "preview-stale-failed"
        stale_live = stale_case / "live"
        stale_staging = stale_case / "staging"
        stale_previous = stale_case / "previous"
        write_release(stale_live, "old-preview")
        write_release(stale_staging, "new-preview")
        write_release(Path(f"{stale_previous}.failed"), "unresolved-release")
        stale = subprocess.run(
            ["bash", str(TRANSACTION), "activate-preview", str(stale_live), str(stale_staging), str(stale_previous)],
            env=transaction_env(),
            check=False,
        )
        if stale.returncode == 0:
            raise AssertionError("transaction ignored an unresolved .failed release")
        assert_marker(stale_live, "old-preview", "stale failed-state rejection")

        for fail_at in ("before-old-move", "after-new-move"):
            case = root / f"preview-{fail_at}"
            preview_live = case / "live"
            preview_staging = case / "staging"
            preview_previous = case / "previous"
            write_release(preview_live, "old-preview")
            write_release(preview_staging, "new-preview")
            failed = subprocess.run(
                ["bash", str(TRANSACTION), "activate-preview", str(preview_live), str(preview_staging), str(preview_previous)],
                env=transaction_env(fail_at),
                check=False,
            )
            if failed.returncode == 0:
                raise AssertionError(f"preview {fail_at} injection unexpectedly succeeded")
            assert_marker(preview_live, "old-preview", f"preview rollback at {fail_at}")

        case = root / "preview-old-move-command-failure"
        preview_live = case / "live"
        preview_staging = case / "staging"
        preview_previous = case / "previous"
        write_release(preview_live, "old-preview")
        write_release(preview_staging, "new-preview")
        case.chmod(0o500)
        try:
            failed = subprocess.run(
                ["bash", str(TRANSACTION), "activate-preview", str(preview_live), str(preview_staging), str(preview_previous)],
                env=transaction_env(),
                check=False,
            )
        finally:
            case.chmod(0o700)
        if failed.returncode == 0:
            raise AssertionError("old-release mv command failure unexpectedly succeeded")
        assert_marker(preview_live, "old-preview", "old-release mv command failure preserved live")

        for fail_at in ("before-old-move", "before-restart"):
            case = root / f"production-{fail_at}"
            production_live = case / "live"
            production_staging = case / "staging"
            production_previous = case / "previous"
            dropin = case / "systemd" / "30-react-production.conf"
            dropin_backup = case / "backup" / "30-react-production.conf"
            write_release(production_live, "old-production")
            write_release(production_staging, "new-production")
            dropin.parent.mkdir(parents=True)
            dropin.write_text("old-dropin", encoding="utf-8")
            failed = subprocess.run(
                [
                    "bash",
                    str(TRANSACTION),
                    "activate-production",
                    str(production_live),
                    str(production_staging),
                    str(production_previous),
                    str(dropin),
                    str(dropin_backup),
                    "vantaline",
                    "CONFIRM_PRODUCTION_RELEASE_TRANSACTION",
                    "ABSENT",
                ],
                env=transaction_env(fail_at),
                check=False,
            )
            if failed.returncode == 0:
                raise AssertionError(f"production {fail_at} injection unexpectedly succeeded")
            assert_marker(production_live, "old-production", f"production rollback at {fail_at}")
            if dropin.read_text(encoding="utf-8") != "old-dropin":
                raise AssertionError(f"production {fail_at} rollback did not restore the old drop-in")

        case = root / "production-success"
        production_live = case / "live"
        production_staging = case / "staging"
        production_previous = case / "previous"
        dropin = case / "systemd" / "30-react-production.conf"
        dropin_backup = case / "backup" / "30-react-production.conf"
        target_dropin = case / "selected-backup" / "30-react-production.conf"
        write_release(production_live, "old-production")
        write_release(production_staging, "restored-production")
        dropin.parent.mkdir(parents=True)
        dropin.write_text("current-dropin", encoding="utf-8")
        target_dropin.parent.mkdir(parents=True)
        target_dropin.write_text("selected-dropin", encoding="utf-8")
        subprocess.run(
            [
                "bash",
                str(TRANSACTION),
                "activate-production",
                str(production_live),
                str(production_staging),
                str(production_previous),
                str(dropin),
                str(dropin_backup),
                "vantaline",
                "CONFIRM_PRODUCTION_RELEASE_TRANSACTION",
                str(target_dropin),
            ],
            env=transaction_env(),
            check=True,
        )
        assert_marker(production_live, "restored-production", "transactional production restore")
        if dropin.read_text(encoding="utf-8") != "selected-dropin":
            raise AssertionError("transactional restore did not install the selected backup drop-in")
        subprocess.run(
            [
                "bash",
                str(TRANSACTION),
                "rollback-production",
                str(production_live),
                str(production_previous),
                str(dropin),
                str(dropin_backup),
                "vantaline",
            ],
            env=transaction_env(),
            check=True,
        )
        assert_marker(production_live, "old-production", "production health-check rollback")
        if dropin.read_text(encoding="utf-8") != "current-dropin":
            raise AssertionError("health-check rollback did not restore the pre-restore drop-in")


def main() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    subprocess.run(["bash", "-n", str(TRANSACTION)], check=True)
    source = SCRIPT.read_text(encoding="utf-8")
    required = (
        "verify_remote_http",
        ".dist-production.staging-${release_id}",
        ".dist-production.previous-${release_id}",
        'if ! verify_remote_http "/" "/static/assets/"',
        "failed health checks and was rolled back",
        "react_release_transaction.sh",
        "COMPLETED",
        'target_dropin="ABSENT"',
        "acquire-lock",
        "release-lock",
        'release_id="${ts}-$(new_release_nonce)"',
        'react-release-transaction-${release_id}',
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"deploy helper is missing safety contracts: {missing}")
    cutover = source.split("cutover_production() {", 1)[-1].split("rollback_production() {", 1)[0]
    if cutover.index("acquire_release_lock") > cutover.index("build_production_cutover"):
        raise AssertionError("production lock must be acquired before the shared frontend build starts")
    verify_failure_injection()
    case_block = source.split('case "${mode}" in', 1)[-1]
    if "preview)" in case_block or "rollback-preview)" in case_block:
        raise AssertionError("retired /react-preview deployment modes are still callable")
    print("PASS: React deploy helper rejects concurrent/stale transactions and survives old-move/restart/health failures")


if __name__ == "__main__":
    main()
