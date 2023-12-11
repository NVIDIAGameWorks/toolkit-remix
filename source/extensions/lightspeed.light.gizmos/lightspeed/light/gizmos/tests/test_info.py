# Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
__all__ = ["TestInfo"]

from pathlib import Path

import omni.kit.app
import omni.kit.test
from lightspeed.light.gizmos.manipulator import LightGizmosManipulator
from lightspeed.light.gizmos.model import LightType as _LightType
from omni.kit.viewport.utility import get_active_viewport
from omni.ui import scene as sc
from omni.ui.tests.test_base import OmniUiTest

EXTENSION_FOLDER_PATH = Path(omni.kit.app.get_app().get_extension_manager().get_extension_path_by_module(__name__))
TEST_DATA_PATH = EXTENSION_FOLDER_PATH.joinpath("data/tests")


class LightGizmosTestModelItem(sc.AbstractManipulatorItem):
    def __init__(self):
        super().__init__()
        self.value = None


class LightGizmosTestModel(sc.AbstractManipulatorModel):
    def __init__(self, light_type, transform):
        super().__init__()

        self._cached_transform = transform
        self.transform = LightGizmosTestModelItem()
        self._cached_light_type = light_type
        self.light_type = LightGizmosTestModelItem()

    def set_value(self, item, value):
        item.value = value
        self._item_changed(item)

    def get_item(self, identifier):
        if identifier == "transform":
            return self.transform
        if identifier == "light_type":
            return self.light_type
        if identifier == "name":
            return "name"
        return None

    def update_from_prim(self):
        self.set_value(self.transform, self._cached_transform)
        self.set_value(self.light_type, self._cached_light_type)

    def get_prim_path(self):
        return ""

    def get_as_floats(self, item):
        if item == self.transform:
            return self.transform.value
        return None


class TestInfo(OmniUiTest):
    async def test_general(self):
        """Testing general look of the item"""
        window = await self.create_test_window(width=256, height=256)
        viewport_api = get_active_viewport()

        models = [
            LightGizmosTestModel(_LightType.SphereLight, sc.Matrix44(1.0)),
            LightGizmosTestModel(_LightType.RectLight, sc.Matrix44.get_translation_matrix(32.0, 0, 0)),
            LightGizmosTestModel(_LightType.DistantLight, sc.Matrix44.get_translation_matrix(64.0, 0, 0)),
            LightGizmosTestModel(_LightType.DiskLight, sc.Matrix44.get_translation_matrix(-32.0, 0, 0)),
            LightGizmosTestModel(_LightType.CylinderLight, sc.Matrix44.get_translation_matrix(-64.0, 0, 0)),
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
                    LightGizmosManipulator(viewport_api, model=model)

        await omni.kit.app.get_app().next_update_async()

        for model in models:
            model.update_from_prim()

        for _ in range(10):
            await omni.kit.app.get_app().next_update_async()

        await self.finalize_test(threshold=100, golden_img_dir=TEST_DATA_PATH, golden_img_name="general.png")
