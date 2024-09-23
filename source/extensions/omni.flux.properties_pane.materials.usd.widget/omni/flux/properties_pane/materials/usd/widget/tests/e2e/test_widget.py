__all__ = ("TestMaterialPropertyWidget",)

import asyncio
import functools
import os
import pathlib
import uuid

import carb.input
import omni.kit.app
import omni.kit.test
import omni.kit.test_suite.helpers
import omni.kit.ui_test
import omni.ui as ui
import omni.usd
from omni.flux.properties_pane.materials.usd.widget import MaterialPropertyWidget
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import UsdShade


class AsyncTestMeterialPropertyHelper:
    def __init__(self):

        self.window = None
        self.property_widget = None

        self._is_built = False

    async def build(self):
        self.window = ui.Window(
            f"{self.__class__.__name__}_{str(uuid.uuid1())}",
            height=200,
            width=200,
            position_x=0,
            position_y=0,
        )
        with self.window.frame:
            self.property_widget = MaterialPropertyWidget("")
        self.window.width = 600
        self.window.height = 600

        await asyncio.sleep(0.1)
        self._is_built = True

    async def destroy(self):
        self.property_widget.destroy()
        self.window.destroy()
        self._is_built = False

    async def __aenter__(self):
        await self.build()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.destroy()

    async def set_paths(self, paths, expand_groups=True):
        self.property_widget.refresh(paths)
        await omni.kit.app.get_app().next_update_async()
        if expand_groups:
            # Expand all groups
            for widget_ref in omni.kit.ui_test.find_all(
                f"{self.window.title}//Frame/**/Image[*].identifier=='property_branch'"
            ):
                await widget_ref.click()


class TestMaterialPropertyWidget(omni.kit.test.AsyncTestCase):
    @classmethod
    @functools.cache
    def get_test_data(cls, *path_parts):
        ext_id = (
            omni.kit.app.get_app()
            .get_extension_manager()
            .get_enabled_extension_id("omni.flux.properties_pane.materials.usd.widget")
        )
        root = pathlib.Path(omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id))
        result = root.joinpath("data", "tests", "usd", *path_parts)
        assert result.exists()
        return str(result)

    async def setUp(self):
        await omni.kit.test_suite.helpers.arrange_windows()
        await omni.kit.test_suite.helpers.open_stage(self.get_test_data("scene.usda"))

    async def tearDown(self):
        await omni.kit.test_suite.helpers.wait_stage_loading()

    async def test_file_texture_edit_changes(self):

        stage = omni.usd.get_context().get_stage()

        prim = stage.GetPrimAtPath("/World/Cube")
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        self.assertIsNotNone(material)
        mat_path = material.GetPath()
        self.assertIsNotNone(mat_path)

        async with AsyncTestMeterialPropertyHelper() as helper:
            await helper.set_paths([mat_path])
            widget_refs = omni.kit.ui_test.find_all(
                f"{helper.window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
            )
            self.assertTrue(len(widget_refs) > 0, "No widgets found")
            widget_ref = widget_refs[0]

            await widget_ref.click()
            await omni.kit.ui_test.emulate_keyboard_press(
                carb.input.KeyboardInput.A, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL
            )
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DEL)
            asset_path = self.get_test_data("16px_Diffuse2.dds")
            posix_asset_path = OmniUrl(asset_path).path

            await widget_ref.input(asset_path, end_key=carb.input.KeyboardInput.ENTER)
            await omni.kit.ui_test.human_delay(human_delay_speed=3)
            self.assertEquals(widget_ref.widget.model.get_value_as_string(), posix_asset_path)

    async def test_preview_window(self):

        stage = omni.usd.get_context().get_stage()

        prim = stage.GetPrimAtPath("/World/Cube")
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        self.assertIsNotNone(material)
        mat_path = material.GetPath()
        self.assertIsNotNone(mat_path)

        async with AsyncTestMeterialPropertyHelper() as helper:
            await helper.set_paths([mat_path])

            preview_image_ref = omni.kit.ui_test.find_all(f"{helper.window.title}//Frame/**/Image[*].name=='Preview'")
            self.assertTrue(len(preview_image_ref) > 0, "No preview image button found")
            preview_image_ref = preview_image_ref[0]

            await preview_image_ref.click()

            # Obtain the texture file path basename from the string field
            string_field_ref = omni.kit.ui_test.find_all(
                f"{helper.window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
            )
            self.assertTrue(len(string_field_ref) > 0, "No texture string field found")
            asset_path = string_field_ref[0].widget.model.get_attributes_raw_value(0).resolvedPath
            texture_file_basename = os.path.basename(asset_path)

            # The texture preview window title should be: ({texture file basename} - {texture type})
            window_refs = omni.kit.ui_test.find_all(f"{texture_file_basename} - Albedo Map")
            self.assertTrue(len(window_refs) == 1, "Preview window not found")
            for window_ref in window_refs:
                window_ref.widget.destroy()
