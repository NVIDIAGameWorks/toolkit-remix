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

__all__ = ["AlphaCardToMesh"]

from typing import Any

from lightspeed.common import constants
from lightspeed.trex.alpha_cutout.core import (
    CutoutParameters,
    get_bound_material,
    get_diffuse_texture_path,
    is_convertible_mesh,
    read_origin,
    snapshot_material,
)
from lightspeed.trex.asset_modifiers.factory import AssetModifierBase, AssetModifierJob, ModifierInput
from lightspeed.trex.asset_pipeline.core.jobs import add_asset_optimization_jobs
from lightspeed.trex.asset_pipeline.core.jobs.apply_handler import SaveMeshMetadataHandler
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_handler import AssetReplaceApplyHandler
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_target import AssetReplaceApplyTarget
from lightspeed.trex.utils.common.prim_utils import is_mesh_asset
from omni.flux.job_queue.core.job import JobGraph, JobOutputs
from pxr import Sdf, Usd, UsdGeom, UsdShade

from .job import AlphaCardToMeshJob
from .values import MATERIAL_KEY, MATERIAL_PRIM_KEY, MESHES_KEY, PRIM_PATH_KEY, TEXTURE_KEY

_DEFAULTS = CutoutParameters()
_PARAMETERS_GROUP = "Parameters"
_THICKEN_GROUP = "Thicken"
_NORMALS_GROUP = "Normals"
_NO_MESH_REASON = "No selected mesh has a diffuse texture to cut along."
_NO_FILE_REASON = "The model file could not be opened."


