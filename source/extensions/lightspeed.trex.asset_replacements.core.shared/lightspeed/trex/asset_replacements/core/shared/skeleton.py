"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import carb
import omni.kit
import omni.kit.undo
from pxr import Gf, Sdf, Usd, UsdSkel, Vt

# Only large uniform bind scales are treated as unit-conversion repairs. Smaller non-1 scales can be
# intentional authored sizing and should stay intact.
_MIN_BIND_SCALE_TO_NORMALIZE = 10.0
_UNIFORM_SCALE_TOLERANCE = 0.01


class SkeletonAutoRemappingError(Exception):
    """Skeleton replacement does not have the proper attributes to be remapped as is."""


class SkeletonDefinitionError(Exception):
    """Missing part of SkelRoot, Skeleton or Binding"""


def path_names_only(paths: list[str]) -> list[str]:
    """Utility to reduce a list of paths to a list of the last part of each path"""
    return [path.split("/")[-1] for path in paths]


def clear_skel_root_type(prim: Usd.Prim) -> bool:
    """Override a prim type to a Xform if it's a SkelRoot"""
    # Nested SkelRoot prims cause problems, so override their type to XForm
    root_api = UsdSkel.Root(prim)
    if root_api:
        omni.kit.commands.execute(
            "SetPrimTypeName",
            prim=prim,
            type_name="Xform",
        )
        return True
    return False


def author_binding_to_skel(binding_api: UsdSkel.BindingAPI, skeleton_prim: Usd.Prim):
    """Author the binding to a skeleton using undoable omni command"""
    # Force the mesh to bind to the captured skeleton
    omni.kit.commands.execute(
        "SetRelationshipTargetsCommand",
        relationship=binding_api.GetSkeletonRel(),
        targets=[skeleton_prim.GetPath()],
    )


def _has_replacement_reference_ancestor(prim: Usd.Prim) -> bool:
    return bool(_get_replacement_reference_root(prim))


def _get_replacement_reference_root(prim: Usd.Prim) -> Usd.Prim | None:
    stage = prim.GetStage()
    path = prim.GetPath().GetParentPath()
    while path and path != Sdf.Path.absoluteRootPath:
        if path.name.startswith("ref_"):
            ref_prim = stage.GetPrimAtPath(path)
            return ref_prim if ref_prim and ref_prim.IsValid() else None
        path = path.GetParentPath()
    return None


def _targets_captured_skeleton(binding_api: UsdSkel.BindingAPI) -> bool:
    skeleton_rel = binding_api.GetSkeletonRel()
    if not skeleton_rel:
        return False
    for target in skeleton_rel.GetTargets():
        target_text = str(target)
        if target_text.startswith("/RootNode/meshes/") and target_text.endswith("/skel"):
            return True
    return False


def _coerce_matrix4d(value) -> Gf.Matrix4d | None:
    if value is None:
        return None
    if isinstance(value, Gf.Matrix4d):
        return value
    try:
        return Gf.Matrix4d(*value)
    except (TypeError, ValueError):
        return None


def _matrix_row_scale(matrix: Gf.Matrix4d, row: int) -> float:
    return sum(float(matrix[row][column]) ** 2 for column in range(3)) ** 0.5


def _uniform_basis_scale(matrix: Gf.Matrix4d) -> float | None:
    scales = [_matrix_row_scale(matrix, row) for row in range(3)]
    if any(scale <= 0.0 for scale in scales):
        return None
    scale = sum(scales) / len(scales)
    if scale < _MIN_BIND_SCALE_TO_NORMALIZE:
        return None
    if any(abs(axis_scale - scale) > scale * _UNIFORM_SCALE_TOLERANCE for axis_scale in scales):
        return None
    return scale


