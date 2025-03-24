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

from typing import Any, Iterable, TypedDict

import carb
import omni.kit.commands
import omni.kit.undo
import omni.usd
from omni.kit.usd_undo import UsdEditTargetUndo
from omni.usd.commands import remove_prim_spec as _remove_prim_spec
from pxr import Sdf, Usd, UsdGeom


class SetDefaultPrimCommand(omni.kit.commands.Command):
    """
    Sets a prim to be the default prim

    Args:
        prim_path (str): Path of the prim to be set as the default prim.
    """

    def __init__(self, prim_path: str, context_name: str = None, stage: Usd.Stage = None):
        self._prim_path = prim_path
        self._stage = stage or omni.usd.get_context(context_name or "").get_stage()
        self._old_default_prim_path = None

    def do(self):
        new_default_prim = self._stage.GetPrimAtPath(self._prim_path)
        if not new_default_prim:
            return

        if self._stage.HasDefaultPrim():
            self._old_default_prim_path = self._stage.GetDefaultPrim().GetPath()

        self._stage.SetDefaultPrim(new_default_prim)

    def undo(self):
        if self._old_default_prim_path:
            old_default_prim = self._stage.GetPrimAtPath(self._old_default_prim_path)
            self._stage.SetDefaultPrim(old_default_prim)
        else:
            self._stage.SetDefaultPrim(None)


class AttributeDef(TypedDict):
    name: str
    op: UsdGeom.XformOp
    precision: UsdGeom.XformOp.Precision
    value: Any | None


class SetFluxXFormPrimCommand(omni.kit.commands.Command):
    """
    Set xforms on a prim undoable **Command**.

    Args:
        prim_path (str): Prim path.
        attribute_defs (AttributeDef): Desired attributes
        context_name (str): Usd context name to run the command on.
        stage (Usd.Stage): Stage to operate. Optional.
    """

    def __init__(
        self,
        prim_path: str,
        attribute_defs: list[AttributeDef],
        context_name: str,
        stage: Usd.Stage = None,
    ):
        self._attribute_defs = attribute_defs
        self._context_name = context_name
        self._stage = stage or omni.usd.get_context(context_name).get_stage()
        self._layer = self._stage.GetEditTarget().GetLayer()
        self._context = omni.usd.get_context(self._context_name)

        self._prim = self._stage.GetPrimAtPath(prim_path)

    def _clean_prims(self, spec: Sdf.Spec):
        """
        Recursively remove unused prim spec from the layer by crawling up spec parents.
        """
        if not spec or spec.properties or spec.nameChildren:
            return
        parent = spec.nameParent
        _remove_prim_spec(self._layer, spec.path)
        self._clean_prims(parent)

    def _delete_from_layer(self, attribute: Usd.Property):
        if not attribute:
            return False
        if omni.usd.is_layer_locked(self._context, self._layer.identifier):
            return False
        prim_spec = self._layer.GetPrimAtPath(attribute.GetPrimPath())
        if prim_spec is None:
            return False
        prop_spec = self._layer.GetPropertyAtPath(attribute.GetPath())
        if not prop_spec:
            return False
        prim_spec.RemoveProperty(prop_spec)
        self._clean_prims(prim_spec)
        return True

    def _create_attributes(self, attr_defs: Iterable[AttributeDef]):
        """
        Create XForm attributes on the prim.

        The provided attr_defs should be the full set of desired attributes. Providing an empty list will delete all
        xform attributes including the 'xformOpOrder'.
        """
        if not self._prim.IsValid():
            carb.log_error(f"{self.__class__.__name__}: {self._prim} is not a valid Usd.Prim.")
            return

        xform_prim = UsdGeom.Xformable(self._prim)

        # If a xform attribute already exists with a specified precision, we want to use that value rather than
        # trying to change it.
        existing_precision: dict[UsdGeom.XformOp, UsdGeom.XformOp.Precision] = {}

        # Delete the existing xform ops.
        for op in xform_prim.GetOrderedXformOps() or []:
            existing_precision[op.GetOpType()] = op.GetPrecision()
            self._delete_from_layer(op.GetAttr())

        # If we've provided new attributes to create, first reset the xform order, otherwise delete the order attribute.
        if attr_defs:
            xform_prim.ClearXformOpOrder()
        else:
            xform_order_attribute = xform_prim.GetXformOpOrderAttr()
            self._delete_from_layer(xform_order_attribute)

        for attr_def in attr_defs:

            carb.log_info(f"{self.__class__.__name__}: Creating attribute {attr_def}")

            precision = existing_precision.get(attr_def["op"], attr_def["precision"])
            xform_prim.AddXformOp(attr_def["op"], precision)

            if attr_def["value"] is not None:
                attr = self._prim.GetAttribute(attr_def["name"])
                attr.Set(attr_def["value"])

    def do(self):
        carb.log_info(f"{self.__class__.__name__}: Creating attributes {self._attribute_defs}")
        self._create_attributes(self._attribute_defs)

    def undo(self):
        carb.log_info(f"{self.__class__.__name__}: Resetting attributes")
        self._create_attributes([])