class AlphaCardToMesh(AssetModifierBase):
    """Cut alpha-tested meshes along their texture alpha, optimize the result and replace the source reference."""

    name = "alpha_card_to_mesh"
    display_name = "Alpha Card to Mesh"
    tooltip = (
        "Cut alpha-tested cards along the alpha channel of their diffuse texture so only the opaque area remains "
        "as geometry, and disable alpha testing on the result."
    )
    description = (
        "Cuts alpha-tested meshes, such as foliage cards, along the alpha channel of their diffuse texture.\n"
        "Only the opaque area remains as geometry and alpha testing is disabled on the result,\n"
        "so the path tracer no longer evaluates the transparent parts.\n"
        "Skinned meshes, meshes with geometry subsets and meshes without a diffuse texture are left out.\n"
        "Running the modifier on a converted mesh converts its original model again."
    )
    experimental = True
    job_type = AlphaCardToMeshJob
    inputs = (
        ModifierInput(
            "alpha_threshold",
            "Alpha Threshold",
            int,
            _DEFAULTS.alpha_threshold,
            tooltip="Alpha value from 0 to 255 at or above which a texel counts as opaque.",
            min_value=0,
            max_value=255,
        ),
        ModifierInput(
            "trace_resolution",
            "Trace Resolution",
            int,
            _DEFAULTS.trace_resolution,
            tooltip="Longest side of the traced mask in texels. Larger values follow the texture more closely and "
            "produce more triangles.",
            min_value=64,
            max_value=1024,
        ),
        ModifierInput(
            "simplify_tolerance",
            "Simplify Tolerance",
            float,
            _DEFAULTS.simplify_tolerance,
            tooltip="Largest deviation from the traced outline in texels. Larger values produce fewer triangles.",
            min_value=0.0,
        ),
        ModifierInput(
            "edge_margin",
            "Edge Margin",
            float,
            _DEFAULTS.edge_margin,
            tooltip="Distance in texels the outline grows beyond the opaque area. Negative values shrink it. Keep "
            "zero when alpha testing is disabled, because the cut edge then is the visible silhouette.",
        ),
        ModifierInput(
            "min_island_area",
            "Minimum Island Area",
            float,
            _DEFAULTS.min_island_area,
            tooltip="Opaque islands smaller than this many texels are dropped.",
            min_value=0.0,
        ),
        ModifierInput(
            "minimal_outline",
            "Minimal Vertex Outline",
            bool,
            _DEFAULTS.minimal_outline,
            tooltip="Connect the traced cutoff with the fewest points that stay within the simplify tolerance "
            "instead of the greedy pass. Slightly slower and yields fewer triangles for the same accuracy.",
        ),
        ModifierInput(
            "disable_alpha_test",
            "Disable Alpha Test",
            bool,
            _DEFAULTS.disable_alpha_test,
            tooltip="Author the opaque alpha state on the material so the runtime skips alpha testing for the cut "
            "mesh. The material property panel labels the alpha test type with the shader enum, which lists the "
            "runtime value as Greater Or Equal.",
        ),
        ModifierInput(
            "thicken",
            "Thicken Mesh",
            bool,
            _DEFAULTS.thicken,
            group=_THICKEN_GROUP,
            tooltip="Extrude the cut mesh backwards, against the surface normal, by the thickness. Adds two "
            "triangles per outline edge.",
        ),
        ModifierInput(
            "thickness",
            "Thickness",
            float,
            _DEFAULTS.thickness,
            group=_THICKEN_GROUP,
            tooltip="Extrusion distance in mesh units, before the mesh transform.",
            min_value=0.0,
            visible_if=lambda values: values["thicken"],
        ),
        ModifierInput(
            "thicken_back_face",
            "Back Face",
            bool,
            _DEFAULTS.thicken_back_face,
            group=_THICKEN_GROUP,
            tooltip="Close the extrusion with a reversed copy of the front face. Turn it off to keep only the "
            "sides; a double-sided capture still shows its front face from behind.",
            visible_if=lambda values: values["thicken"],
        ),
        ModifierInput(
            "thicken_anti_stretch",
            "UV Anti-Stretch",
            bool,
            _DEFAULTS.thicken_anti_stretch,
            group=_THICKEN_GROUP,
            tooltip="Texture the extruded sides with the band of the texture just inside the outline instead of "
            "smearing the edge texel across the thickness.",
            visible_if=lambda values: values["thicken"],
        ),
        ModifierInput(
            "smooth_normals",
            "Smooth Normals",
            bool,
            _DEFAULTS.smooth_normals,
            group=_THICKEN_GROUP,
            tooltip="Blend the normals of the thickened mesh towards the average around each position so the rim "
            "shades rounded instead of creased.",
            visible_if=lambda values: values["thicken"],
        ),
        ModifierInput(
            "smoothing",
            "Smoothing",
            float,
            _DEFAULTS.smoothing,
            group=_THICKEN_GROUP,
            tooltip="Strength of the normal smoothing: 0 keeps the flat rim, 1 averages fully.",
            min_value=0.0,
            max_value=1.0,
            visible_if=lambda values: values["thicken"] and values["smooth_normals"],
        ),
        ModifierInput(
            "up_normals",
            "Up-Facing Normals",
            bool,
            _DEFAULTS.up_normals,
            group=_NORMALS_GROUP,
            tooltip="Blend every vertex normal towards the stage up axis so a canopy of cards shades like one lit "
            "volume instead of a pile of differently tilted planes.",
        ),
        ModifierInput(
            "up_amount",
            "Up Amount",
            float,
            _DEFAULTS.up_amount,
            group=_NORMALS_GROUP,
            tooltip="Blend weight of the up direction: 0 keeps the original normals, 1 points them straight up.",
            min_value=0.0,
            max_value=1.0,
            visible_if=lambda values: values["up_normals"],
        ),
    )

    def summarize_result(self, outputs: JobOutputs) -> str | None:
        """Report the face and vertex counts of the handled meshes.

        Args:
            outputs: Outputs of a finished conversion job.

        Returns:
            The modifier name, the number of converted meshes and one line per mesh.
        """
        return f"{self.display_name}: {outputs[AlphaCardToMeshJob.REPORT].summarize()}"

    def is_compatible(self, prim: Usd.Prim) -> bool:
        """Accept geometry meshes and the prims the Selection panel selects for them.

        Args:
            prim: Stage Manager row prim or selected prim.

        Returns:
            ``True`` for a ``UsdGeom.Mesh``, and for a mesh asset row or a Remix reference prim that holds one;
            those two expand to the meshes below them.
        """
        if prim.IsA(UsdGeom.Mesh):
            return True
        if not is_mesh_asset(prim) and prim.GetAttribute(constants.IS_REMIX_REF_ATTR).Get() is not True:
            return False
        return any(child.IsA(UsdGeom.Mesh) for child in Usd.PrimRange(prim))

    def build_graph(
        self, stage: Usd.Stage | None, graph: JobGraph, job: AssetModifierJob, target: AssetReplaceApplyTarget | None
    ) -> None:
        """List the convertible meshes in the job, then optimize the cutout and replace the source reference.

        Args:
            stage: Open project stage, or ``None``.
            graph: Graph that already holds the job.
            job: The conversion job, before it runs.
            target: References to replace, or ``None`` for a File Path Constant source.
        """
        file_stage = Usd.Stage.Open(job.source_url)
        if not file_stage:
            job.skip_reason = _NO_FILE_REASON
            return
        origin_url = None
        if job.prim_paths and stage is not None:
            meshes, origin_url = _collect_selected_meshes(stage, file_stage, job.prim_paths, target)
        else:
            meshes = _collect_file_meshes(file_stage)
        if not meshes:
            job.skip_reason = _NO_MESH_REASON
            return
        job.values[MESHES_KEY] = meshes
        if origin_url:
            # A converted mesh is read from the model it came from, so every run starts from the original.
            job.source_url = origin_url
        add_asset_optimization_jobs(
            graph,
            job.output(AlphaCardToMeshJob.MESH_REQUEST),
            handler_type=AssetReplaceApplyHandler if target is not None else SaveMeshMetadataHandler,
            target=target,
        )


