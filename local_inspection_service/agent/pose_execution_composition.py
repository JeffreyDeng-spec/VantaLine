"""Compose photo highlight, pose rendering and sample preparation with explicit owners."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
import numpy as np
from ..storage.artifacts.files import BusinessFiles
from ..storage.artifacts.images import ImageFiles
from .state_composition import AgentStateWorkflows
from .planning_composition import PosePlanningWorkflows
from .pose_execution_ports import PoseImageProvider
Record = dict[str, Any]
from .pose_render_ports import PoseMetadataSerializer, PoseRenderArtifacts, PoseRenderPaths, PoseRenderPresentation, PoseRenderReferences
from .photo_highlight_ports import PhotoObjectSelection, PhotoSourceMedia, PhotoSpriteLimits, PhotoSpriteReadiness, PhotoWorkflowModels, PhotoWorkflowObjects, PhotoWorkflowState, PoseImageProvider
from .photo_highlight_image_ports import PhotoHighlightImagePolicy, PhotoMaskGeometry
from .photo_highlight_builder_ports import PhotoBuildArtifacts, PhotoBuildMasks, PhotoBuildModelPolicy, PhotoBuildPolicy, PhotoBuildPublication, PhotoBuildRuntime, PhotoMaskBounds, PoseSpriteMetadata
from .pose_execution_ports import PoseCallContent, PoseCallPresentation, PoseCallRegistry, PoseImageProvider, PoseSampleSteps, PoseWorkflowDiagnostics, PoseWorkflowModels, PoseWorkflowState

from .pose_render_content import PoseRenderContent
from .pose_artifact_store import PoseArtifactStore

@dataclass(frozen=True)
class ArtifactsPoseRenderArtifactsInputs:
    digest: Callable[[], Callable[[Path], str | None]]
    public_url: Callable[[], Callable[[Path], str]]
    bounded: Callable[[], Callable[[Any, int], str]]
    dumps: Callable[[], PoseMetadataSerializer]
from .photo_highlight_sources import PhotoHighlightSources
from .photo_highlight_selection import PhotoHighlightSelection
from .photo_highlight_workflow import PhotoHighlightWorkflow

@dataclass(frozen=True)
class PhotosPhotoWorkflowObjectsInputs:
    identifier: Callable[[], Callable[[Record], str]]
    signature: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class PhotosPhotoWorkflowStateInputs:
    tool: Callable[[], str]

@dataclass(frozen=True)
class PhotosPhotoWorkflowModelsInputs:
    settings: Callable[[], Callable[[], Record]]
    provider: Callable[[], Callable[[Record], PoseImageProvider]]
from .photo_highlight_image_input import PhotoHighlightImageInput
from .photo_highlight_comparison import PhotoHighlightComparison
from .photo_highlight_builder import PhotoHighlightSpriteBuilder

@dataclass(frozen=True)
class BuilderPhotoBuildPolicyInputs:
    material: Callable[[], Callable[[Record], str]]
    alpha: Callable[[], Callable[[Record], str]]
    complete: Callable[[], Callable[[Record, list[Record]], bool]]
    minimum: Callable[[], int]

@dataclass(frozen=True)
class BuilderPhotoBuildMasksInputs:
    decode: Callable[[], Callable[[np.ndarray], tuple[np.ndarray, Record]]]
    bounds: Callable[[], PhotoMaskBounds]
    roi: Callable[[], Callable[[np.ndarray, np.ndarray], tuple[np.ndarray | None, Record]]]
from .pose_call_registration import PoseCallRegistration

@dataclass(frozen=True)
class RegistrationPoseWorkflowModelsInputs:
    settings: Callable[[], Callable[[], Record]]
    provider: Callable[[], Callable[[Record], PoseImageProvider]]
    error: Callable[[], type[Exception]]

@dataclass(frozen=True)
class RegistrationPoseCallRegistryInputs:
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    cached: Callable[[], Callable[[Record], bool]]
    tool: Callable[[], str]
from .pose_call_execution import PoseCallExecution

@dataclass(frozen=True)
class ExecutionPoseWorkflowModelsInputs:
    settings: Callable[[], Callable[[], Record]]
    provider: Callable[[], Callable[[Record], PoseImageProvider]]
    error: Callable[[], type[Exception]]

@dataclass(frozen=True)
class ExecutionPoseCallRegistryInputs:
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    cached: Callable[[], Callable[[Record], bool]]
    tool: Callable[[], str]

@dataclass(frozen=True)
class ExecutionPoseCallContentInputs:
    chroma: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class ExecutionPoseCallPresentationInputs:
    bounded: Callable[[], Callable[[Any, int], str]]
from .pose_sample_preparation import PoseSamplePreparation

@dataclass(frozen=True)
class SamplesPoseWorkflowModelsInputs:
    settings: Callable[[], Callable[[], Record]]
    provider: Callable[[], Callable[[Record], PoseImageProvider]]
    error: Callable[[], type[Exception]]

@dataclass(frozen=True)
class SamplesPoseSampleStepsInputs:
    background: Callable[[], Callable[[Record, Record], str | None]]
    materialize: Callable[[], Callable[[Record, Record], bool]]
    missing: Callable[[], Callable[[Record, Record, Record], list[str]]]
    save: Callable[[], Callable[[Record], None]]

class PoseExecutionWorkflows:
    """Construct inert owners in dependency order; selection is below task workflow."""
    def __init__(self, *, state: AgentStateWorkflows, planning: PosePlanningWorkflows,
                 files: BusinessFiles, images: ImageFiles,
                 render_references: PoseRenderReferences,
                 render_presentation: PoseRenderPresentation,
                 artifacts_paths: PoseRenderPaths,
                 artifacts_artifacts: ArtifactsPoseRenderArtifactsInputs,
                 artifacts_presentation: PoseRenderPresentation,
                 sources_media: PhotoSourceMedia,
                 sources_limits: PhotoSpriteLimits,
                 sources_sprites: PhotoSpriteReadiness,
                 selection_selection: PhotoObjectSelection,
                 photos_objects: PhotosPhotoWorkflowObjectsInputs,
                 photos_limits: PhotoSpriteLimits,
                 photos_state: PhotosPhotoWorkflowStateInputs,
                 photos_models: PhotosPhotoWorkflowModelsInputs,
                 image_input_policy: PhotoHighlightImagePolicy,
                 comparison_geometry: PhotoMaskGeometry,
                 builder_policy: BuilderPhotoBuildPolicyInputs,
                 builder_runtime: PhotoBuildRuntime,
                 builder_masks: BuilderPhotoBuildMasksInputs,
                 builder_model: PhotoBuildModelPolicy,
                 builder_publication: PhotoBuildPublication,
                 builder_artifacts: PhotoBuildArtifacts,
                 builder_metadata: PoseSpriteMetadata,
                 registration_models: RegistrationPoseWorkflowModelsInputs,
                 registration_registry: RegistrationPoseCallRegistryInputs,
                 execution_models: ExecutionPoseWorkflowModelsInputs,
                 execution_registry: ExecutionPoseCallRegistryInputs,
                 execution_content: ExecutionPoseCallContentInputs,
                 execution_presentation: ExecutionPoseCallPresentationInputs,
                 samples_models: SamplesPoseWorkflowModelsInputs,
                 samples_steps: SamplesPoseSampleStepsInputs,
                 samples_diagnostics: PoseWorkflowDiagnostics):
        self.state = state
        self.planning = planning
        self.images = images
        self.render = PoseRenderContent(
            PoseRenderReferences(
                contexts=render_references.contexts,
                resolve=render_references.resolve,
                mime=render_references.mime,
                encode=render_references.encode,
                public_url=render_references.public_url,
                digest=render_references.digest,
            ),
            PoseRenderPresentation(
                screen=render_presentation.screen,
            ),
            files=files,
        )
        self.artifacts = PoseArtifactStore(
            PoseRenderPaths(
                owner_root=artifacts_paths.owner_root,
                sanitize=artifacts_paths.sanitize,
            ),
            PoseRenderArtifacts(
                output=lambda: self.agent_mcp_pose_output_path,
                digest=artifacts_artifacts.digest,
                public_url=artifacts_artifacts.public_url,
                bounded=artifacts_artifacts.bounded,
                now=lambda: self.state.agent_mcp_now,
                dumps=artifacts_artifacts.dumps,
            ),
            PoseRenderPresentation(
                screen=artifacts_presentation.screen,
            ),
            files=files,
        )
        self.sources = PhotoHighlightSources(
            PhotoSourceMedia(
                resolve=sources_media.resolve,
                suffixes=sources_media.suffixes,
            ),
            PhotoSpriteLimits(
                minimum=sources_limits.minimum,
                version=sources_limits.version,
            ),
            PhotoSpriteReadiness(
                assets=sources_sprites.assets,
                complete=sources_sprites.complete,
            ),
            files=files,
        )
        self.selection = PhotoHighlightSelection(
            PhotoObjectSelection(
                normalize=selection_selection.normalize,
                training=selection_selection.training,
                lookup=selection_selection.lookup,
                canonical=selection_selection.canonical,
                material=selection_selection.material,
            ),
        )
        self.photos = PhotoHighlightWorkflow(
            PhotoWorkflowObjects(
                items=lambda: self.pipeline_photo_highlight_object_items,
                identifier=photos_objects.identifier,
                sources=lambda: self.object_photo_highlight_source_paths,
                signature=photos_objects.signature,
            ),
            PhotoSpriteLimits(
                minimum=photos_limits.minimum,
                version=photos_limits.version,
            ),
            PhotoWorkflowState(
                now=lambda: self.state.agent_mcp_now,
                tool=photos_state.tool,
                stage=lambda: self.state.set_agent_mcp_stage,
                pause=lambda: self.state.pause_agent_mcp_task,
                current=lambda: self.state.agent_mcp_orchestration,
                photo_flow=lambda: self.pipeline_uses_photo_highlight_sprite_flow,
                skip_legacy=lambda: self.mark_legacy_pose_flow_skipped_for_photo_highlight,
                build_plan=lambda: self.planning.build_agent_mcp_pose_plan,
            ),
            PhotoWorkflowModels(
                configuration=lambda: self.state.agent_mcp_gemini_image_config,
                settings=photos_models.settings,
                provider=photos_models.provider,
                build_sprites=lambda: self.build_clean_sprites_from_photo_highlight_masks,
            ),
        )
        self.image_input = PhotoHighlightImageInput(
            PhotoHighlightImagePolicy(
                identifier=image_input_policy.identifier,
                max_side=image_input_policy.max_side,
            ),
        )
        self.comparison = PhotoHighlightComparison(
            PhotoMaskGeometry(
                alpha=comparison_geometry.alpha,
                iou=comparison_geometry.iou,
            ),
        )
        self.builder = PhotoHighlightSpriteBuilder(
            PhotoBuildPolicy(
                material=builder_policy.material,
                sources=lambda: self.object_photo_highlight_source_paths,
                ready=lambda: self.photo_highlight_clean_sprites_ready,
                alpha=builder_policy.alpha,
                complete=builder_policy.complete,
                minimum=builder_policy.minimum,
            ),
            PhotoBuildRuntime(
                identifier=builder_runtime.identifier,
                root=builder_runtime.root,
                output=builder_runtime.output,
                safe_id=builder_runtime.safe_id,
                now=builder_runtime.now,
                bounded=builder_runtime.bounded,
            ),
            PhotoBuildMasks(
                prompt=lambda: self.photo_highlight_mask_prompt,
                input=lambda: self.photo_highlight_input_data_url,
                decode=builder_masks.decode,
                bounds=builder_masks.bounds,
                roi=builder_masks.roi,
                compare=lambda: self.photo_highlight_auto_compare,
            ),
            PhotoBuildModelPolicy(
                attempts=builder_model.attempts,
                error=builder_model.error,
                pose_version=builder_model.pose_version,
                photo_version=builder_model.photo_version,
            ),
            PhotoBuildPublication(
                sanitize=builder_publication.sanitize,
                item=builder_publication.item,
                publish=builder_publication.publish,
            ),
            PhotoBuildArtifacts(
                write=builder_artifacts.write,
                public_url=builder_artifacts.public_url,
            ),
            PoseSpriteMetadata(
                footprint=builder_metadata.footprint,
                normalize=builder_metadata.normalize,
                scale=builder_metadata.scale,
                laying=builder_metadata.laying,
            ),
            files=files,
            images=images,
        )
        self.registration = PoseCallRegistration(
            PoseWorkflowState(
                plan=lambda: self.ensure_agent_mcp_pose_plan,
                photo_flow=lambda: self.pipeline_uses_photo_highlight_sprite_flow,
                stage=lambda: self.state.set_agent_mcp_stage,
                skip_legacy=lambda: self.mark_legacy_pose_flow_skipped_for_photo_highlight,
                pause=lambda: self.state.pause_agent_mcp_task,
                current=lambda: self.state.agent_mcp_orchestration,
            ),
            PoseWorkflowModels(
                configuration=lambda: self.state.agent_mcp_gemini_image_config,
                error=registration_models.error,
                provider=registration_models.provider,
                settings=registration_models.settings,
            ),
            PoseCallRegistry(
                tool=registration_registry.tool,
                lookup=registration_registry.lookup,
                cached=registration_registry.cached,
                identifier=lambda: self.state.agent_mcp_tool_call_id,
                upsert=lambda: self.state.upsert_agent_mcp_tool_call,
            ),
        )
        self.execution = PoseCallExecution(
            PoseWorkflowState(
                plan=lambda: self.ensure_agent_mcp_pose_plan,
                photo_flow=lambda: self.pipeline_uses_photo_highlight_sprite_flow,
                stage=lambda: self.state.set_agent_mcp_stage,
                skip_legacy=lambda: self.mark_legacy_pose_flow_skipped_for_photo_highlight,
                pause=lambda: self.state.pause_agent_mcp_task,
                current=lambda: self.state.agent_mcp_orchestration,
            ),
            PoseWorkflowModels(
                configuration=lambda: self.state.agent_mcp_gemini_image_config,
                error=execution_models.error,
                provider=execution_models.provider,
                settings=execution_models.settings,
            ),
            PoseCallRegistry(
                tool=execution_registry.tool,
                lookup=execution_registry.lookup,
                cached=execution_registry.cached,
                identifier=lambda: self.state.agent_mcp_tool_call_id,
                upsert=lambda: self.state.upsert_agent_mcp_tool_call,
            ),
            PoseCallContent(
                prompt=lambda: self.agent_mcp_pose_prompt,
                references=lambda: self.agent_mcp_pose_reference_content,
                chroma=execution_content.chroma,
                artifact=lambda: self.write_agent_mcp_pose_artifact,
            ),
            PoseCallPresentation(
                now=lambda: self.state.agent_mcp_now,
                bounded=execution_presentation.bounded,
            ),
        )
        self.samples = PoseSamplePreparation(
            PoseWorkflowState(
                plan=lambda: self.ensure_agent_mcp_pose_plan,
                photo_flow=lambda: self.pipeline_uses_photo_highlight_sprite_flow,
                stage=lambda: self.state.set_agent_mcp_stage,
                skip_legacy=lambda: self.mark_legacy_pose_flow_skipped_for_photo_highlight,
                pause=lambda: self.state.pause_agent_mcp_task,
                current=lambda: self.state.agent_mcp_orchestration,
            ),
            PoseWorkflowModels(
                configuration=lambda: self.state.agent_mcp_gemini_image_config,
                error=samples_models.error,
                provider=samples_models.provider,
                settings=samples_models.settings,
            ),
            PoseSampleSteps(
                missing=samples_steps.missing,
                register=lambda: self.ensure_agent_mcp_pose_tool_calls,
                background=samples_steps.background,
                execute=lambda: self.execute_agent_mcp_pose_tool_calls,
                materialize=samples_steps.materialize,
                photos=lambda: self.prepare_photo_highlight_sprites_for_task,
                save=samples_steps.save,
            ),
            PoseWorkflowDiagnostics(
                stderr=samples_diagnostics.stderr,
                print_exception=samples_diagnostics.print_exception,
            ),
        )

    def agent_mcp_pose_reference_content(self, item: dict[str, Any], *, max_images: int=3) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return self.render.agent_mcp_pose_reference_content(item, max_images=max_images)

    def agent_mcp_pose_prompt(self, task: dict[str, Any], plan: dict[str, Any], pose: dict[str, Any], chroma_screen: dict[str, Any] | None=None) -> str:
        return self.render.agent_mcp_pose_prompt(task, plan, pose, chroma_screen)

    def agent_mcp_pose_output_path(self, task: dict[str, Any], accessory_id: str, pose_id: str, mime_type: str) -> Path:
        return self.artifacts.agent_mcp_pose_output_path(task, accessory_id, pose_id, mime_type)

    def write_agent_mcp_pose_artifact(self, task: dict[str, Any], call: dict[str, Any], result: dict[str, Any], *, prompt: str, reference_assets: list[dict[str, Any]]) -> dict[str, Any]:
        return self.artifacts.write_agent_mcp_pose_artifact(task, call, result, prompt=prompt, reference_assets=reference_assets)

    def object_photo_highlight_source_paths(self, item: dict[str, Any], *, limit: int=3) -> list[Path]:
        return self.sources.object_photo_highlight_source_paths(item, limit=limit)

    def photo_highlight_clean_sprites_ready(self, item: dict[str, Any], source_paths: list[Path]) -> bool:
        return self.sources.photo_highlight_clean_sprites_ready(item, source_paths)

    def pipeline_photo_highlight_object_items(self, task: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
        return self.selection.pipeline_photo_highlight_object_items(task, config)

    def mark_legacy_pose_flow_skipped_for_photo_highlight(self, task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> dict[str, Any]:
        return self.photos.mark_legacy_pose_flow_skipped_for_photo_highlight(task, config, orchestration)

    def photo_highlight_mask_prompt(self, item: dict[str, Any]) -> str:
        return self.image_input.photo_highlight_mask_prompt(item)

    def photo_highlight_input_data_url(self, image_bgr: np.ndarray) -> tuple[np.ndarray, str, float, float] | None:
        return self.image_input.photo_highlight_input_data_url(image_bgr)

    def photo_highlight_auto_compare(self, ai_roi_mask: np.ndarray, auto_roi_mask: np.ndarray | None) -> dict[str, Any]:
        return self.comparison.photo_highlight_auto_compare(ai_roi_mask, auto_roi_mask)

    def build_clean_sprites_from_photo_highlight_masks(self, task: dict[str, Any], item: dict[str, Any], provider: PoseImageProvider, model: str, *, force: bool=False) -> tuple[bool, str]:
        return self.builder.build_clean_sprites_from_photo_highlight_masks(task, item, provider, model, force=force)

    def prepare_photo_highlight_sprites_for_task(self, task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> tuple[bool, bool]:
        return self.photos.prepare_photo_highlight_sprites_for_task(task, config, orchestration)

    def execute_agent_mcp_pose_tool_calls(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        return self.execution.execute_agent_mcp_pose_tool_calls(task, config)

    def ensure_agent_mcp_pose_plan(self, task: dict[str, Any], config: dict[str, Any], *, force: bool=False) -> dict[str, Any]:
        return self.photos.ensure_agent_mcp_pose_plan(task, config, force=force)

    def ensure_agent_mcp_pose_tool_calls(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return self.registration.ensure_agent_mcp_pose_tool_calls(task, config)

    def prepare_agent_mcp_before_sample_generation(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        return self.samples.prepare_agent_mcp_before_sample_generation(task, config)

    def pipeline_uses_photo_highlight_sprite_flow(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        return bool(self.pipeline_photo_highlight_object_items(task, config))
