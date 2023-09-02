from pathlib import Path

import omni.kit.test
import omni.usd
from lightspeed.trex.replacement.core.shared import AssetReplacementLayersCore
from omni.kit.test_suite.helpers import get_test_data_path, open_stage, wait_stage_loading


class TestLayers(omni.kit.test.AsyncTestCase):

    # Before running each test
    async def setUp(self):
        self.core = AssetReplacementLayersCore()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

        self.core = None

    async def test_get_layers_exclude_remove_should_return_replacement_capture_root(self):
        mod_path = Path(get_test_data_path(__name__, "usd/mod.usda")).as_posix().lower()
        capture_path = Path(get_test_data_path(__name__, "usd/deps/captures/capture.usda")).as_posix().lower()
        project_path = Path(get_test_data_path(__name__, "usd/project.usda")).as_posix().lower()

        await open_stage(project_path)
        val = self.core.get_layers_exclude_remove()

        self.assertListEqual([mod_path, capture_path, project_path], [v.lower() for v in val])

    async def test_get_layers_exclude_lock_should_return_replacement_capture_root(self):
        mod_path = Path(get_test_data_path(__name__, "usd/mod.usda")).as_posix().lower()
        capture_path = Path(get_test_data_path(__name__, "usd/deps/captures/capture.usda")).as_posix().lower()
        project_path = Path(get_test_data_path(__name__, "usd/project.usda")).as_posix().lower()

        await open_stage(project_path)
        val = self.core.get_layers_exclude_lock()

        self.assertListEqual([mod_path, capture_path, project_path], [v.lower() for v in val])

    async def test_get_layers_exclude_mute_should_return_capture_root(self):
        capture_path = Path(get_test_data_path(__name__, "usd/deps/captures/capture.usda")).as_posix().lower()
        project_path = Path(get_test_data_path(__name__, "usd/project.usda")).as_posix().lower()

        await open_stage(project_path)
        val = self.core.get_layers_exclude_mute()

        self.assertListEqual([capture_path, project_path], [v.lower() for v in val])

    async def test_get_layers_exclude_edit_target_should_return_all_except_replacement(self):
        capture_path = Path(get_test_data_path(__name__, "usd/deps/captures/capture.usda")).as_posix().lower()
        dep_mod_path = Path(get_test_data_path(__name__, "usd/deps/mods/SubProject/mod.usda")).as_posix().lower()
        project_path = Path(get_test_data_path(__name__, "usd/project.usda")).as_posix().lower()

        await open_stage(project_path)
        val = self.core.get_layers_exclude_edit_target()

        self.assertListEqual([project_path, capture_path, dep_mod_path], [v.lower() for v in val])

    async def test_get_layers_exclude_add_child_should_return_capture_root(self):
        capture_path = Path(get_test_data_path(__name__, "usd/deps/captures/capture.usda")).as_posix().lower()
        project_path = Path(get_test_data_path(__name__, "usd/project.usda")).as_posix().lower()

        await open_stage(project_path)
        val = self.core.get_layers_exclude_add_child()

        self.assertListEqual([capture_path, project_path], [v.lower() for v in val])

    async def test_get_layers_exclude_move_should_return_replacement_capture_root(self):
        mod_path = Path(get_test_data_path(__name__, "usd/mod.usda")).as_posix().lower()
        capture_path = Path(get_test_data_path(__name__, "usd/deps/captures/capture.usda")).as_posix().lower()
        project_path = Path(get_test_data_path(__name__, "usd/project.usda")).as_posix().lower()

        await open_stage(project_path)
        val = self.core.get_layers_exclude_move()

        self.assertListEqual([mod_path, capture_path, project_path], [v.lower() for v in val])
