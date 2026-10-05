"""Candidate-owned artifact cleanup and existing reference image selection."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .candidate_artifact_ports import CandidateArtifactFiles, CandidateArtifactRecords

@dataclass(frozen=True)
class CandidateArtifacts:
    files: CandidateArtifactFiles
    records: CandidateArtifactRecords

    def cleanup_accessory_candidate_artifacts(self, candidate: dict[str, Any]) -> list[str]:
        """Remove only directories that are unambiguously owned by a pending candidate."""
        raw_candidate_id = str(candidate.get("id") or candidate.get("candidate_id") or "").strip()
        if not raw_candidate_id:
            return []
        if str(candidate.get("confirmed_accessory_id") or "").strip() or str(candidate.get("status") or "").lower() == "confirmed":
            return []
        candidate_id = self.records.safe_record_id()(raw_candidate_id)

        upload_root = (self.files.UPLOAD_DIR() / "accessory_candidates").resolve()
        output_root = self.files.output_write_dir()("accessory_candidates").resolve()
        owned_directories: set[Path] = set()
        referenced_upload_files: set[Path] = set()

        for key in ("source_files", "original_source_files", "video_reference_frames"):
            values = candidate.get(key)
            if not isinstance(values, list):
                continue
            for raw_value in values:
                raw_path = raw_value.get("path") if isinstance(raw_value, dict) else raw_value
                if not isinstance(raw_path, str) or not raw_path.strip():
                    continue
                source_path = Path(raw_path).resolve()
                try:
                    relative = source_path.relative_to(upload_root)
                except ValueError:
                    continue
                referenced_upload_files.add(source_path)
                if not relative.parts:
                    continue
                owner_dir = upload_root / relative.parts[0]
                if owner_dir.name == candidate_id or owner_dir.name.startswith("src_"):
                    owned_directories.add(owner_dir)

        candidate_upload_dir = upload_root / candidate_id
        if self.files._business_files().exists(candidate_upload_dir):
            owned_directories.add(candidate_upload_dir)
        candidate_output_dir = output_root / candidate_id
        if self.files._business_files().exists(candidate_output_dir):
            owned_directories.add(candidate_output_dir)

        def referenced_paths(record: dict[str, Any]) -> set[Path]:
            paths: set[Path] = set()

            def collect(value: Any) -> None:
                if isinstance(value, str):
                    path = Path(value)
                    if path.is_absolute():
                        paths.add(path.resolve())
                elif isinstance(value, list):
                    for item in value:
                        collect(item)
                elif isinstance(value, dict):
                    for item in value.values():
                        collect(item)

            for key in (
                "source_files",
                "original_source_files",
                "video_reference_frames",
                "thumbnails",
                "normalized_assets",
                "ai_profile_reference_files",
                "codex_image_jobs",
                "codex_image_job",
            ):
                collect(record.get(key))
            return paths

        protected_records = [item for item in self.records.load_config()().get("accessories", []) if isinstance(item, dict)]
        for _, other_candidate in self.records.list_accessory_candidate_records()(reverse=False):
            other_id = str(other_candidate.get("id") or other_candidate.get("candidate_id") or "").strip()
            if other_id and other_id != raw_candidate_id:
                protected_records.append(other_candidate)
        protected_paths = set().union(*(referenced_paths(record) for record in protected_records)) if protected_records else set()

        for directory in owned_directories:
            resolved_directory = directory.resolve()
            for protected_path in protected_paths:
                try:
                    protected_path.relative_to(resolved_directory)
                except ValueError:
                    continue
                raise OSError(f"Refusing to delete candidate artifacts still referenced by another record: {resolved_directory}")

        deleted: list[str] = []
        for directory in sorted(owned_directories, key=str):
            resolved = directory.resolve()
            allowed_parent = upload_root if resolved.parent == upload_root else output_root
            if resolved.parent != allowed_parent:
                raise OSError(f"Refusing to delete non-candidate artifact directory: {resolved}")
            if allowed_parent == upload_root and not (resolved.name == candidate_id or resolved.name.startswith("src_")):
                raise OSError(f"Refusing to delete ambiguous upload directory: {resolved}")
            if allowed_parent == upload_root and resolved.name.startswith("src_"):
                contained_files = {path.resolve() for path in self.files._business_files().glob(resolved, "*", recursive=True) if self.files._business_files().is_file(path)}
                if not contained_files.issubset(referenced_upload_files):
                    raise OSError(f"Refusing to delete upload directory containing unreferenced files: {resolved}")
            if allowed_parent == output_root and resolved.name != candidate_id:
                raise OSError(f"Refusing to delete ambiguous output directory: {resolved}")
            if self.files._business_files().exists(resolved):
                self.files._business_files().rmtree(resolved)
                deleted.append(str(resolved))
        return deleted


    def existing_source_image_paths(self, item: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []
        seen: set[str] = set()
        for path_str in item.get("source_files", []) or []:
            path = Path(str(path_str))
            key = str(path)
            if key in seen:
                continue
            if self.files._business_files().exists(path) and path.suffix.lower() in self.files.IMAGE_REFERENCE_SUFFIXES():
                paths.append(path)
                seen.add(key)
        return paths
