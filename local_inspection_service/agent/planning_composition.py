"""Compose unchanged pose planning around templates and narrow external capabilities."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Pattern
from .pose_plan_ports import Record, PlanStrings, PlanEncoder, PlanSerializer, GeneratePosePlan, EnsurePosePlan
from .pose_asset_ports import PoseTemplateIdentity, PoseTemplateCalls
from .pose_templates import AgentPoseTemplates
from .pose_plan_policy import PosePlanPolicy
from .pose_plan_generation import PosePlanGeneration
from .pose_plan_assembly import PosePlanAssembly
from .pose_plan_ports import PosePlanIdentity, PosePlanContent, PosePlanRuntime, PosePlanTemplates, PosePlanProvider, PosePlanMedia, PosePlanCalls, PosePlanCatalog

@dataclass(frozen=True)
class PolicyPosePlanIdentityInputs:
    uid: Callable[[], Callable[[Record], str]]
    material: Callable[[], Callable[[Record], str]]
    sanitize: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class GenerationPosePlanIdentityInputs:
    uid: Callable[[], Callable[[Record], str]]
    material: Callable[[], Callable[[Record], str]]
    sanitize: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class AssemblyPosePlanIdentityInputs:
    uid: Callable[[], Callable[[Record], str]]
    material: Callable[[], Callable[[Record], str]]
    sanitize: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class AssemblyPosePlanCatalogInputs:
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]
    canonical_ids: Callable[[], Callable[[Record, list[str]], list[str]]]

class PosePlanningWorkflows:
    """Build templates, policy, provider generation and task plans without starting work."""
    def __init__(self, *, templates_identity: PoseTemplateIdentity,
                 policy_identity: PolicyPosePlanIdentityInputs,
                 policy_content: PosePlanContent,
                 policy_runtime: PosePlanRuntime,
                 generation_identity: GenerationPosePlanIdentityInputs,
                 generation_content: PosePlanContent,
                 generation_runtime: PosePlanRuntime,
                 generation_provider: PosePlanProvider,
                 generation_media: PosePlanMedia,
                 assembly_identity: AssemblyPosePlanIdentityInputs,
                 assembly_runtime: PosePlanRuntime,
                 assembly_catalog: AssemblyPosePlanCatalogInputs):
        self.templates = AgentPoseTemplates(
            PoseTemplateIdentity(
                uid=templates_identity.uid,
                kind=templates_identity.kind,
                search=templates_identity.search,
            ),
            PoseTemplateCalls(
                request=lambda: self.agent_mcp_pose_request,
            ),
        )
        self.policy = PosePlanPolicy(
            PosePlanIdentity(
                uid=policy_identity.uid,
                material=policy_identity.material,
                kind=lambda: self.agent_mcp_object_kind,
                sanitize=policy_identity.sanitize,
            ),
            PosePlanContent(
                size=policy_content.size,
                sprites=policy_content.sprites,
                bounded=policy_content.bounded,
                optional_number=policy_content.optional_number,
                strings=policy_content.strings,
                compile=policy_content.compile,
            ),
            PosePlanRuntime(
                now=policy_runtime.now,
                version=policy_runtime.version,
                max_poses=policy_runtime.max_poses,
                min_confidence=policy_runtime.min_confidence,
                clock=policy_runtime.clock,
            ),
            PosePlanTemplates(
                request=lambda: self.agent_mcp_pose_request,
                poses=lambda: self.agent_mcp_pose_templates,
                fallback=lambda: self.fallback_accessory_pose_plan,
            ),
        )
        self.generation = PosePlanGeneration(
            PosePlanIdentity(
                uid=generation_identity.uid,
                material=generation_identity.material,
                kind=lambda: self.agent_mcp_object_kind,
                sanitize=generation_identity.sanitize,
            ),
            PosePlanContent(
                size=generation_content.size,
                sprites=generation_content.sprites,
                bounded=generation_content.bounded,
                optional_number=generation_content.optional_number,
                strings=generation_content.strings,
                compile=generation_content.compile,
            ),
            PosePlanRuntime(
                now=generation_runtime.now,
                version=generation_runtime.version,
                max_poses=generation_runtime.max_poses,
                min_confidence=generation_runtime.min_confidence,
                clock=generation_runtime.clock,
            ),
            PosePlanTemplates(
                request=lambda: self.agent_mcp_pose_request,
                poses=lambda: self.agent_mcp_pose_templates,
                fallback=lambda: self.fallback_accessory_pose_plan,
            ),
            PosePlanProvider(
                settings=generation_provider.settings,
                call=generation_provider.call,
                dumps=generation_provider.dumps,
            ),
            PosePlanMedia(
                path=generation_media.path,
                encode=generation_media.encode,
                max_side=generation_media.max_side,
                quality=generation_media.quality,
            ),
            PosePlanCalls(
                payload=lambda: self.accessory_pose_plan_prompt_payload,
                prompt=lambda: self.pose_plan_system_prompt,
                normalize=lambda: self.normalize_accessory_pose_plan,
                generate=lambda: self.generate_accessory_pose_plan,
            ),
        )
        self.assembly = PosePlanAssembly(
            PosePlanIdentity(
                uid=assembly_identity.uid,
                material=assembly_identity.material,
                kind=lambda: self.agent_mcp_object_kind,
                sanitize=assembly_identity.sanitize,
            ),
            PosePlanRuntime(
                now=assembly_runtime.now,
                version=assembly_runtime.version,
                max_poses=assembly_runtime.max_poses,
                min_confidence=assembly_runtime.min_confidence,
                clock=assembly_runtime.clock,
            ),
            PosePlanTemplates(
                request=lambda: self.agent_mcp_pose_request,
                poses=lambda: self.agent_mcp_pose_templates,
                fallback=lambda: self.fallback_accessory_pose_plan,
            ),
            PosePlanCatalog(
                lookup=assembly_catalog.lookup,
                counts=assembly_catalog.counts,
                canonical_ids=assembly_catalog.canonical_ids,
                ensure=lambda: self.ensure_accessory_pose_plan,
            ),
        )

    def agent_mcp_object_kind(self, item: dict[str, Any]) -> str:
        return self.templates.agent_mcp_object_kind(item)

    def agent_mcp_pose_request(self) -> dict[str, Any]:
        return self.templates.agent_mcp_pose_request()

    def agent_mcp_pose_templates(self, base_id: str, object_kind: str) -> list[dict[str, Any]]:
        return self.templates.agent_mcp_pose_templates(base_id, object_kind)

    def accessory_pose_plan_prompt_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        return self.policy.accessory_pose_plan_prompt_payload(item)

    def pose_plan_system_prompt(self) -> str:
        return self.policy.pose_plan_system_prompt()

    def fallback_accessory_pose_plan(self, item: dict[str, Any]) -> dict[str, Any]:
        return self.policy.fallback_accessory_pose_plan(item)

    def normalize_accessory_pose_plan(self, raw: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        return self.policy.normalize_accessory_pose_plan(raw, item)

    def generate_accessory_pose_plan(self, item: dict[str, Any], *, allow_provider: bool=True, force: bool=False) -> dict[str, Any] | None:
        return self.generation.generate_accessory_pose_plan(item, allow_provider=allow_provider, force=force)

    def ensure_accessory_pose_plan(self, item: dict[str, Any], *, force: bool=False) -> dict[str, Any] | None:
        return self.generation.ensure_accessory_pose_plan(item, force=force)

    def build_agent_mcp_pose_plan(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return self.assembly.build_agent_mcp_pose_plan(task, config)
