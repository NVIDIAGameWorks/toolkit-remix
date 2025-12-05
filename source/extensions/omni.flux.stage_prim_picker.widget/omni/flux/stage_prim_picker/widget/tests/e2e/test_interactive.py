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

import asyncio

import omni.kit.test
import omni.ui as ui
import omni.usd
from omni.flux.stage_prim_picker.widget import StagePrimPickerField
from pxr import UsdGeom, UsdLux


class SimplePrimPathModel(ui.AbstractValueModel):
    """Simple model to hold a prim path value for testing"""

    def __init__(self, initial_value: str = "", read_only: bool = False):
        super().__init__()
        self._value = initial_value
        self.read_only = read_only

    def get_value_as_string(self) -> str:
        return self._value

    def set_value(self, value):
        self._value = str(value)
        self._value_changed()

    def get_value_as_float(self) -> float:
        try:
            return float(self._value)
        except (ValueError, TypeError):
            return 0.0

    def get_value_as_bool(self) -> bool:
        return bool(self._value)

    def get_value_as_int(self) -> int:
        try:
            return int(self._value)
        except (ValueError, TypeError):
            return 0


class MockItem:
    """Mock item for testing the field builder"""

    def __init__(self, name: str, value: str = ""):
        self.name = name
        self.element_count = 1
        self.value_models = [SimplePrimPathModel(value)]


