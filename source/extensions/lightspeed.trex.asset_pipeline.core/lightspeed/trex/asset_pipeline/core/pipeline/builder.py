"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = [
    "build_prepare_optimization_steps",
    "build_remix_mesh_pipeline",
    "build_remix_texture_pipeline",
]


from importlib import import_module
from typing import TYPE_CHECKING

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineStep

if TYPE_CHECKING:
    from ..jobs.models import ProcessedTexture

from .config import RemixAssetPipelineConfig


def build_prepare_optimization_steps(config: RemixAssetPipelineConfig) -> list[PipelineStep]:
    """Build the model-preparation step list.

    The returned steps import the model, clean up and convert its materials to AperturePBR, then
    discover its textures and record every composed layer. Conversion runs before discovery, as the
    legacy schema ran ``MaterialShaders`` before ``ConvertToDDS``, so discovery reads the AperturePBR
    input names and every source-shader texture reaches the texture job.

    Args:
        config: Run configuration consumed by the standardize-input step.

    Returns:
        The prepare phase steps, in order.
    """
    step_types = import_module("..steps", __package__)
    return [
        step_types.StandardizeInputStep(config.texture_type),
        step_types.MaterialCleanupStep(),
        step_types.ConvertMaterialsStep(),
        step_types.DiscoverTexturesStep(),
    ]


def build_remix_texture_pipeline() -> list[PipelineStep]:
    """Build the texture-processing step list for one standalone batch.

    Normal conversion and DDS encoding are the only steps that do real work for a texture item.
    The model-only steps are omitted rather than relied on to skip themselves.

    Returns:
        The texture phase steps, in order.
    """
    step_types = import_module("..steps", __package__)
    return [
        step_types.ConvertNormalStep(),
        step_types.ConvertDDSStep(),
    ]


def build_remix_mesh_pipeline(
    config: RemixAssetPipelineConfig,
    processed_textures: dict[tuple[str, TextureTypes], ProcessedTexture],
) -> list[PipelineStep]:
    """Build the mesh-optimization step list that consumes the processed textures.

    The import step runs first, because each queue job owns its own workspace. The prepare job's
    workspace is gone by now, so this job materializes the model and its textures again before any
    step reads them.

    Material cleanup and conversion ran in the prepare phase. They run again here because each job
    materializes the model afresh, and both skip a model that is already AperturePBR. The legacy
    model ingestion schema never triangulated meshes, so this pipeline keeps the authored topology.
    Texture application runs after material conversion, so the collected shader paths and input
    names are the post-conversion ones.

    An empty map means the model has no processed textures, so the step keeps the bindings the
    model already authored.

    Args:
        config: Run configuration consumed by the import step.
        processed_textures: Map from ``(material_path, texture_type)`` to the resolved
            ``ProcessedTexture``. Must be built by :func:`resolve_processed_textures` from
            the ledger and texture result before this builder is called.

    Returns:
        The mesh phase steps, in order.
    """
    step_types = import_module("..steps", __package__)
    steps: list[PipelineStep] = [
        step_types.StandardizeInputStep(config.texture_type),
        # Cleanup runs before conversion, matching the legacy schema, which cleared unassigned
        # materials and bound a fallback before it converted any shader.
        step_types.MaterialCleanupStep(),
        step_types.ConvertMaterialsStep(),
        step_types.NormalizeEmissiveIntensityStep(),
        step_types.ApplyProcessedTexturesStep(processed_textures),
    ]
    # Path rewriting runs last, once every texture output path is final.
    steps.append(step_types.ReferenceStep())
    # Root wrapping and unit scale run on the final composed stage, after path rewriting.
    steps.append(step_types.MetaStep())
    return steps
