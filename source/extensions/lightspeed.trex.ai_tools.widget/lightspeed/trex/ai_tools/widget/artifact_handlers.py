"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

import abc
import pathlib
from typing import Any

import carb
import lightspeed.trex.ai_tools.widget.job
import omni.flux.job_queue.core.events
import omni.flux.job_queue.core.interface
import omni.flux.job_queue.core.job
import omni.flux.job_queue.widget
import omni.kit.app
import omni.usd
from lightspeed.common.constants import REMIX_INGESTED_ASSETS_FOLDER
from lightspeed.trex.ai_tools.widget.job import OutputArtifact
from lightspeed.trex.utils.common.prim_utils import is_shader_prototype
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.flux.material_api import ShaderInfoAPI
from omni.flux.utils.common.api import send_request
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit import commands, undo
from pxr import Sdf, Usd


class ArtifactHandler(abc.ABC):
    """
    Base class for handling artifacts produced by ComfyUI workflows.

    Subclasses implement the logic for ingesting and applying specific
    artifact types (textures, meshes, etc.) to the USD stage.

    Handlers "claim" artifacts they can handle from a list. This allows
    flexible matching based on metadata, file extension, or any other criteria.

    Note: These handlers are internal to ComfyJobApplyHandler and not exposed
    through a separate registry. To add new artifact types, add them to the
    ARTIFACT_HANDLERS list in ComfyJobApplyHandler.
    """

    def __init__(self, context_name: str = ""):
        self.context_name = context_name

    @classmethod
    @abc.abstractmethod
    def claim(
        cls, artifacts: list[lightspeed.trex.ai_tools.widget.job.OutputArtifact]
    ) -> list[lightspeed.trex.ai_tools.widget.job.OutputArtifact]:
        """Claim artifacts this handler can process."""
        pass

    @abc.abstractmethod
    async def apply(
        self,
        prim_paths: list[str],
        artifacts: list[lightspeed.trex.ai_tools.widget.job.OutputArtifact],
    ) -> None:
        """Apply artifacts to the given prims."""
        pass


class ComfyJobApplyHandler(omni.flux.job_queue.widget.ApplyHandler):
    """
    Apply handler for ComfyUI jobs.

    This handler processes ComfyJob results by delegating to specialized
    ArtifactHandlers for different output types.

    Artifact handlers are defined in ARTIFACT_HANDLERS and are checked in order.
    Each handler "claims" artifacts it can process, and unclaimed artifacts
    are logged as warnings.
    """

    # Artifact handlers in priority order. First handler to claim an artifact wins.
    # Defined as a class variable so subclasses can extend or override.
    ARTIFACT_HANDLERS: list[type[ArtifactHandler]] = []  # Populated after class definitions below

    def __init__(self, context_name: str = ""):
        self.context_name = context_name

    @classmethod
    def can_handle(cls, job: omni.flux.job_queue.core.job.Job) -> bool:
        return isinstance(job, lightspeed.trex.ai_tools.widget.job.ComfyJob)

    def get_apply_context(self, job: omni.flux.job_queue.core.job.Job) -> dict[str, Any]:
        context = omni.usd.get_context(self.context_name)
        stage = context.get_stage()
        if stage is None:
            return {}
        edit_target = stage.GetEditTarget()
        return {"edit_target": str(edit_target.GetLayer().identifier)}

    def _claim_artifacts(
        self,
        artifacts: list[lightspeed.trex.ai_tools.widget.job.OutputArtifact],
    ) -> dict[type[ArtifactHandler], list[lightspeed.trex.ai_tools.widget.job.OutputArtifact]]:
        """
        Route artifacts to appropriate handlers.

        Each handler claims artifacts it can process. Artifacts are only
        processed by the first handler that claims them.
        """
        result: dict[type[ArtifactHandler], list[lightspeed.trex.ai_tools.widget.job.OutputArtifact]] = {}
        remaining = list(artifacts)

        for handler_class in self.ARTIFACT_HANDLERS:
            if not remaining:
                break
            claimed = handler_class.claim(remaining)
            if claimed:
                result[handler_class] = claimed
                remaining = [a for a in remaining if a not in claimed]

        for artifact in remaining:
            carb.log_warn(
                f"[ComfyJobApplyHandler] No handler claimed artifact: {artifact.path} (metadata: {artifact.metadata})"
            )
        return result

    async def apply(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        job: omni.flux.job_queue.core.job.Job,
    ) -> None:
        if not isinstance(job, lightspeed.trex.ai_tools.widget.job.ComfyJob):
            raise TypeError(f"Expected ComfyJob, got {type(job).__name__}")

        result_event = interface.get_latest_event(job.job_id, omni.flux.job_queue.core.events.Result)
        if result_event is None:
            raise ValueError(f"No result event found for job {job.job_id}")

        artifacts: list[lightspeed.trex.ai_tools.widget.job.OutputArtifact] = result_event.value
        prim_paths = job.prim_paths

        if not prim_paths:
            raise ValueError(f"No prim paths found for job {job.job_id}")

        claimed = self._claim_artifacts(artifacts)

        carb.log_info(f"[ComfyJobApplyHandler] Applying {len(artifacts)} artifacts to {len(prim_paths)} prims")
        for handler_class, handler_artifacts in claimed.items():
            carb.log_info(f"  {handler_class.__name__}: {len(handler_artifacts)} artifacts")

        for handler_class, handler_artifacts in claimed.items():
            handler = handler_class(self.context_name)
            await handler.apply(prim_paths, handler_artifacts)


