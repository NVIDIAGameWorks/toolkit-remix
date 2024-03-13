import omni.usd
from carb.input import KeyboardInput
from lightspeed.trex.control.stagecraft import Setup as _ControlSetup
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage, wait_stage_loading


class TestHotkeys(AsyncTestCase):

    # Before running each test
    async def setUp(self):
        _ControlSetup()
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def test_unselect_all_with_esc(self):
        # Setup
        usd_context = omni.usd.get_context()

        # Select an object and ensure it is selected
        expected_value = ["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"]
        usd_context.get_selection().set_selected_prim_paths(expected_value, False)
        self.assertListEqual(usd_context.get_selection().get_selected_prim_paths(), expected_value)

        # Use the ESC hotkey to unselect everything
        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay(human_delay_speed=10)

        # Ensure that nothing is selected
        self.assertListEqual(usd_context.get_selection().get_selected_prim_paths(), [])
