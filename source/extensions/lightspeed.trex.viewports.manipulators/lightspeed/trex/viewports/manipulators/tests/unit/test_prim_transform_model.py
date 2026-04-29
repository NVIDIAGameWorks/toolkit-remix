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

from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

import omni.kit.test

from ...custom_manipulator import prim_transform_model as _prim_transform_model_module
from ...custom_manipulator.prim_transform_model import PrimTransformModel


class TestPrimTransformModel(omni.kit.test.AsyncTestCase):
    @staticmethod
    def _make_model(handle=None):
        model = PrimTransformModel.__new__(PrimTransformModel)
        model._PrimTransformModel__notice_interaction = handle
        model._PrimTransformModel__usd_context_name = ""
        model._PrimTransformModel__redirect_paths = []
        return model

    async def test_on_began_starts_interaction_before_base_handler(self):
        # Arrange
        model = self._make_model()
        payload = object()
        stage = object()
        handle = object()
        handle_seen_by_base_handler = []
        usd_context = SimpleNamespace(get_stage=Mock(return_value=stage))

        def _base_on_began(instance, _begun_payload):
            handle_seen_by_base_handler.append(instance._PrimTransformModel__notice_interaction)

        with (
            patch.object(
                _prim_transform_model_module._PrimTransformModel,
                "on_began",
                autospec=True,
                side_effect=_base_on_began,
            ) as mock_base_on_began,
            patch.object(PrimTransformModel, "usd_context", new_callable=PropertyMock, return_value=usd_context),
            patch.object(
                _prim_transform_model_module,
                "_begin_interaction",
                return_value=handle,
            ) as mock_begin_interaction,
        ):
            # Act
            model.on_began(payload)

        # Assert
        mock_begin_interaction.assert_called_once_with(stage)
        mock_base_on_began.assert_called_once_with(model, payload)
        self.assertEqual(handle_seen_by_base_handler, [handle])
        self.assertIs(model._PrimTransformModel__notice_interaction, handle)

    async def test_on_began_closes_existing_interaction_before_starting_new_one(self):
        # Arrange
        previous_handle = object()
        next_handle = object()
        model = self._make_model(handle=previous_handle)
        payload = object()
        stage = object()
        usd_context = SimpleNamespace(get_stage=Mock(return_value=stage))

        with (
            patch.object(
                _prim_transform_model_module._PrimTransformModel,
                "on_began",
                autospec=True,
            ) as mock_base_on_began,
            patch.object(PrimTransformModel, "usd_context", new_callable=PropertyMock, return_value=usd_context),
            patch.object(
                _prim_transform_model_module,
                "_begin_interaction",
                return_value=next_handle,
            ) as mock_begin_interaction,
            patch.object(_prim_transform_model_module, "_end_interaction") as mock_end_interaction,
        ):
            # Act
            model.on_began(payload)

        # Assert
        mock_end_interaction.assert_called_once_with(previous_handle)
        mock_begin_interaction.assert_called_once_with(stage)
        mock_base_on_began.assert_called_once_with(model, payload)
        self.assertIs(model._PrimTransformModel__notice_interaction, next_handle)

    async def test_on_began_ends_interaction_if_base_handler_raises(self):
        # Arrange
        model = self._make_model()
        payload = object()
        stage = object()
        handle = object()
        usd_context = SimpleNamespace(get_stage=Mock(return_value=stage))

        with (
            patch.object(
                _prim_transform_model_module._PrimTransformModel,
                "on_began",
                autospec=True,
                side_effect=RuntimeError("boom"),
            ),
            patch.object(PrimTransformModel, "usd_context", new_callable=PropertyMock, return_value=usd_context),
            patch.object(
                _prim_transform_model_module,
                "_begin_interaction",
                return_value=handle,
            ),
            patch.object(_prim_transform_model_module, "_end_interaction") as mock_end_interaction,
        ):
            # Act
            with self.assertRaises(RuntimeError):
                model.on_began(payload)

        # Assert
        mock_end_interaction.assert_called_once_with(handle)
        self.assertIsNone(model._PrimTransformModel__notice_interaction)

    async def test_on_ended_finishes_interaction_after_base_handler(self):
        # Arrange
        handle = object()
        model = self._make_model(handle=handle)
        payload = object()

        with (
            patch.object(
                _prim_transform_model_module._PrimTransformModel,
                "on_ended",
                autospec=True,
            ) as mock_base_on_ended,
            patch.object(_prim_transform_model_module, "_end_interaction") as mock_end_interaction,
        ):
            # Act
            model.on_ended(payload)

        # Assert
        mock_base_on_ended.assert_called_once_with(model, payload)
        mock_end_interaction.assert_called_once_with(handle)
        self.assertIsNone(model._PrimTransformModel__notice_interaction)

    async def test_on_canceled_finishes_interaction_after_base_handler(self):
        # Arrange
        handle = object()
        model = self._make_model(handle=handle)
        payload = object()

        with (
            patch.object(
                _prim_transform_model_module._PrimTransformModel,
                "on_canceled",
                autospec=True,
            ) as mock_base_on_canceled,
            patch.object(_prim_transform_model_module, "_end_interaction") as mock_end_interaction,
        ):
            # Act
            model.on_canceled(payload)

        # Assert
        mock_base_on_canceled.assert_called_once_with(model, payload)
        mock_end_interaction.assert_called_once_with(handle)
        self.assertIsNone(model._PrimTransformModel__notice_interaction)
