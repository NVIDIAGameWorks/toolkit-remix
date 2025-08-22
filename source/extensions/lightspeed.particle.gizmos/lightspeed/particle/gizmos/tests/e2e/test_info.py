"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["TestInfo"]

from pathlib import Path

import omni.kit.app
import omni.kit.test
from lightspeed.particle.gizmos.manipulator import ParticleGizmoManipulator
from omni.kit.viewport.utility import get_active_viewport
from omni.ui import scene as sc
from omni.ui.tests.test_base import OmniUiTest

EXTENSION_FOLDER_PATH = Path(omni.kit.app.get_app().get_extension_manager().get_extension_path_by_module(__name__))
TEST_DATA_PATH = EXTENSION_FOLDER_PATH.joinpath("data/tests")


class ParticlesGizmosTestModelItem(sc.AbstractManipulatorItem):
    def __init__(self, value):
        super().__init__()
        self.value = value


class ParticlesGizmosTestModel(sc.AbstractManipulatorModel):
    def __init__(self, transform):
        super().__init__()

        self._cached_transform = transform
        self.transform = ParticlesGizmosTestModelItem(transform)
        self.gizmo_transform = ParticlesGizmosTestModelItem(transform)
        self.selected = ParticlesGizmosTestModelItem(False)

    def set_value(self, item, value):
        item.value = value
        self._item_changed(item)

    def get_item(self, identifier):
        if identifier == "transform":
            return self.transform
        if identifier == "gizmo_transform":
            return self.transform
        return None

    def update_from_prim(self):
        self.set_value(self.transform, self._cached_transform)
        self.set_value(self.gizmo_transform, self._cached_transform)

    def get_prim_path(self):
        return ""

    def get_as_floats(self, item):
        return item.value


class TestInfo(OmniUiTest):
    async def test_general(self):
        """Testing general look of the item"""
        window = await self.create_test_window(width=256, height=256)
        viewport_api = get_active_viewport()

        models = [
            ParticlesGizmosTestModel(sc.Matrix44(1.0)),
            ParticlesGizmosTestModel(sc.Matrix44.get_translation_matrix(32.0, 0, 0)),
            ParticlesGizmosTestModel(sc.Matrix44.get_translation_matrix(64.0, 0, 0)),
            ParticlesGizmosTestModel(sc.Matrix44.get_translation_matrix(-32.0, 0, 0)),
            ParticlesGizmosTestModel(sc.Matrix44.get_translation_matrix(-64.0, 0, 0)),
        ]

        with window.frame:
            # Camera matrices
            projection = [1e-2, 0, 0, 0]
            projection += [0, 1e-2, 0, 0]
            projection += [0, 0, -2e-7, 0]
            projection += [0, 0, 1, 1]
            view = sc.Matrix44.get_translation_matrix(0, 0, 0)

            scene_view = sc.SceneView(sc.CameraModel(projection, view))
            with scene_view.scene:
                # The manipulator
                for model in models:
                    ParticleGizmoManipulator(viewport_api, model=model)

        await omni.kit.app.get_app().next_update_async()

        for model in models:
            model.update_from_prim()

        for _ in range(10):
            await omni.kit.app.get_app().next_update_async()

        # TODO: Update golden image for particles
        await self.finalize_test(threshold=100, golden_img_dir=TEST_DATA_PATH, golden_img_name="general.png")
