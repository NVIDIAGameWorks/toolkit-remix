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

__all__ = ["ApplyProcessedTexturesStep"]

import pathlib

import carb
import omni.client
import omni.usd
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.common.path_utils import (
    get_absolute_path_from_relative,
    texture_to_udim as _texture_to_udim,
)
from pxr import Sdf, Usd, UsdShade

from ..jobs.models import ProcessedTexture
from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import AssetKind, RemixAssetItem, TextureAsset, TextureBinding
from ..pipeline.texture_inputs import get_source_texture_paths, get_texture_source_identity, iter_texture_inputs
from ..utils import get_authoring_spec
from ..worker import run_in_worker_thread


class ApplyProcessedTexturesStep(PipelineStep):
    """Resolve, correlate, and apply processed textures to model USD stages in one pass.

    Opens the stage once for each model item, walks every material's shader inputs to find
    texture binding sites, correlates each binding against processed texture outputs through
    the prepare-phase ledger, and writes the final asset paths on the authoring layers.

    For a model whose textures were never processed, the step still walks the stage and
    materialises texture records so publication carries the unconverted files.
    """

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    def __init__(
        self,
        processed_textures: dict[tuple[str, TextureTypes], ProcessedTexture],
    ) -> None:
        """Store the validated identity-to-processed-texture map.

        An empty map means the model has no processed textures. The step still walks the stage
        and records source bindings so publication carries the unconverted files.

        Args:
            processed_textures: Map from ``(material_path, texture_type)`` to the resolved
                ``ProcessedTexture`` that belongs to that binding identity. Must be validated
                by :func:`resolve_processed_textures` before construction.
        """
        super().__init__()
        self._processed_textures = processed_textures

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "apply_processed_textures"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Apply processed textures"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when a model item has not had textures applied yet."""
        state = context.execution_state.get(self.name)
        if state and state.did_run:
            return False
        return any(item.kind is AssetKind.MODEL for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why texture application has no work."""
        if not any(item.kind is AssetKind.MODEL for item in context.items):
            return "no model items"
        return "apply_processed_textures already completed"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Walk every model stage once to resolve, correlate, and write texture bindings.

        Each binding is rewritten in the layer that authored the composed value, since that
        layer (root or a referenced child such as ``SubUSDs/child.usda``) owns the reference.

        For a UDIM texture the shader receives the ``<UDIM>`` token form derived from the first
        concrete tile, or an empty asset path when ``context.replace_udim_textures_by_empty``
        is true.

        For an octahedral normal the step also authors ``inputs:encoding = 0`` on the shader prim.

        A discovered binding with no matching processed-texture entry is not an error here: the
        step falls back to the resolved source texture, so direct/standalone use runs without a
        texture-processing job. The connected graph enforces strict ledger/result validation before
        this step runs, through :func:`resolve_processed_textures`.

        Raises:
            FileNotFoundError: If an authored texture path cannot be resolved to a readable file.
            RuntimeError: If a recorded shader or texture attribute no longer exists, or if a
                binding's authored value cannot be traced back to a real layer inside the model.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            source_texture_paths = get_source_texture_paths(item)
            stage = await context.open_stage(item.value)
            item.textures.clear()
            item.texture_bindings.clear()
            texture_by_key: dict[str, TextureAsset] = {}

            # Collision-safe local-key space when the ledger is empty (no processed textures).
            local_seq = 0

            # Walk materials to find texture binding sites.
            for prim in stage.Traverse():
                if not prim.IsA(UsdShade.Material):
                    continue

                shader_prim = omni.usd.get_shader_from_material(prim, get_prim=True)
                if shader_prim is None or not shader_prim.IsValid():
                    continue

                material_path = str(prim.GetPath())

                for texture_type, input_name in iter_texture_inputs(shader_prim):
                    attr = shader_prim.GetAttribute(input_name)
                    if not attr or not attr.HasAuthoredValue():
                        continue

                    original_asset_path = attr.Get()
                    if not isinstance(original_asset_path, Sdf.AssetPath) or not original_asset_path.path:
                        continue

                    resolved_path = pathlib.Path(
                        original_asset_path.resolvedPath
                        or get_absolute_path_from_relative(original_asset_path.path, stage.GetRootLayer())
                    )
                    # A <UDIM> token path names a pattern, not a concrete file, so exists() is
                    # always false for it and the check would reject every UDIM model.
                    if "<UDIM>" not in original_asset_path.path and not await run_in_worker_thread(
                        resolved_path.exists
                    ):
                        raise FileNotFoundError(
                            f"Texture path on {attr.GetPath()} does not resolve to a readable file: "
                            f"{original_asset_path.path}"
                        )

                    # --- Correlate against processed textures ---
                    identity = (material_path, texture_type)
                    processed = self._processed_textures.get(identity)
                    if processed is not None:
                        texture = texture_by_key.get(processed.key)
                        if texture is None:
                            texture = TextureAsset(
                                path=pathlib.Path(processed.asset_url),
                                texture_type=processed.texture_type,
                                key=processed.key,
                                original_path=get_texture_source_identity(item, resolved_path, source_texture_paths),
                                udim_tiles=tuple(pathlib.Path(tile_url) for tile_url in processed.udim_tiles),
                            )
                            texture_by_key[processed.key] = texture
                    else:
                        # No processed texture for this binding; keep the resolved source.
                        local_key = str(resolved_path)
                        texture = texture_by_key.get(local_key)
                        if texture is None:
                            texture = TextureAsset(
                                path=resolved_path,
                                texture_type=texture_type,
                                key=f"texture_{local_seq}",
                                original_path=get_texture_source_identity(item, resolved_path, source_texture_paths),
                            )
                            local_seq += 1
                            texture_by_key[local_key] = texture

                    binding = TextureBinding(
                        shader_path=shader_prim.GetPath(),
                        input_name=input_name,
                        original_asset_path=original_asset_path,
                        texture=texture,
                        material_path=material_path,
                    )
                    item.texture_bindings.append(binding)

            item.textures = list(texture_by_key.values())

            # --- Write the final asset paths on the authoring layers ---
            model_output = context.get_output_path(item.value, source_path=item.source_path)
            model_parent = item.value.resolve().parent
            changed_layers: dict[str, Sdf.Layer] = {}
            with Sdf.ChangeBlock():
                for binding in item.texture_bindings:
                    shader_prim = stage.GetPrimAtPath(binding.shader_path)
                    if not shader_prim:
                        raise RuntimeError(f"Texture binding shader no longer exists: {binding.shader_path}")

                    attr = shader_prim.GetAttribute(binding.input_name)
                    if not attr:
                        raise RuntimeError(
                            f"Texture binding attribute '{binding.input_name}' no longer exists "
                            f"on {binding.shader_path}"
                        )

                    authoring_spec = get_authoring_spec(attr, model_parent)
                    authoring_layer = authoring_spec.layer
                    authoring_layer_path = pathlib.Path(authoring_layer.realPath).resolve()
                    relative_layer_path = authoring_layer_path.relative_to(model_parent)

                    owner_output = model_output.parent / relative_layer_path
                    is_udim = bool(binding.texture.udim_tiles)

                    if context.is_in_work_dir(owner_output):
                        owner_output = context.get_output_path(owner_output, source_path=owner_output)

                    if is_udim and context.replace_udim_textures_by_empty:
                        new_asset_path = Sdf.AssetPath("")
                    else:
                        # The runner publishes every texture record to its reserved output beside the
                        # model, so the model refers to that published copy: never to the texture
                        # job's own output directory and never to a source file elsewhere. The
                        # relative URL keeps the ``./`` form the legacy ``RelativeAssetPaths`` fix wrote.
                        texture_path = binding.texture.udim_tiles[0] if is_udim else binding.texture.path
                        texture_output = context.get_output_path(texture_path, source_path=binding.texture.source_path)
                        if is_udim:
                            texture_output = pathlib.Path(_texture_to_udim(str(texture_output)))
                        new_asset_path = Sdf.AssetPath(
                            omni.client.make_relative_url(str(owner_output), str(texture_output))
                        )

                    if authoring_spec.default != new_asset_path:
                        authoring_spec.default = new_asset_path
                        changed_layers[authoring_layer.identifier] = authoring_layer

                    # Author the octahedral encoding attribute when the texture is a converted normal.
                    if binding.texture.texture_type is TextureTypes.NORMAL_OTH:
                        encoding_attr = shader_prim.GetAttribute("inputs:encoding")
                        if encoding_attr:
                            encoding_property_stack = encoding_attr.GetPropertyStack(Usd.TimeCode.Default())
                            encoding_spec = encoding_property_stack[0] if encoding_property_stack else None
                            encoding_layer = encoding_spec.layer if encoding_spec is not None else None
                            if (
                                encoding_spec is not None
                                and encoding_layer is not None
                                and encoding_layer.realPath
                                and encoding_spec.default != 0
                            ):
                                encoding_spec.default = 0
                                changed_layers[encoding_layer.identifier] = encoding_layer

            for layer in changed_layers.values():
                layer.Save()

            if changed_layers:
                carb.log_info(f"[ApplyProcessedTextures] Saved updated stage {item.value}")