def _file_prim_path(
    prim_path: Sdf.Path, target: AssetReplaceApplyTarget | None, file_stage: Usd.Stage
) -> tuple[Sdf.Path, Sdf.Path] | None:
    """Map a project prim path to the path of the same prim inside the referenced model file.

    Args:
        prim_path: Path of the mesh in the project stage.
        target: References that compose the prim.
        file_stage: Stage of the model file.

    Returns:
        The path inside the file and the path of the owning reference prim, or ``None`` when no reference
        target owns the prim.
    """
    if target is None:
        return None
    owners = [
        reference_target
        for reference_target in target.reference_targets
        if prim_path.HasPrefix(Sdf.Path(reference_target.owner_prim_path))
    ]
    if not owners:
        return None
    reference_target = max(owners, key=lambda item: len(item.owner_prim_path))
    owner_path = Sdf.Path(reference_target.owner_prim_path)
    reference = reference_target.source_reference
    if reference is not None and not reference.primPath.isEmpty:
        root = reference.primPath
    else:
        default_prim = file_stage.GetDefaultPrim()
        root = default_prim.GetPath() if default_prim and default_prim.IsValid() else Sdf.Path.absoluteRootPath
    if prim_path == owner_path:
        return root, owner_path
    return root.AppendPath(str(prim_path.MakeRelativePath(owner_path))), owner_path


