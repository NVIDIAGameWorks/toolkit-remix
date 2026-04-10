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

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import omni.kit.test
from lightspeed.trex.control.stagecraft.setup import Setup
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.window import WizardTypes as _WizardTypes


class TestCheckCaptureOnOpen(omni.kit.test.AsyncTestCase):
    """Unit tests for control.stagecraft.Setup._check_capture_on_open."""

    def _make_setup(self, project_layer=None, capture_layer=None):
        """Build a minimal Setup-like object to exercise _check_capture_on_open via mocks."""
        with (
            patch("lightspeed.trex.control.stagecraft.setup._LayerManagerCore"),
            patch("lightspeed.trex.control.stagecraft.setup._CaptureCoreSetup"),
            patch("lightspeed.trex.control.stagecraft.setup._ReplacementCoreSetup"),
            patch("lightspeed.trex.control.stagecraft.setup._StageCoreSetup"),
            patch("lightspeed.trex.control.stagecraft.setup._trex_contexts_instance"),
            patch("lightspeed.trex.control.stagecraft.setup._get_menu_workfile_instance"),
            patch("lightspeed.trex.control.stagecraft.setup._get_event_manager_instance"),
            patch("lightspeed.trex.control.stagecraft.setup._get_global_hotkey_manager"),
            patch("lightspeed.trex.control.stagecraft.setup.load_layout"),
            patch("lightspeed.trex.control.stagecraft.setup.carb"),
        ):
            setup = Setup.__new__(Setup)
        setup._context_name = ""
        setup._layer_manager = MagicMock()
        setup._capture_core_setup = MagicMock()
        setup._layer_manager.get_layer_of_type.side_effect = lambda layer_type: (
            project_layer if str(layer_type).endswith("workfile") else capture_layer
        )
        return setup

    async def test_opens_wizard_when_project_has_no_capture(self):
        """_check_capture_on_open should show an OPEN wizard when capture is missing."""
        # Arrange
        fake_project_layer = MagicMock()
        fake_project_layer.realPath = "/some/project/mod.usda"
        setup = self._make_setup(project_layer=fake_project_layer, capture_layer=None)
        mock_wizard = MagicMock()

        # Act
        with patch(
            "lightspeed.trex.control.stagecraft.setup._get_wizard_instance",
            return_value=mock_wizard,
        ) as mock_get_instance:
            setup._check_capture_on_open()

        # Assert
        mock_get_instance.assert_called_once_with(_WizardTypes.OPEN, setup._context_name)
        mock_wizard.set_payload.assert_called_once()
        mock_wizard.subscribe_wizard_completed.assert_called_once()
        mock_wizard.show_project_wizard.assert_called_once_with(reset_page=True)

    async def test_no_wizard_when_capture_layer_exists(self):
        """_check_capture_on_open should do nothing when both project and capture layers are present."""
        # Arrange
        fake_project_layer = MagicMock()
        fake_project_layer.realPath = "/some/project/mod.usda"
        fake_capture_layer = MagicMock()
        setup = self._make_setup(project_layer=fake_project_layer, capture_layer=fake_capture_layer)

        # Act
        with patch("lightspeed.trex.control.stagecraft.setup._get_wizard_instance") as mock_get_instance:
            setup._check_capture_on_open()

        # Assert
        mock_get_instance.assert_not_called()

    async def test_no_wizard_when_no_project_layer(self):
        """_check_capture_on_open should do nothing when there is no project layer (stage not a project)."""
        # Arrange
        setup = self._make_setup(project_layer=None, capture_layer=None)

        # Act
        with patch("lightspeed.trex.control.stagecraft.setup._get_wizard_instance") as mock_get_instance:
            setup._check_capture_on_open()

        # Assert
        mock_get_instance.assert_not_called()

    async def test_wizard_payload_contains_remix_directory_when_deps_exists(self):
        """REMIX_DIRECTORY is included in the payload when the deps symlink resolves to an existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_dir = Path(tmpdir) / "my_project"
            project_dir.mkdir()
            deps_dir = project_dir / "deps"
            deps_dir.mkdir()
            fake_project_layer = MagicMock()
            fake_project_layer.realPath = str(project_dir / "mod.usda")
            setup = self._make_setup(project_layer=fake_project_layer, capture_layer=None)
            mock_wizard = MagicMock()

            # Act
            with patch(
                "lightspeed.trex.control.stagecraft.setup._get_wizard_instance",
                return_value=mock_wizard,
            ):
                setup._check_capture_on_open()

            # Assert
            payload = mock_wizard.set_payload.call_args[0][0]
            self.assertIn(_ProjectWizardKeys.PROJECT_FILE.value, payload)
            self.assertIn(_ProjectWizardKeys.REMIX_DIRECTORY.value, payload)
            self.assertEqual(payload[_ProjectWizardKeys.REMIX_DIRECTORY.value], deps_dir.resolve())

    async def test_wizard_payload_omits_remix_directory_when_deps_missing(self):
        """REMIX_DIRECTORY is omitted from the payload when the deps directory does not exist."""
        # Arrange
        fake_project_layer = MagicMock()
        fake_project_layer.realPath = "/nonexistent/project/mod.usda"
        setup = self._make_setup(project_layer=fake_project_layer, capture_layer=None)
        mock_wizard = MagicMock()

        # Act
        with patch(
            "lightspeed.trex.control.stagecraft.setup._get_wizard_instance",
            return_value=mock_wizard,
        ):
            setup._check_capture_on_open()

        # Assert
        payload = mock_wizard.set_payload.call_args[0][0]
        self.assertIn(_ProjectWizardKeys.PROJECT_FILE.value, payload)
        self.assertNotIn(_ProjectWizardKeys.REMIX_DIRECTORY.value, payload)

    async def test_capture_repair_imports_directly_into_main_context(self):
        """_on_capture_repair_completed should call import_capture_layer with the deps-relative path."""
        # Arrange
        setup = self._make_setup(project_layer=None, capture_layer=None)
        payload = {
            _ProjectWizardKeys.PROJECT_FILE.value: Path("/some/project/mod.usda"),
            _ProjectWizardKeys.CAPTURE_FILE.value: Path("/resolved/rtx-remix/captures/my_capture.usda"),
        }

        # Act
        setup._on_capture_repair_completed(payload)

        # Assert
        expected_path = str(Path("/some/project/deps/captures/my_capture.usda"))
        setup._capture_core_setup.import_capture_layer.assert_called_once_with(expected_path)

    async def test_capture_repair_no_import_when_no_capture_selected(self):
        """_on_capture_repair_completed should do nothing when no capture was selected."""
        # Arrange
        setup = self._make_setup(project_layer=None, capture_layer=None)
        payload = {
            _ProjectWizardKeys.PROJECT_FILE.value: Path("/some/project/mod.usda"),
        }

        # Act
        setup._on_capture_repair_completed(payload)

        # Assert
        setup._capture_core_setup.import_capture_layer.assert_not_called()
