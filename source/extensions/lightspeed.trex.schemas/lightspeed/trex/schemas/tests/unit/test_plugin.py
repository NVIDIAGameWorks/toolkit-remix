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

from lightspeed.trex.schemas.plugin import _get_remix_particle_system_plugin_path
from omni.kit.test import AsyncTestCase


class TestPlugin(AsyncTestCase):
    def test_get_remix_particle_system_plugin_path_nested_resources_exists_returns_resources_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            plugins_root = Path(temp_dir)
            resources_path = plugins_root / "RemixParticleSystem" / "resources"
            resources_path.mkdir(parents=True)
            (resources_path / "plugInfo.json").touch()
            (plugins_root / "plugInfo.json").touch()

            # Act
            plugin_path = _get_remix_particle_system_plugin_path(str(plugins_root))

            # Assert
            self.assertEqual(str(resources_path), plugin_path)

    def test_get_remix_particle_system_plugin_path_root_plugin_exists_returns_root_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            plugins_root = Path(temp_dir)
            (plugins_root / "RemixParticleSystem").mkdir()
            (plugins_root / "plugInfo.json").touch()

            # Act
            plugin_path = _get_remix_particle_system_plugin_path(str(plugins_root))

            # Assert
            self.assertEqual(str(plugins_root), plugin_path)

    def test_get_remix_particle_system_plugin_path_plugin_info_missing_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            plugins_root = Path(temp_dir)
            (plugins_root / "RemixParticleSystem").mkdir()

            # Act
            with self.assertRaisesRegex(FileNotFoundError, "RemixParticleSystem plugInfo.json not found"):
                _get_remix_particle_system_plugin_path(str(plugins_root))