def _collect_selected_meshes(
    stage: Usd.Stage, file_stage: Usd.Stage, prim_paths: tuple[str, ...], target: AssetReplaceApplyTarget | None
) -> tuple[list[dict[str, Any]], str | None]:
    """Build the job entries for selected project prims.

    A mesh that is already a cutout records the model it was made from; that model is converted again instead
    of the cutout, so repeated runs never cut a cutout. Otherwise the material is read from the project stage so
    user overrides compose in: a capture owner (any owner that is not a Remix reference prim) gets a snapshot of
    it because capture materials live outside the model file, while a replacement keeps the materials of its
    file, where overrides under its reference prim still apply after the swap.

    Args:
        stage: Project stage.
        file_stage: Stage of the model file.
        prim_paths: Selected prim paths.
        target: References that compose the prims.

    Returns:
        Serializable mesh entries, and the original model to read them from when the selected meshes are
        cutouts.
    """
    entries = []
    origin_url = None
    origin_stage = None
    for prim in _selected_meshes(stage, prim_paths):
        mapped = _file_prim_path(prim.GetPath(), target, file_stage)
        if mapped is None:
            continue
        file_path, owner_path = mapped
        file_prim = file_stage.GetPrimAtPath(file_path)
        if not file_prim or not file_prim.IsA(UsdGeom.Mesh):
            continue
        origin = read_origin(file_prim)
        if origin is None:
            material = get_bound_material(prim)
            texture = get_diffuse_texture_path(material) if material else None
            if not texture:
                continue
            is_capture = not _is_remix_reference(stage, owner_path)
            entries.append(
                {
                    PRIM_PATH_KEY: str(file_path),
                    TEXTURE_KEY: texture,
                    MATERIAL_KEY: snapshot_material(material) if is_capture else None,
                    MATERIAL_PRIM_KEY: str(material.GetPath()) if is_capture else None,
                }
            )
            continue
        source_file, source_prim, material_prim = origin
        if origin_stage is None:
            origin_stage = Usd.Stage.Open(source_file)
            origin_url = source_file if origin_stage else None
        if origin_stage is None or source_file != origin_url:
            continue
        mesh_prim = origin_stage.GetPrimAtPath(source_prim)
        if not is_convertible_mesh(mesh_prim):
            continue
        material_owner = stage.GetPrimAtPath(material_prim) if material_prim else None
        material = (
            UsdShade.Material(material_owner)
            if material_owner and material_owner.IsA(UsdShade.Material)
            else get_bound_material(prim if material_prim else mesh_prim)
        )
        texture = get_diffuse_texture_path(material) if material else None
        if not texture:
            continue
        entries.append(
            {
                PRIM_PATH_KEY: source_prim,
                TEXTURE_KEY: texture,
                MATERIAL_KEY: snapshot_material(material) if material_prim else None,
                MATERIAL_PRIM_KEY: str(material.GetPath()) if material_prim else None,
            }
        )
    return entries, origin_url


def _selected_meshes(stage: Usd.Stage, prim_paths: tuple[str, ...]) -> list[Usd.Prim]:
    """Expand the selection to its convertible meshes, each listed once.

    Args:
        stage: Project stage.
        prim_paths: Selected prim paths: meshes, or asset and reference prims that hold meshes.

    Returns:
        The selected meshes and every mesh below a selected non-mesh prim, in selection order.
    """
    meshes: dict[Sdf.Path, Usd.Prim] = {}
    for path in prim_paths:
        prim = stage.GetPrimAtPath(path)
        if not prim:
            continue
        candidates = [prim] if prim.IsA(UsdGeom.Mesh) else Usd.PrimRange(prim)
        for candidate in candidates:
            if is_convertible_mesh(candidate):
                meshes.setdefault(candidate.GetPath(), candidate)
    return list(meshes.values())


def _is_remix_reference(stage: Usd.Stage, prim_path: Sdf.Path) -> bool:
    """Return whether a prim is a reference prim the toolkit created for a replacement.

    Args:
        stage: Project stage.
        prim_path: Path of the owning reference prim.

    Returns:
        ``True`` when the prim carries the Remix reference marker.
    """
    prim = stage.GetPrimAtPath(prim_path)
    return bool(prim) and prim.GetAttribute(constants.IS_REMIX_REF_ATTR).Get() is True


def _collect_file_meshes(file_stage: Usd.Stage) -> list[dict[str, Any]]:
    """Build the job entries for every textured mesh of a model file.

    Args:
        file_stage: Stage of the model file.

    Returns:
        Serializable mesh entries.
    """
    entries = []
    for prim in file_stage.Traverse():
        if not is_convertible_mesh(prim):
            continue
        material = get_bound_material(prim)
        texture = get_diffuse_texture_path(material) if material else None
        if texture:
            entries.append({PRIM_PATH_KEY: str(prim.GetPath()), TEXTURE_KEY: texture, MATERIAL_KEY: None})
    return entries