class TestInteractiveStagePrimPicker(omni.kit.test.AsyncTestCase):
    """Interactive test for manually testing the StagePrimPickerField widget"""

    async def setUp(self):
        """Set up test environment with a populated stage"""
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

        # Create a more interesting stage with various prim types
        self._create_test_stage()

        self._test_window = None
        self._picker_field = None

    def _create_test_stage(self):
        """Create a test stage with various prim types"""
        # Create root
        UsdGeom.Xform.Define(self.stage, "/World")

        # Create geometry group
        UsdGeom.Xform.Define(self.stage, "/World/Geometry")
        UsdGeom.Cube.Define(self.stage, "/World/Geometry/Cube")
        UsdGeom.Sphere.Define(self.stage, "/World/Geometry/Sphere")
        UsdGeom.Cylinder.Define(self.stage, "/World/Geometry/Cylinder")
        UsdGeom.Cone.Define(self.stage, "/World/Geometry/Cone")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/CustomMesh")

        # Create lights group
        UsdGeom.Xform.Define(self.stage, "/World/Lights")
        UsdLux.SphereLight.Define(self.stage, "/World/Lights/KeyLight")
        UsdLux.SphereLight.Define(self.stage, "/World/Lights/FillLight")
        UsdLux.DistantLight.Define(self.stage, "/World/Lights/SunLight")
        UsdLux.RectLight.Define(self.stage, "/World/Lights/AreaLight")

        # Create camera group
        UsdGeom.Xform.Define(self.stage, "/World/Cameras")
        UsdGeom.Camera.Define(self.stage, "/World/Cameras/MainCamera")
        UsdGeom.Camera.Define(self.stage, "/World/Cameras/SecondaryCamera")

        # Create some nested structures
        UsdGeom.Xform.Define(self.stage, "/World/Props")
        UsdGeom.Xform.Define(self.stage, "/World/Props/Chair")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Chair/Seat")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Chair/Back")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Chair/Leg1")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Chair/Leg2")

        UsdGeom.Xform.Define(self.stage, "/World/Props/Table")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Table/Top")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Table/Leg1")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Table/Leg2")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Table/Leg3")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Table/Leg4")

        # Add prims with very long names to test width handling
        UsdGeom.Mesh.Define(
            self.stage,
            "/World/Geometry/VeryLongPrimNameThatShouldTestTheWidthOfTheDropdownListOverflow",
        )
        UsdGeom.Mesh.Define(
            self.stage,
            "/World/Geometry/AnotherExtremelyLongPrimPathNameToTestScrollingAndTextWrappingBehaviorInTheUserInterface",
        )

    async def tearDown(self):
        """Clean up test environment"""
        if self._test_window:
            self._test_window.destroy()
            self._test_window = None

        if self._picker_field:
            self._picker_field.destroy()
            self._picker_field = None

        await self.context.close_stage_async()
        self.stage = None

    async def test_interactive_basic_picker(self):
        """
        Interactive test: Basic prim picker without filter

        This test creates a window with the basic prim picker widget.
        You can interact with it for 100 seconds to test usability.

        Test the following:
        - Click the "..." button to open the picker
        - Search for prims (try: "Cube", "Light", "Camera", "Table")
        - Select a prim and verify it updates the field
        - Try searching with partial matches
        - Test case-insensitive search
        """
        print("\n" + "=" * 80)
        print("INTERACTIVE TEST: Basic Prim Picker")
        print("=" * 80)
        print("Instructions:")
        print("  1. Click the '...' button to open the prim picker")
        print("  2. Try searching for different prims:")
        print("     - Type 'Cube' to find the cube")
        print("     - Type 'Light' to find all lights")
        print("     - Type 'table' (lowercase) to test case-insensitive search")
        print("  3. Select prims and watch the field update")
        print("  4. The stage has Geometry, Lights, Cameras, and Props")
        print("\nYou have 100 seconds to interact with the widget...")
        print("=" * 80 + "\n")

        self._create_test_window("Basic Prim Picker Test", StagePrimPickerField())

        # Wait 100 seconds without blocking
        await asyncio.sleep(100)

    async def test_interactive_mesh_filter(self):
        """
        Interactive test: Prim picker with mesh-only filter

        This test creates a window with a prim picker that only shows mesh prims.
        You can interact with it for 100 seconds to test the filtering.

        Test the following:
        - Verify only mesh prims appear in the list
        - Search for specific meshes
        - Confirm lights and cameras don't appear
        """
        print("\n" + "=" * 80)
        print("INTERACTIVE TEST: Mesh-Only Prim Picker")
        print("=" * 80)
        print("Instructions:")
        print("  1. Click the '...' button to open the picker")
        print("  2. Notice that only Mesh prims are shown")
        print("  3. Lights, Cameras, and Xforms should NOT appear")
        print("  4. Try searching for 'Mesh', 'Seat', 'Top', etc.")
        print("\nYou have 100 seconds to interact with the widget...")
        print("=" * 80 + "\n")

        def mesh_filter(prim):
            return prim.IsA(UsdGeom.Mesh)

        self._create_test_window("Mesh-Only Prim Picker Test", StagePrimPickerField(prim_filter=mesh_filter))

        # Wait 100 seconds without blocking
        await asyncio.sleep(100)

    async def test_interactive_light_filter(self):
        """
        Interactive test: Prim picker with light-only filter

        This test creates a window with a prim picker that only shows light prims.
        You can interact with it for 100 seconds to test the filtering.

        Test the following:
        - Verify only light prims appear
        - Search for specific lights
        - Confirm geometry doesn't appear
        """
        print("\n" + "=" * 80)
        print("INTERACTIVE TEST: Light-Only Prim Picker")
        print("=" * 80)
        print("Instructions:")
        print("  1. Click the '...' button to open the picker")
        print("  2. Notice that only Light prims are shown")
        print("  3. Available lights: KeyLight, FillLight, SunLight, AreaLight")
        print("  4. Try searching for 'Sun', 'Key', 'Fill', etc.")
        print("\nYou have 100 seconds to interact with the widget...")
        print("=" * 80 + "\n")

        def light_filter(prim):
            return prim.IsA(UsdLux.Light)

        self._create_test_window("Light-Only Prim Picker Test", StagePrimPickerField(prim_filter=light_filter))

        # Wait 100 seconds without blocking
        await asyncio.sleep(100)

    async def test_interactive_multiple_pickers(self):
        """
        Interactive test: Multiple prim pickers with different filters

        This test creates a window with three different prim pickers side by side.
        You can interact with them for 100 seconds to test usability.

        Test the following:
        - Each picker should filter correctly
        - Popups should work independently
        - Values update correctly in each field
        """
        print("\n" + "=" * 80)
        print("INTERACTIVE TEST: Multiple Prim Pickers")
        print("=" * 80)
        print("Instructions:")
        print("  1. Three pickers are shown:")
        print("     - All Prims (no filter)")
        print("     - Meshes Only")
        print("     - Lights Only")
        print("  2. Test each picker independently")
        print("  3. Verify filters work correctly")
        print("  4. Test that popups don't interfere with each other")
        print("\nYou have 100 seconds to interact with the widgets...")
        print("=" * 80 + "\n")

        self._test_window = ui.Window(
            "Multiple Pickers Test",
            width=800,
            height=600,
        )

        with self._test_window.frame:
            with ui.VStack(spacing=20):
                ui.Spacer(height=10)

                # All prims picker
                with ui.HStack(spacing=10, height=0):
                    ui.Spacer(width=10)
                    ui.Label("All Prims:", width=150)
                    picker1 = StagePrimPickerField()
                    item1 = MockItem("all_prims")
                    picker1.build_ui(item1)
                    ui.Spacer(width=10)

                ui.Spacer(height=10)

                # Mesh-only picker
                with ui.HStack(spacing=10, height=0):
                    ui.Spacer(width=10)
                    ui.Label("Meshes Only:", width=150)
                    picker2 = StagePrimPickerField(prim_filter=lambda p: p.IsA(UsdGeom.Mesh))
                    item2 = MockItem("mesh_prim")
                    picker2.build_ui(item2)
                    ui.Spacer(width=10)

                ui.Spacer(height=10)

                # Light-only picker
                with ui.HStack(spacing=10, height=0):
                    ui.Spacer(width=10)
                    ui.Label("Lights Only:", width=150)
                    picker3 = StagePrimPickerField(prim_filter=lambda p: p.IsA(UsdLux.Light))
                    item3 = MockItem("light_prim")
                    picker3.build_ui(item3)
                    ui.Spacer(width=10)

                ui.Spacer(height=20)

                # Instructions
                with ui.VStack(spacing=5):
                    ui.Spacer(width=10)
                    ui.Label("Current Values:", height=0)
                    ui.Spacer(height=5)

                    def create_value_display(item, label):
                        with ui.HStack(height=0):
                            ui.Spacer(width=20)
                            ui.Label(f"{label}:", width=150)
                            value_label = ui.Label("(none)", width=0)
                            ui.Spacer(width=20)

                        def update_display(model):
                            value = model.get_value_as_string()
                            value_label.text = value if value else "(none)"

                        item.value_models[0].add_value_changed_fn(update_display)

                    create_value_display(item1, "All Prims Value")
                    create_value_display(item2, "Mesh Value")
                    create_value_display(item3, "Light Value")

                ui.Spacer()

        # Wait 100 seconds without blocking
        await asyncio.sleep(100)

    def _create_test_window(self, title: str, picker_field: StagePrimPickerField):
        """Helper to create a test window with a prim picker"""
        self._test_window = ui.Window(
            title,
            width=600,
            height=400,
        )

        # Apply proper background styling
        if self._test_window.frame:
            self._test_window.frame.style = {"Window": {"background_color": 0xFF23211F}}

        with self._test_window.frame:
            with ui.VStack(spacing=10):
                ui.Spacer(height=20)

                # Title
                with ui.HStack(height=0):
                    ui.Spacer()
                    ui.Label(title, style={"font_size": 18})
                    ui.Spacer()

                ui.Spacer(height=20)

                # The prim picker widget - constrained to fixed width like property panel
                with ui.HStack(spacing=10, height=0):
                    ui.Spacer(width=20)
                    ui.Label("Select Prim:", width=150)

                    # Wrap in Frame to simulate TreeView column constraint
                    with ui.Frame(width=ui.Pixel(300)):
                        self._picker_field = picker_field
                        item = MockItem("test_prim_path")
                        picker_field.build_ui(item)

                    ui.Spacer(width=20)

                ui.Spacer(height=20)

                # Display current value
                with ui.VStack(spacing=5):
                    ui.Label("Current Value:", height=0, alignment=ui.Alignment.CENTER)
                    value_label = ui.Label(
                        "(none selected)",
                        height=0,
                        alignment=ui.Alignment.CENTER,
                        style={"font_size": 14, "color": 0xFF00AA00},
                    )

                # Subscribe to value changes
                def update_value_display(model):
                    value = model.get_value_as_string()
                    value_label.text = value if value else "(none selected)"

                item.value_models[0].add_value_changed_fn(update_value_display)

                ui.Spacer(height=20)

                # Instructions
                with ui.VStack(spacing=5):
                    ui.Label("Instructions:", height=0)
                    ui.Label("  • Click the '...' button to open the prim picker", height=0)
                    ui.Label("  • Search for prims using the search field", height=0)
                    ui.Label("  • Click a prim to select it", height=0)
                    ui.Label("  • The value above will update automatically", height=0)

                ui.Spacer()

                # Footer
                with ui.HStack(height=0):
                    ui.Spacer()
                    ui.Label("Waiting 100 seconds for interaction...", style={"color": 0xFFAAAAAA, "font_size": 12})
                    ui.Spacer()

                ui.Spacer(height=20)