def register_apply_handlers() -> None:
    """Register AI Tools job apply handlers."""
    omni.flux.job_queue.widget.ApplyHandlerRegistry.register(ComfyJobApplyHandler)


def unregister_apply_handlers() -> None:
    """Unregister AI Tools job apply handlers."""
    omni.flux.job_queue.widget.ApplyHandlerRegistry.unregister(ComfyJobApplyHandler)


def _iter_related_prims(prim: Usd.Prim):
    from lightspeed.trex.ai_tools.widget.job_generator import iter_related_prims  # noqa: PLC0415

    return iter_related_prims(prim)


class TextureArtifactHandler(ArtifactHandler):
    """Handles texture artifacts from ComfyUI workflows."""

    TEXTURE_TYPE_MAP = {
        "albedo": TextureTypes.DIFFUSE,
        "diffuse": TextureTypes.DIFFUSE,
        "basecolor": TextureTypes.DIFFUSE,
        "roughness": TextureTypes.ROUGHNESS,
        "metallic": TextureTypes.METALLIC,
        "metalness": TextureTypes.METALLIC,
        "normal_ogl": TextureTypes.NORMAL_OGL,
        "normal_dx": TextureTypes.NORMAL_DX,
        "normal_oth": TextureTypes.NORMAL_OTH,
        "height": TextureTypes.HEIGHT,
        "displacement": TextureTypes.HEIGHT,
        "emissive": TextureTypes.EMISSIVE,
        "emission": TextureTypes.EMISSIVE,
    }
    TEXTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".dds", ".tga", ".bmp", ".exr", ".hdr"}

    @classmethod
    def claim(
        cls, artifacts: list[lightspeed.trex.ai_tools.widget.job.OutputArtifact]
    ) -> list[lightspeed.trex.ai_tools.widget.job.OutputArtifact]:
        claimed = []
        for artifact in artifacts:
            remix_type = artifact.get("remix_type", "")
            if remix_type == "texture_file_path":
                claimed.append(artifact)
                continue
            ext = artifact.path.suffix.lower()
            if ext in cls.TEXTURE_EXTENSIONS:
                claimed.append(artifact)
        return claimed

    def _get_texture_type(self, artifact: OutputArtifact) -> TextureTypes:
        texture_type_str = artifact.get("texture_type")
        if texture_type_str:
            texture_type = self.TEXTURE_TYPE_MAP.get(texture_type_str.lower())
            if texture_type:
                return texture_type
        name = artifact.get("name", "")
        if name:
            texture_type = self.TEXTURE_TYPE_MAP.get(name.lower())
            if texture_type:
                return texture_type
        return self._guess_texture_type_from_filename(artifact.path.name)

    @staticmethod
    def _guess_texture_type_from_filename(filename: str) -> TextureTypes:
        lowered = filename.lower()
        if "albedo" in lowered or "diffuse" in lowered or "basecolor" in lowered:
            return TextureTypes.DIFFUSE
        if "roughness" in lowered:
            return TextureTypes.ROUGHNESS
        if "metallic" in lowered or "metalness" in lowered:
            return TextureTypes.METALLIC
        if "normal_ogl" in lowered:
            return TextureTypes.NORMAL_OGL
        if "normal_dx" in lowered:
            return TextureTypes.NORMAL_DX
        if "normal_oth" in lowered:
            return TextureTypes.NORMAL_OTH
        if "height" in lowered or "displacement" in lowered or "depth" in lowered:
            return TextureTypes.HEIGHT
        if "emissive" in lowered or "emission" in lowered:
            return TextureTypes.EMISSIVE
        return TextureTypes.OTHER

    @staticmethod
    async def _ingest_texture(texture_type: TextureTypes, path: pathlib.Path, output_directory: str) -> str:
        context_data = {
            "input_files": [(str(path), texture_type.name)],
            "output_directory": output_directory,
        }
        request_data = {"executor": 0, "context_plugin": {"data": context_data}}
        data = await send_request("POST", "/ingestcraft/mass-validator/queue/material", json=request_data)
        ingested_paths = set()
        for completed_task in data.get("completed_schemas", []):
            for check_plugin in completed_task.get("check_plugins", []):
                for dataflow in check_plugin.get("data", {}).get("data_flows") or []:
                    if dataflow.get("channel") == "ingestion_output":
                        ingested_paths.update(dataflow.get("output_data", []))
        if len(ingested_paths) != 1:
            raise ValueError(f"Expected exactly one ingested path, got: {ingested_paths}")
        return ingested_paths.pop()

    async def _ingest_textures(
        self,
        prim: Usd.Prim,
        output_directory: str,
        artifacts: list[OutputArtifact],
    ) -> list[tuple[str, str, TextureTypes]]:
        results: list[tuple[str, str, TextureTypes]] = []
        for artifact in artifacts:
            texture_type = self._get_texture_type(artifact)
            input_name = TEXTURE_TYPE_INPUT_MAP.get(texture_type)
            if not input_name:
                carb.log_warn(f"[TextureArtifactHandler] No input mapping for texture type {texture_type}")
                continue
            attr_path = str(prim.GetPath().AppendProperty(input_name))
            name = artifact.get("name", artifact.path.stem)
            carb.log_info(f"[TextureArtifactHandler] Ingesting {name} as {texture_type.name} -> {input_name}")
            try:
                ingested_path = await self._ingest_texture(texture_type, artifact.path, output_directory)
                results.append((attr_path, ingested_path, texture_type))
            except Exception as e:  # noqa: BLE001
                carb.log_error(f"[TextureArtifactHandler] Failed to ingest {name}: {e}")
        return results

    @staticmethod
    def _apply_texture_replacement(prim: Usd.Prim, texture_attr_path: str, texture_asset_path: str) -> None:
        carb.log_info(f"[TextureArtifactHandler] Applying override {texture_attr_path} -> {texture_asset_path}")
        stage = prim.GetStage()
        attr_type = None
        attr_path = Sdf.Path(texture_attr_path)
        for input_property in ShaderInfoAPI(prim).get_input_properties():
            if attr_path.name == input_property.GetName():
                attr_type = Sdf.ValueTypeNames.Find(input_property.GetTypeName())
                break
        if attr_type is None:
            attr_type = Sdf.ValueTypeNames.Asset
            carb.log_info(f"[TextureArtifactHandler] Creating new attribute {texture_attr_path} with type Asset")
        commands.execute(
            "ChangeProperty",
            prop_path=texture_attr_path,
            value=Sdf.AssetPath(omni.usd.make_path_relative_to_current_edit_target(texture_asset_path, stage=stage)),
            prev=None,
            type_to_create_if_not_exist=attr_type,
            target_layer=stage.GetEditTarget().GetLayer(),
        )

    def _get_target_shader_prim(self, prim: Usd.Prim) -> Usd.Prim | None:
        for related_prim in _iter_related_prims(prim):
            if is_shader_prototype(related_prim):
                return related_prim
        return None

    async def apply(
        self,
        prim_paths: list[str],
        artifacts: list[OutputArtifact],
    ) -> None:
        context = omni.usd.get_context(self.context_name)
        stage = context.get_stage()
        if not stage:
            raise ValueError("No stage is currently loaded.")
        root_layer = stage.GetRootLayer()
        if root_layer.anonymous:
            raise ValueError("No project is currently loaded.")
        project_url = OmniUrl(root_layer.realPath)
        output_directory = str(OmniUrl(project_url.parent_url) / REMIX_INGESTED_ASSETS_FOLDER)
        carb.log_info(
            f"[TextureArtifactHandler] Processing {len(artifacts)} texture artifacts for {len(prim_paths)} prims..."
        )
        for artifact in artifacts:
            carb.log_info(f"  {artifact.get('name', artifact.path.name)}: {artifact.path}")
        with undo.group():
            for prim_path in prim_paths:
                prim = stage.GetPrimAtPath(prim_path)
                if not prim:
                    carb.log_warn(f"[TextureArtifactHandler] Prim not found: {prim_path}, skipping")
                    continue
                target_prim = self._get_target_shader_prim(prim)
                if target_prim is None:
                    carb.log_warn(
                        f"[TextureArtifactHandler] No shader found for prim {prim_path} or its related prims, skipping"
                    )
                    continue
                target_prim_path = target_prim.GetPath()
                texture_replacements = await self._ingest_textures(target_prim, output_directory, artifacts)
                await omni.kit.app.get_app().next_update_async()
                stage = context.get_stage()
                if not stage:
                    carb.log_warn("[TextureArtifactHandler] Stage closed during async operation, aborting")
                    return
                target_prim = stage.GetPrimAtPath(target_prim_path)
                if not target_prim:
                    carb.log_warn(
                        f"[TextureArtifactHandler] Target prim no longer exists: {target_prim_path}, skipping"
                    )
                    continue
                carb.log_info(
                    f"[TextureArtifactHandler] Applying {len(texture_replacements)} "
                    f"texture replacements to {prim_path}..."
                )
                for texture_attr_path, texture_asset_path, _texture_type in texture_replacements:
                    self._apply_texture_replacement(target_prim, texture_attr_path, texture_asset_path)
        carb.log_info("[TextureArtifactHandler] Done with texture replacements.")


# Configure the artifact handlers for ComfyJobApplyHandler
# Order matters: first handler to claim an artifact wins
ComfyJobApplyHandler.ARTIFACT_HANDLERS = [
    TextureArtifactHandler,
]
