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
from pxr import Sdf, Usd, UsdSkel, Vt


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

    def apply(self, joint_map: list[int]):
        """Apply the remapping to the bound prim"""
        self._author_remapped_joints(joint_map)
        self._author_remapped_joint_indices(joint_map)
        self._clear_skel_joints_attr()


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