def _matrix_without_uniform_basis_scale(
    matrix: Gf.Matrix4d, scale: float, normalize_translation: bool = False
) -> Gf.Matrix4d:
    rows = [[float(matrix[row][column]) for column in range(4)] for row in range(4)]
    for row in range(3):
        for column in range(3):
            rows[row][column] /= scale
    if normalize_translation:
        for column in range(3):
            rows[3][column] /= scale
    return Gf.Matrix4d(
        rows[0][0],
        rows[0][1],
        rows[0][2],
        rows[0][3],
        rows[1][0],
        rows[1][1],
        rows[1][2],
        rows[1][3],
        rows[2][0],
        rows[2][1],
        rows[2][2],
        rows[2][3],
        rows[3][0],
        rows[3][1],
        rows[3][2],
        rows[3][3],
    )


def _should_normalize_geom_bind_scale(prim: Usd.Prim, binding_api: UsdSkel.BindingAPI) -> bool:
    return _has_replacement_reference_ancestor(prim) and _targets_captured_skeleton(binding_api)


def _get_matching_uniform_basis_scale(matrix: Gf.Matrix4d, expected_scale: float) -> float | None:
    scale = _uniform_basis_scale(matrix)
    if scale is None:
        return None
    if abs(scale - expected_scale) > expected_scale * _UNIFORM_SCALE_TOLERANCE:
        return None
    return scale


def _matrix_array_with_normalized_uniform_basis(
    value, expected_scale: float, normalize_translation: bool
) -> list[Gf.Matrix4d] | None:
    if not value:
        return None

    changed = False
    matrices = []
    for matrix_value in value:
        matrix = _coerce_matrix4d(matrix_value)
        if matrix is None:
            return None

        matrix_scale = _get_matching_uniform_basis_scale(matrix, expected_scale)
        if matrix_scale is None:
            matrices.append(matrix)
            continue

        matrices.append(_matrix_without_uniform_basis_scale(matrix, matrix_scale, normalize_translation))
        changed = True

    return matrices if changed else None


def _active_binding_targets_skeleton(root_prim: Usd.Prim, skeleton_path: Sdf.Path) -> bool:
    for prim in Usd.PrimRange(root_prim, Usd.PrimAllPrimsPredicate):
        binding_api = UsdSkel.BindingAPI(prim)
        if not binding_api:
            continue
        skeleton_rel = binding_api.GetSkeletonRel()
        if skeleton_rel and skeleton_path in skeleton_rel.GetTargets():
            return True
    return False


def _get_nearby_replacement_skeletons(prim: Usd.Prim) -> list[Usd.Prim]:
    ref_root = _get_replacement_reference_root(prim)
    if not ref_root:
        return []

    ancestor = prim.GetParent()
    while ancestor and ancestor.IsValid():
        skeletons = [
            skeleton_prim
            for skeleton_prim in Usd.PrimRange(ancestor, Usd.PrimAllPrimsPredicate)
            if UsdSkel.Skeleton(skeleton_prim)
        ]
        if skeletons:
            return skeletons
        if ancestor == ref_root:
            break
        ancestor = ancestor.GetParent()
    return []


def _collect_skeleton_transform_repairs(
    repairs: list[tuple[Usd.Attribute, object, float, str]],
    seen_attr_paths: set[Sdf.Path],
    prim: Usd.Prim,
    scale: float,
):
    for skeleton_prim in _get_nearby_replacement_skeletons(prim):
        skeleton_path = skeleton_prim.GetPath()
        if _active_binding_targets_skeleton(skeleton_prim.GetParent(), skeleton_path):
            continue

        skeleton = UsdSkel.Skeleton(skeleton_prim)
        for attr, normalize_translation in (
            (skeleton.GetRestTransformsAttr(), False),
            (skeleton.GetBindTransformsAttr(), True),
        ):
            if not attr:
                continue
            attr_path = attr.GetPath()
            if attr_path in seen_attr_paths:
                continue

            matrices = _matrix_array_with_normalized_uniform_basis(attr.Get(), scale, normalize_translation)
            if matrices is None:
                continue

            repairs.append((attr, matrices, scale, str(skeleton_path)))
            seen_attr_paths.add(attr_path)