class RemoveOverrideCommand(omni.kit.commands.Command):
    """
    Will remove override for a given attribute
    and remove any empty overrides on the prim or its children.
    If no attribute is given, then only
    empty overrides will be removed. **Command**.

    Args:
        prim_path (str): Prim path.
        layer (Sdf.Path): Layer to check for overrides
        context_name (str): Usd context name to run the command on.
        stage (Usd.Stage): Stage to operate. Optional.
        attribute (Usd.Attribute): Attribute to remove. Optional
        check_up_to_prim (str): Prim to stop check. Optional
    """

    def __init__(
        self,
        prim_path: str,
        layer: Sdf.Path,
        context_name: str,
        stage: Usd.Stage = None,
        attribute: Usd.Attribute = None,
        check_up_to_prim: str = None,
    ):
        self._context_name = context_name
        self._stage = stage or omni.usd.get_context(context_name).get_stage()

        self._prim = self._stage.GetPrimAtPath(prim_path)
        if check_up_to_prim:
            self._check_up_to_prim = self._stage.GetPrimAtPath(check_up_to_prim)
        else:
            self._check_up_to_prim = None
        self._layer = layer
        self._attribute = attribute

        self._edit_target_undo = None

    def _has_attribute_override(self, prim: Usd.Prim) -> bool:
        try:
            attrs = prim.GetAttributes()
        except RuntimeError:
            return False
        for attr in attrs:
            stack = attr.GetPropertyStack(Usd.TimeCode.Default())
            for item in stack:
                if item.layer.identifier == self._layer.identifier:
                    return True
        return False

    def _has_non_empty_child_overrides(self, prim: Usd.Prim, seen: set = None) -> bool:
        # If there are no prims to work on, return.
        if not prim.IsValid():
            return False
        children = prim.GetChildren()

        for child in children:  # Noqa SIM110
            if seen is None or child not in seen:
                if self._has_attribute_override(child):
                    return True
                val = self._has_non_empty_child_overrides(child, seen=seen)
                if val:
                    return True
        return False

    def _remove_prim_spec(self):
        omni.kit.commands.execute(
            "RemovePrimSpecCommand",
            layer_identifier=self._layer.identifier,
            prim_spec_path=self._prim.GetPath(),
            usd_context=self._context_name,
        )

    def _remove_overrides_recursive(self, prim: Usd.Prim, seen: set = None):
        # Return if there's no prim to work on
        if not prim:
            return

        if seen is None:
            seen = set()
            seen.add(prim)

        # If there is a prim given to check to, don't go past it
        if self._check_up_to_prim and prim == self._check_up_to_prim:
            return

        any_overrides = self._has_non_empty_child_overrides(prim, seen=seen)
        if not any_overrides and not self._has_attribute_override(prim):
            self._remove_prim_spec()
            # In case we hit the end of the line.
            try:
                parent = prim.GetParent()
            except RuntimeError:
                carb.log_info("Reached the end of prim tree for override check.")
                parent = None

            self._remove_overrides_recursive(parent, seen=seen)

    def _remove_attribute(self):
        with Sdf.ChangeBlock():
            prim_spec = self._layer.GetPrimAtPath(self._attribute.GetPrimPath())
            if prim_spec is None:
                return

            prop_spec = self._layer.GetPropertyAtPath(self._attribute.GetPath())
            if not prop_spec:
                return

            edit_target = self._stage.GetEditTargetForLocalLayer(self._layer)
            edit_target = edit_target.ComposeOver(self._stage.GetEditTarget())
            self._edit_target_undo = UsdEditTargetUndo(edit_target)
            self._edit_target_undo.reserve(prop_spec.path)
            prim_spec.RemoveProperty(prop_spec)

    def do(self):
        carb.log_info(f"{self.__class__.__name__}: Removing empty overrides for {self._prim.GetPath()}")
        # Only delete properties on unlocked layers
        if omni.usd.is_layer_locked(omni.usd.get_context(self._context_name), self._layer.identifier):
            carb.log_info(f"{self.__class__.__name__}: Layer is locked for {self._prim.GetPath()}")
            return

        with omni.kit.undo.group():
            if self._attribute:
                self._remove_attribute()
            self._remove_overrides_recursive(self._prim)

    def undo(self):
        carb.log_info(f"{self.__class__.__name__}: Resetting attribute")
        with Sdf.ChangeBlock():
            if self._edit_target_undo:
                self._edit_target_undo.undo()


