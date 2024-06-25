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

from functools import partial
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import omni.kit.commands
import omni.kit.undo
import omni.ui as ui
import omni.usd
from omni.flux.utils.common.utils import get_omni_prims as _get_omni_prims
from pxr import Sdf, UsdGeom
from pydantic import validator

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402

if TYPE_CHECKING:
    from pxr import Usd


class WrapRootPrims(_CheckBaseUSD):
    _CUSTOM_ATTR_NAME = "flux:wrap"

    def __init__(self):
        super().__init__()

        self.__last_run = (None, None)

    class Data(_CheckBaseUSD.Data):
        set_default_prim: bool = True
        wrap_prim_name: Optional[str] = None

        @validator("wrap_prim_name", allow_reuse=True)
        def is_not_empty(cls, v):  # noqa
            """Check that the prim name is not empty"""
            if v and not str(v).strip():
                raise ValueError("The value cannot be empty")
            return v

        @validator("wrap_prim_name", allow_reuse=True)
        def is_valid_prim_path(cls, v):  # noqa
            """Check that the prim name is not empty"""
            if v and not Sdf.Path.IsValidIdentifier(str(v)):
                raise ValueError("The value is not a valid Prim name")
            return v

    name = "WrapRootPrims"
    tooltip = (
        "This plugin will wrap all the root prims into an empty Xform prim and optionally set the wrapper as the "
        "default prim."
    )
    data_type = Data
    display_name = "Wrap Root Prims"

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Checks if the given stage has a default prim.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        stage = omni.usd.get_context(context_plugin_data).get_stage()
        root_prims = self.__get_root_prims(stage)
        # To make sure the root prims were wrapped, verify that the last run was run on the same layer and prim
        success = len(root_prims) == 1 and self.__last_run == (
            stage.GetRootLayer().identifier,
            root_prims[0].GetPath(),
        )

        message = f"Check:\n{'- PASS: Root prims wrapped' if success else '- FAIL: Root prims not wrapped'}\n"
        return success, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Attempts to set a default prim.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        success = True

        self.on_progress(0, "Start", True)

        stage = omni.usd.get_context(context_plugin_data).get_stage()
        root_prims = self.__get_root_prims(stage)
        if not root_prims:
            message += "- SKIP: No root prims were found\n"
            return success, message, None

        with omni.kit.undo.group():
            # Group the prims under a single prim
            omni.kit.commands.execute(
                "GroupPrims",
                prim_paths=[prim.GetPath() for prim in root_prims],
                destructive=False,
                stage=stage,
            )
            # Fetch the newly created group
            root_prims = self.__get_root_prims(stage)
            group_prim = root_prims[0] if root_prims else None
            if group_prim:
                # remove pivot created by the GroupPrims command used above.
                await self._remove_pivot_xformop(context_plugin_data, group_prim)

                if schema_data.wrap_prim_name:
                    from_path = group_prim.GetPath()
                    to_path = omni.usd.get_stage_next_free_path(
                        stage, from_path.ReplaceName(schema_data.wrap_prim_name), False
                    )
                    omni.kit.commands.execute(
                        "MovePrim",
                        path_from=from_path,
                        path_to=to_path,
                        on_move_fn=partial(self.__set_default_prim, schema_data, stage),
                        stage_or_context=stage,
                    )
                else:
                    group_path = group_prim.GetPath()
                    self.__set_default_prim(schema_data, stage, group_path, group_path)

                root_prims = self.__get_root_prims(stage)
                group_prim = root_prims[0] if root_prims else None
                progress_message = f"PASS: Created new wrapper prim `{group_prim.GetPath()}` from PseudoRoot"
            else:
                progress_message = "FAIL: Unable to create a wrapper prim from PseudoRoot"
                success = False

        message += f"- {progress_message}\n"

        # Store the root layer and root prim
        self.__last_run = (stage.GetRootLayer().identifier, group_prim.GetPath() if group_prim else None)

        return success, message, None

    @omni.usd.handle_exception
    async def _remove_pivot_xformop(self, context_name, prim):
        xform = UsdGeom.Xformable(prim)
        xform_ops_attr = xform.GetXformOpOrderAttr()
        xform_ops = xform_ops_attr.Get()
        new_xform_ops = []
        for op in xform_ops:
            if op.endswith(":pivot"):
                omni.kit.commands.execute(
                    "RemoveProperty",
                    prop_path=prim.GetAttribute(op).GetPath(),
                    usd_context_name=context_name,
                )
            else:
                new_xform_ops.append(op)

        omni.kit.commands.execute(
            "ChangePropertyCommand",
            prop_path=xform_ops_attr.GetPath(),
            value=new_xform_ops,
            prev=None,
            usd_context_name=context_name,
        )

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")

    def __get_root_prims(self, stage: "Usd.Stage") -> List["Sdf.Path"]:
        root_prims = []

        session_layer = stage.GetSessionLayer()
        for prim in stage.GetPseudoRoot().GetChildren():
            # Get all the root prims except for Session Layer prims
            if session_layer.GetPrimAtPath(prim.GetPath()) or prim.GetPath() in _get_omni_prims():
                continue
            root_prims.append(prim)

        return root_prims

    def __set_default_prim(self, schema_data: Data, stage: Any, _: Sdf.Path, target_path: Sdf.Path):
        if schema_data.set_default_prim:
            # Set the group as the default prim
            omni.kit.commands.execute("SetDefaultPrim", prim_path=target_path, stage=stage)