def _get_scale_repair_target_layer(stage: Usd.Stage, target_layer: Sdf.Layer | None = None) -> Sdf.Layer | None:
    if not stage:
        return None

    session_layer = stage.GetSessionLayer()
    if target_layer and target_layer != session_layer:
        return target_layer

    edit_layer = stage.GetEditTarget().GetLayer()
    if edit_layer and edit_layer != session_layer:
        return edit_layer

    root_layer = stage.GetRootLayer()
    if root_layer and root_layer != session_layer:
        return root_layer

    return None


def _author_scale_repairs(
    stage: Usd.Stage, repairs: list[tuple[Usd.Attribute, object, float, str]], target_layer: Sdf.Layer | None = None
) -> int:
    authoring_layer = _get_scale_repair_target_layer(stage, target_layer)
    if not authoring_layer:
        return 0

    repairs_applied = 0
    with Usd.EditContext(stage, authoring_layer), omni.kit.undo.group():
        for attr, value, scale, prim_path in repairs:
            if not attr:
                continue
            omni.kit.commands.execute(
                "ChangePropertyCommand",
                usd_context_name=stage,
                prop_path=str(attr.GetPath()),
                value=value,
                prev=attr.Get(),
                type_to_create_if_not_exist=attr.GetTypeName(),
                is_custom=attr.IsCustom(),
                variability=attr.GetVariability(),
            )
            repairs_applied += 1
            carb.log_info(
                f"Repaired {scale:.4g}x skinned replacement {attr.GetName()} scale for Toolkit view: {prim_path}"
            )
    return repairs_applied


def repair_skinned_replacement_scale(bound_prim: Usd.Prim, target_layer: Sdf.Layer | None = None) -> int:
    """Normalize large replacement skel scales for one bound replacement mesh.

    Runtime remapping evaluates these meshes against the captured skeleton. Toolkit USD skinning still applies the
    replacement asset's authored bind-space unit scale, so remapped meshes and their source skeletons can appear huge.
    The repair is scoped to a selected replacement binding and authored to the current non-session edit target.
    """
    if not bound_prim or not bound_prim.IsValid():
        return 0

    stage = bound_prim.GetStage()
    if not stage:
        return 0

    binding_api = UsdSkel.BindingAPI(bound_prim)
    if not binding_api or not _should_normalize_geom_bind_scale(bound_prim, binding_api):
        return 0

    geom_bind_attr = binding_api.GetGeomBindTransformAttr()
    matrix = _coerce_matrix4d(geom_bind_attr.Get() if geom_bind_attr else None)
    if matrix is None:
        return 0

    scale = _uniform_basis_scale(matrix)
    if scale is None:
        return 0

    repairs = [
        (
            geom_bind_attr,
            _matrix_without_uniform_basis_scale(matrix, scale),
            scale,
            str(bound_prim.GetPath()),
        )
    ]
    seen_attr_paths = {geom_bind_attr.GetPath()}
    _collect_skeleton_transform_repairs(repairs, seen_attr_paths, bound_prim, scale)
    return _author_scale_repairs(stage, repairs, target_layer=target_layer)