class SetVisibilitySelectedPrimsCommand(omni.kit.commands.Command):
    """
    Sets the visibility of the selected primitives.
    """

    def __init__(self, selected_paths: list[str], value: bool, context_name: str = ""):
        """
        Args:
            selected_paths (list[str]): A list of prim paths to set the visibility.
            value (bool): The visibility value to set.
            context_name (str): The context name to get the stage from.
        """

        self._timeline = omni.timeline.get_timeline_interface()
        self._stage = omni.usd.get_context(context_name).get_stage()
        self._selected_paths = [Sdf.Path(path) for path in selected_paths]
        self._selected_paths = Sdf.Path.RemoveDescendentPaths(self._selected_paths)
        self._value = value
        self._previous_visibility = {}
        self._action_taken = {}
        self._current_time = None

    def _get_prim_visibility(self, prim: Usd.Prim, time: float):
        imageable = UsdGeom.Imageable(prim)
        visibility_attr = imageable.GetVisibilityAttr()

        time_sampled = visibility_attr.GetNumTimeSamples() > 1
        if time_sampled:
            curr_time_code = time * self._stage.GetTimeCodesPerSecond()
        else:
            curr_time_code = Usd.TimeCode.Default()

        return imageable.ComputeVisibility(curr_time_code)

    def _toggle_visibility(self, undo: bool):
        if not undo:
            self._current_time = self._timeline.get_current_time()

        for selected_path in self._selected_paths:
            if undo and not self._action_taken.get(selected_path):
                continue

            selected_prim = self._stage.GetPrimAtPath(selected_path)
            if not selected_prim:
                continue

            if not undo:
                # It needs to save parent visibility as toggling visibility may influence parents.
                prefixes = selected_path.GetPrefixes()[:-1]
                for path in prefixes:
                    parent = self._stage.GetPrimAtPath(path)
                    if not parent:
                        break

                    visibility = self._get_prim_visibility(parent, self._current_time)
                    if visibility != UsdGeom.Tokens.inherited:
                        self._previous_visibility[parent.GetPath()] = visibility
                        break

            previous_visibility = self._get_prim_visibility(selected_prim, self._current_time)
            target_visibility = self._value if not undo else not self._value
            imageable = UsdGeom.Imageable(selected_prim)
            if target_visibility:
                imageable.MakeVisible()
            else:
                imageable.MakeInvisible()

            self._action_taken[selected_path] = previous_visibility != self._get_prim_visibility(
                selected_prim, self._current_time
            )

        if undo:
            for path, visibility in self._previous_visibility.items():
                prim = self._stage.GetPrimAtPath(path)
                if not prim:
                    continue
                imageable = UsdGeom.Imageable(prim)

                if visibility == UsdGeom.Tokens.visible:
                    imageable.MakeVisible()
                if visibility == UsdGeom.Tokens.invisible:
                    imageable.MakeInvisible()

    def do(self):
        self._toggle_visibility(False)

    def undo(self):
        self._toggle_visibility(True)


omni.kit.commands.register_all_commands_in_module(__name__)
