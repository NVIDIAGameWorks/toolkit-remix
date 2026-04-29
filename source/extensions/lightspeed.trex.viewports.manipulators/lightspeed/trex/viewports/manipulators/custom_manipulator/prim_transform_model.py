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

import types

import omni.kit.undo
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from omni.flux.utils.common.interactive_usd_notices import begin_interaction as _begin_interaction
from omni.flux.utils.common.interactive_usd_notices import end_interaction as _end_interaction
from omni.kit.manipulator.prim.core.model import PrimTransformModel as _PrimTransformModel


def on_ended_transform(self):
    """Ends the transform operation."""

    with omni.kit.undo.group():
        for tag, data in self._transform_data_map.items():
            self.get_data_accessor(tag).on_ended_transform(
                (
                    self._model.get_path_redirect()
                    if self._model.get_usd_context_name() == _TrexContexts.STAGE_CRAFT.value
                    else data.paths
                ),
                [],
                data.new_translations,
                data.new_rotation_eulers,
                data.new_rotation_orders,
                data.new_scales,
                data.old_translations,
                data.old_rotation_eulers,
                data.old_rotation_orders,
                data.old_scales,
            )


def do_transform_selected_prims(self):
    """Applies the current transform to selected prims."""

    for tag, data in self._transform_data_map.items():
        self.get_data_accessor(tag).do_transform_selected_prims(
            (
                self._model.get_path_redirect()
                if self._model.get_usd_context_name() == _TrexContexts.STAGE_CRAFT.value
                else data.paths
            ),
            [],
            data.new_translations,
            data.new_rotation_eulers,
            data.new_rotation_orders,
            data.new_scales,
        )


def do_transform_all_selected_prims_to_manipulator_pivot(
    self,
    paths: list,
    new_translations: list[float],
    new_rotation_eulers: list[float],
    new_rotation_orders: list[int],
    new_scales: list[float],
):
    """Applies the manipulator-pivot transform to selected prims.

    Args:
        paths: Paths selected by the manipulator model.
        new_translations: New translations to author.
        new_rotation_eulers: New Euler rotations to author.
        new_rotation_orders: New rotation orders to author.
        new_scales: New scales to author.
    """

    self.do_transform_all_selected_prims_to_manipulator_pivot_original(
        (
            self._model.get_path_redirect()
            if self._model.get_usd_context_name() == _TrexContexts.STAGE_CRAFT.value
            else paths
        ),
        new_translations,
        new_rotation_eulers,
        new_rotation_orders,
        new_scales,
    )


class PrimTransformModel(_PrimTransformModel):
    """Prim transform model that groups interactive USD notices during viewport transforms."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__usd_context_name = kwargs["usd_context_name"]
        self.__redirect_paths = []
        self.__notice_interaction = None

        self._data_accessor_selector.on_ended_transform = types.MethodType(
            on_ended_transform, self._data_accessor_selector
        )
        self._data_accessor_selector.do_transform_selected_prims = types.MethodType(
            do_transform_selected_prims, self._data_accessor_selector
        )
        self._data_accessor_selector.do_transform_all_selected_prims_to_manipulator_pivot_original = (
            self._data_accessor_selector.do_transform_all_selected_prims_to_manipulator_pivot
        )
        self._data_accessor_selector.do_transform_all_selected_prims_to_manipulator_pivot = types.MethodType(
            do_transform_all_selected_prims_to_manipulator_pivot, self._data_accessor_selector
        )

    def set_path_redirect(self, paths: list[str]):
        """Set redirected selection paths for Stage Craft transforms.

        Args:
            paths: Paths to use instead of the base manipulator selection.
        """

        self.__redirect_paths = paths

    def get_path_redirect(self):
        """Return redirected selection paths for Stage Craft transforms.

        Returns:
            Paths to use instead of the base manipulator selection.
        """

        return self.__redirect_paths

    def get_usd_context_name(self):
        """Return the USD context name used by this transform model.

        Returns:
            USD context name passed to the model constructor.
        """

        return self.__usd_context_name

    def on_began(self, payload):
        """Start a transform interaction and delegate to the base model.

        Args:
            payload: Manipulator gesture payload from the base model.

        Raises:
            Exception: Re-raises any exception from the base handler after ending the interaction.
        """

        if self.__notice_interaction is not None:
            _end_interaction(self.__notice_interaction)
            self.__notice_interaction = None
        stage = self.usd_context.get_stage()
        self.__notice_interaction = _begin_interaction(stage)
        try:
            super().on_began(payload)
        except Exception:
            _end_interaction(self.__notice_interaction)
            self.__notice_interaction = None
            raise

    def on_ended(self, payload):
        """End a transform interaction and flush deferred notices.

        Args:
            payload: Manipulator gesture payload from the base model.
        """

        try:
            super().on_ended(payload)
        finally:
            _end_interaction(self.__notice_interaction)
            self.__notice_interaction = None

    def on_canceled(self, payload):
        """Cancel a transform interaction and flush deferred notices.

        Args:
            payload: Manipulator gesture payload from the base model.
        """

        try:
            super().on_canceled(payload)
        finally:
            _end_interaction(self.__notice_interaction)
            self.__notice_interaction = None