class SkeletonReplacementBinding:
    REMIX_JOINT_ATTR = "skel:remix_joints"
    JOINT_ATTR = "skel:joints"  # canonical USD attribute name on original asset

    def __init__(self, skel_root: Usd.Prim, bound_prim: Usd.Prim):
        self._stage = skel_root.GetStage()
        # the root of this asset which is a skel root for captured skeletons
        self._skel_root_prim = skel_root
        self._skel_root = UsdSkel.Root(self._skel_root_prim)
        if not self._skel_root:
            raise SkeletonDefinitionError(f"Skeleton root is not valid: {self._skel_root}")
        # capture will always have a skeleton named skel
        self._captured_skeleton_prim = skel_root.GetChild("skel")
        if not self._captured_skeleton_prim:
            raise SkeletonDefinitionError(
                f"Captured skeleton not found: {self._skel_root_prim.GetPath().AppendChild('skel')}"
            )
        self._captured_skeleton: UsdSkel.Skeleton = UsdSkel.Skeleton(self._captured_skeleton_prim)
        self._original_mesh_joint_indices: Vt.IntArray | None = None

        self._bound_prim = bound_prim
        self._binding_api = UsdSkel.BindingAPI(bound_prim)
        if not self._binding_api:
            raise SkeletonDefinitionError(f"No skel binding found under: {bound_prim.GetPath()}")

        # find the lower strength "original" binding and open a stage loading that prim
        self._replacement_stage = None
        for spec in reversed(self._bound_prim.GetPrimStack()):
            self._replacement_stage = Usd.Stage.Open(spec.layer, self._stage.GetPathResolverContext())
            self._orig_bound_prim = self._replacement_stage.GetPrimAtPath(spec.path)
            self._orig_binding_api = UsdSkel.BindingAPI(self._orig_bound_prim)
            if not self._orig_binding_api:
                continue
            self._orig_skeleton = self._orig_binding_api.GetSkeleton()
            if not self._orig_skeleton:
                continue
            if self._orig_bound_prim.GetPath() == self._bound_prim.GetPath():
                carb.log_warn(f"Only one skel binding found on {self._bound_prim.GetPath()}.")
            break
        else:
            # If we don't have a replacement, we can show a remapping from the same skel.
            carb.log_warn(f"Only one skel binding found on {self._bound_prim.GetPath()}.")
            self._orig_skeleton = self._captured_skeleton
            self._orig_binding_api = self._binding_api
            self._orig_bound_prim = self._bound_prim

    @property
    def bound_prim(self) -> Usd.Prim:
        return self._bound_prim

    @property
    def captured_skeleton(self) -> UsdSkel.Skeleton:
        return self._captured_skeleton

    @property
    def original_skeleton(self) -> UsdSkel.Skeleton:
        return self._orig_skeleton

    def get_captured_joints(self) -> list[str]:
        """Return the list of legacy joints in the skeleton that was captured in the runtime"""
        return list(self._captured_skeleton.GetJointsAttr().Get())

    def get_mesh_joints(self) -> list[str]:
        """Return the list of joints that were originally bound to the replacement mesh"""
        return list(self._orig_binding_api.GetSkeleton().GetJointsAttr().Get())

    def get_remapped_joints(self) -> list[str]:
        """Return the list of captured joints that will drive the corresponding mesh joints"""
        joint_attr = self._bound_prim.GetAttribute(self.REMIX_JOINT_ATTR)
        if joint_attr:
            value = joint_attr.Get()
            if value:
                return value
        # Initial replacement clears this attribute, so we need to grab pre-cleared value
        joint_attr = self._orig_bound_prim.GetAttribute(self.JOINT_ATTR)
        if joint_attr:
            value = joint_attr.Get()
            if value:
                return value
        return []

    def get_joint_map(self) -> list[int]:
        """Return the authored map from mesh joint list index to captured joint list index"""
        remapped_joints = self.get_remapped_joints()
        captured_joints = list(self.get_captured_joints())
        return [captured_joints.index(j) if j in captured_joints else -1 for j in remapped_joints]

    def get_original_joint_indices(self) -> Vt.IntArray | None:
        """Return the originally bound joint influences on the replacement mesh"""
        if self._original_mesh_joint_indices is not None:
            return self._original_mesh_joint_indices  # only need to read this once
        indices_primvar = self._orig_binding_api.GetJointIndicesPrimvar()
        if indices_primvar:
            self._original_mesh_joint_indices = indices_primvar.Get()
        return self._original_mesh_joint_indices

    def get_joint_indices(self) -> Vt.IntArray | None:
        """Return the new joint influences on the replacement mesh"""
        return self._binding_api.GetJointIndicesAttr().Get()

    @staticmethod
    def generate_joint_map(mesh_joints, captured_joints, fallback=False) -> list[int]:
        """Use heuristics to generate a map from mesh joint list index to captured joint list index"""
        captured_joints_list = list(path_names_only(captured_joints))
        joint_map: list[int] = [-1] * len(mesh_joints)
        try:
            for index, joint_name in enumerate(path_names_only(mesh_joints)):
                joint_map[index] = captured_joints_list.index(joint_name)
        except ValueError as err:
            if fallback:
                # use a naive reordering if no name match was found...
                max_index = len(captured_joints_list) - 1
                joint_map = [min(i, max_index) if j == -1 else j for i, j in zip(range(len(mesh_joints)), joint_map)]
            else:
                carb.log_error(
                    f"Replacement mesh contains joint names that are not in the"
                    " captured skeleton and could not be remapped."
                    f" - Skeleton: {captured_joints}\n"
                    f" - Mesh: {mesh_joints}\n"
                )
                raise SkeletonAutoRemappingError("No valid remapping found using joint names.") from err
        return joint_map

    def _remap_joints(self, joint_map: list[int]) -> list[str]:
        """Produce the new list of driving captured joints from a joint map"""
        skel_joints = self.get_captured_joints()
        return [skel_joints[joint_map[i]] for i in range(len(joint_map))]

    def _author_remapped_joints(self, joint_map: list[int]):
        """Author the new list of driving captured joints on the mesh prim"""
        remap_joints_attr = self._binding_api.GetPrim().GetAttribute(self.REMIX_JOINT_ATTR)
        original_joints = None
        if remap_joints_attr:
            original_joints = remap_joints_attr.Get()

        value = self._remap_joints(joint_map)
        omni.kit.commands.execute(
            "ChangePropertyCommand",
            usd_context_name=self._stage,
            prop_path=remap_joints_attr.GetPath(),
            value=value,
            prev=original_joints,
            type_to_create_if_not_exist=Sdf.ValueTypeNames.TokenArray,
            variability=Sdf.VariabilityUniform,
            is_custom=True,
        )

    def _author_remapped_joint_indices(self, joint_map: list[int]):
        """Author the new joint influences on the mesh prim"""
        indices = self.get_original_joint_indices()
        if not indices or not joint_map:
            return
        remapped_indices = [joint_map[index] for index in indices]
        omni.kit.commands.execute(
            "ChangePropertyCommand",
            usd_context_name=self._stage,
            prop_path=self._binding_api.GetJointIndicesAttr().GetPath(),
            value=remapped_indices,
            prev=indices,
        )
        carb.log_info(f"Joint indices successfully remapped for {self._bound_prim.GetPath()}")

    def _clear_skel_joints_attr(self):
        """Clear the skel:joints attribute on the mesh prim"""
        original_joints = self._binding_api.GetJointsAttr().Get()
        # Set skel:joints property to None.
        omni.kit.commands.execute(
            "ChangePropertyCommand",
            usd_context_name=self._stage,
            prop_path=self._binding_api.GetJointsAttr().GetPath(),
            value=Sdf.ValueBlock(),
            prev=original_joints,
        )

    def repair_scale(self) -> int:
        """Repair large skinned replacement scale on the bound mesh and nearby replacement skeleton."""
        return repair_skinned_replacement_scale(self._bound_prim)

    def apply(self, joint_map: list[int]) -> int:
        """Apply remapping and repair large skinned replacement scale.

        Returns:
            The number of scale repairs applied to the bound prim and nearby replacement skeleton.
        """
        self._author_remapped_joints(joint_map)
        self._author_remapped_joint_indices(joint_map)
        self._clear_skel_joints_attr()
        return self.repair_scale()


class CachedReplacementSkeletons:
    """Container to cache replacement skeletons for performance"""

    def __init__(self):
        self._replacement_skel_models = {}

    def get_skel_replacement(
        self, skel_root: Usd.Prim, replacement_asset_root: Usd.Prim
    ) -> SkeletonReplacementBinding | None:
        try:
            return self._replacement_skel_models[(skel_root, replacement_asset_root)]
        except KeyError:
            return None

    def add_skel_replacement(self, skel_root: Usd.Prim, replacement_asset_root: Usd.Prim):
        skel_replacement = self.get_skel_replacement(skel_root, replacement_asset_root)
        if skel_replacement:
            return skel_replacement

        try:
            skel_replacement = SkeletonReplacementBinding(skel_root, replacement_asset_root)
        except SkeletonDefinitionError:
            return None
        self._replacement_skel_models[(skel_root, replacement_asset_root)] = skel_replacement
        return skel_replacement
