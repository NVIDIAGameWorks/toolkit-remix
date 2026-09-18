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
from unittest.mock import MagicMock, patch

import lightspeed.trex.properties_pane.material.widget.setup_ui as _setup_ui
from lightspeed.trex.properties_pane.material.widget.setup_ui import SetupUI
from omni.kit.test import AsyncTestCase

_MODULE = "lightspeed.trex.properties_pane.material.widget.setup_ui"


def _make_group(name: str, hidden: bool = False):
    name_model = SimpleNamespace(get_value_as_string=lambda: name)
    return SimpleNamespace(can_have_children=True, name_models=[name_model], value_models=[], hidden=hidden)


class TestSetupUI(AsyncTestCase):
    """Verify DLSS Neural Rendering material-group availability handling."""

    def test_constructor_subscribes_to_dlss_neural_rendering_availability_changes(self):
        # Arrange
        settings = MagicMock()
        with (
            patch(f"{_MODULE}.carb.settings.get_settings", return_value=settings),
            patch(f"{_MODULE}.usd.get_context"),
            patch(f"{_MODULE}._AssetReplacementsCore"),
            patch(f"{_MODULE}._MaterialCore"),
            patch.object(SetupUI, "set_external_drag_and_drop"),
            patch.object(SetupUI, "_SetupUI__create_ui"),
        ):
            # Act
            setup = SetupUI("")

            # Assert
            settings.subscribe_to_node_change_events.assert_called_once_with(
                _setup_ui.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE,
                setup._on_dlss_neural_rendering_availability_changed,
            )

    def test_update_dlss_neural_rendering_group_visibility_when_unavailable_hides_supported_group_names(self):
        # Arrange
        settings = MagicMock()
        settings.get.return_value = False
        setup = SetupUI.__new__(SetupUI)
        setup._settings = settings
        legacy_group = _make_group("DLSS Neural Rendering")
        legacy_experimental_group = _make_group("DLSS Neural Rendering [Experimental]")
        experimental_group = _make_group("DLSS 3D-Guided Neural Generation [Experimental]")
        unrelated_group = _make_group("Base Material")

        # Act
        setup._update_dlss_neural_rendering_group_visibility(
            [legacy_group, legacy_experimental_group, experimental_group, unrelated_group]
        )

        # Assert
        self.assertTrue(legacy_group.hidden)
        self.assertTrue(legacy_experimental_group.hidden)
        self.assertTrue(experimental_group.hidden)
        self.assertFalse(unrelated_group.hidden)
        settings.get.assert_called_once_with(_setup_ui.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE)

    def test_update_dlss_neural_rendering_group_visibility_when_available_shows_group(self):
        # Arrange
        settings = MagicMock()
        settings.get.return_value = True
        setup = SetupUI.__new__(SetupUI)
        setup._settings = settings
        group = _make_group("DLSS 3D-Guided Neural Generation [Experimental]", hidden=True)

        # Act
        setup._update_dlss_neural_rendering_group_visibility([group])

        # Assert
        self.assertFalse(group.hidden)
        settings.get.assert_called_once_with(_setup_ui.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE)

    def test_on_dlss_neural_rendering_availability_changed_updates_current_model(self):
        # Arrange
        settings = MagicMock()
        settings.get.return_value = False
        group = _make_group("DLSS 3D-Guided Neural Generation [Experimental]")
        property_model = MagicMock()
        property_model.get_all_items.return_value = [group]
        setup = SetupUI.__new__(SetupUI)
        setup._settings = settings
        setup._material_properties_widget = SimpleNamespace(property_model=property_model)

        # Act
        setup._on_dlss_neural_rendering_availability_changed()

        # Assert
        property_model.get_all_items.assert_called_once_with(include_hidden=True)
        self.assertTrue(group.hidden)

    def test_on_material_refresh_done_applies_current_dlss_neural_rendering_availability(self):
        # Arrange
        settings = MagicMock()
        settings.get.return_value = False
        group = _make_group("DLSS 3D-Guided Neural Generation [Experimental]")
        property_model = MagicMock()
        property_model.get_all_items.return_value = [group]
        setup = SetupUI.__new__(SetupUI)
        setup._settings = settings
        setup._material_properties_widget = SimpleNamespace(property_model=property_model)

        # Act
        setup._on_material_refresh_done()

        # Assert
        property_model.get_all_items.assert_called_once_with(include_hidden=True)
        self.assertTrue(group.hidden)

    def test_destroy_with_dlss_availability_subscription_unsubscribes_and_clears_state(self):
        # Arrange
        settings = MagicMock()
        subscription = MagicMock()
        setup = SetupUI.__new__(SetupUI)
        setup._settings = settings
        setup._dlss_availability_subscription = subscription
        setup._external_drag_and_drop = None
        setup._unfiltered_selected_prims = []

        with patch.object(_setup_ui, "_reset_default_attrs") as reset_default_attrs:
            # Act
            setup.destroy()

            # Assert
            settings.unsubscribe_to_change_events.assert_called_once_with(subscription)
            self.assertIsNone(setup._settings)
            self.assertIsNone(setup._dlss_availability_subscription)
            reset_default_attrs.assert_called_once_with(setup)
