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

import omni.kit.app
import omni.kit.test
import omni.ui as ui
from lightspeed.trex.utils.widget.decorators import SKIPPED, skip_when_widget_is_invisible
from omni.kit.test_suite.helpers import arrange_windows


class TestWidget:
    """Test widget using real Omni UI for testing visibility logic"""

    def __init__(self):
        self.root_widget = ui.Frame()
        self.callback_executed = False
        self.callback_count = 0
        self.callback_args = None
        self.callback_kwargs = None

    @skip_when_widget_is_invisible(widget="root_widget")
    def decorated_callback(self, *args, **kwargs):
        """Test callback that should be filtered when invisible"""
        self.callback_executed = True
        self.callback_count += 1
        self.callback_args = args
        self.callback_kwargs = kwargs
        return "executed"

    @skip_when_widget_is_invisible(widget="root_widget")
    def decorated_callback_with_return(self, value):
        """Test callback that returns a value"""
        self.callback_count += 1
        return value * 2


class TestSkipWhenInvisibleDecorator(omni.kit.test.AsyncTestCase):
    """Test suite for @skip_when_widget_is_invisible decorator"""

    async def setUp(self):
        await arrange_windows()

    async def test_decorator_executes_when_widget_visible(self):
        """Test that decorated callback executes when widget is visible"""
        window = ui.Window("test_visible", width=400, height=300)
        with window.frame:
            widget = TestWidget()

        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        result = widget.decorated_callback("arg1", kwarg1="value1")

        self.assertTrue(widget.callback_executed)
        self.assertEqual(widget.callback_count, 1)
        self.assertEqual(widget.callback_args, ("arg1",))
        self.assertEqual(widget.callback_kwargs, {"kwarg1": "value1"})
        self.assertEqual(result, "executed")

        window.destroy()

    async def test_decorator_skips_when_widget_invisible(self):
        """Test that decorated callback is skipped when widget is invisible"""
        window = ui.Window("test_invisible", width=400, height=300)
        with window.frame:
            widget = TestWidget()

        widget.root_widget.visible = False
        await omni.kit.app.get_app().next_update_async()

        result = widget.decorated_callback("arg1")

        self.assertFalse(widget.callback_executed)
        self.assertEqual(widget.callback_count, 0)
        self.assertIsNone(widget.callback_args)
        self.assertEqual(result, SKIPPED)

        window.destroy()

    async def test_decorator_with_missing_widget_attribute(self):
        """Test that decorator raises AttributeError when widget attribute doesn't exist"""

        class WidgetWithMissingAttr:
            def __init__(self):
                self.callback_count = 0
                # No root_widget attribute

            @skip_when_widget_is_invisible(widget="root_widget")
            def decorated_callback(self):
                self.callback_count += 1
                return "executed"

        widget = WidgetWithMissingAttr()

        # Should raise AttributeError with helpful message
        with self.assertRaises(AttributeError) as context:
            widget.decorated_callback()

        error_msg = str(context.exception)
        self.assertIn("root_widget", error_msg)
        self.assertIn("WidgetWithMissingAttr", error_msg)
        self.assertEqual(widget.callback_count, 0, "Callback should not have executed")

    async def test_decorator_multiple_calls(self):
        """Test that decorator correctly handles multiple calls"""
        window = ui.Window("test_multiple_calls", width=400, height=300)
        with window.frame:
            widget = TestWidget()

        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        # Call 3 times when visible
        widget.decorated_callback()
        widget.decorated_callback()
        widget.decorated_callback()
        self.assertEqual(widget.callback_count, 3)

        # Make invisible and call 2 more times
        widget.root_widget.visible = False
        await omni.kit.app.get_app().next_update_async()
        widget.decorated_callback()
        widget.decorated_callback()
        self.assertEqual(widget.callback_count, 3)  # Count should not increase

        # Make visible again and call once
        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()
        widget.decorated_callback()
        self.assertEqual(widget.callback_count, 4)

        window.destroy()

    async def test_decorator_preserves_return_value(self):
        """Test that decorator preserves return values"""
        window = ui.Window("test_return_value", width=400, height=300)
        with window.frame:
            widget = TestWidget()

        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        result = widget.decorated_callback_with_return(5)
        self.assertEqual(result, 10)

        widget.root_widget.visible = False
        await omni.kit.app.get_app().next_update_async()
        result = widget.decorated_callback_with_return(5)
        self.assertEqual(result, SKIPPED)

        window.destroy()

    async def test_decorator_with_exception_in_callback(self):
        """Test that decorator doesn't suppress exceptions from the callback"""

        class WidgetWithException:
            def __init__(self):
                self.root_widget = ui.Frame(visible=True)

            @skip_when_widget_is_invisible(widget="root_widget")
            def decorated_callback_that_raises(self):
                raise ValueError("Test exception")

        window = ui.Window("test_exception", width=400, height=300)
        with window.frame:
            widget = WidgetWithException()

        await omni.kit.app.get_app().next_update_async()

        with self.assertRaises(ValueError) as context:
            widget.decorated_callback_that_raises()
        self.assertEqual(str(context.exception), "Test exception")

        window.destroy()

    async def test_decorator_is_stackable(self):
        """Test that multiple decorators can be stacked"""

        class WidgetWithMultipleChecks:
            def __init__(self):
                self.root_widget = ui.Frame(visible=True)
                self.secondary_widget = ui.Frame(visible=True)
                self.callback_count = 0

            @skip_when_widget_is_invisible(widget="root_widget")
            @skip_when_widget_is_invisible(widget="secondary_widget")
            def on_event(self):
                self.callback_count += 1

        window = ui.Window("test_stackable", width=400, height=300)
        with window.frame:
            widget = WidgetWithMultipleChecks()

        await omni.kit.app.get_app().next_update_async()

        # Both visible - should execute
        widget.on_event()
        self.assertEqual(widget.callback_count, 1)

        # Hide root_widget - should NOT execute
        widget.root_widget.visible = False
        await omni.kit.app.get_app().next_update_async()
        widget.on_event()
        self.assertEqual(widget.callback_count, 1)  # No change

        # Show root, hide secondary - should NOT execute
        widget.root_widget.visible = True
        widget.secondary_widget.visible = False
        await omni.kit.app.get_app().next_update_async()
        widget.on_event()
        self.assertEqual(widget.callback_count, 1)  # No change

        # Both visible again - should execute
        widget.secondary_widget.visible = True
        await omni.kit.app.get_app().next_update_async()
        widget.on_event()
        self.assertEqual(widget.callback_count, 2)

        window.destroy()

    async def test_skips_when_parent_frame_invisible(self):
        """Test that decorator skips when parent frame is invisible even if widget is visible"""
        window = ui.Window("test_parent_frame", width=400, height=300)
        with window.frame:
            parent_frame = ui.Frame(visible=True)
            with parent_frame:
                widget = TestWidget()

        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        # Both visible - should execute
        result = widget.decorated_callback()
        self.assertEqual(widget.callback_count, 1)
        self.assertEqual(result, "executed")

        # Hide parent frame - should skip even though widget.root_widget.visible is True
        parent_frame.visible = False
        await omni.kit.app.get_app().next_update_async()

        result = widget.decorated_callback()
        self.assertEqual(result, SKIPPED, "Should skip when parent frame is invisible")
        self.assertEqual(widget.callback_count, 1)  # Should not increment

        window.destroy()

    async def test_skips_when_grandparent_frame_invisible(self):
        """Test that decorator skips when grandparent frame is invisible"""
        window = ui.Window("test_grandparent_frame", width=400, height=300)
        with window.frame:
            grandparent_frame = ui.Frame(visible=True)
            with grandparent_frame:
                parent_frame = ui.Frame(visible=True)
                with parent_frame:
                    widget = TestWidget()

        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        # All visible - should execute
        result = widget.decorated_callback()
        self.assertEqual(widget.callback_count, 1)
        self.assertEqual(result, "executed")

        # Hide grandparent - should skip
        grandparent_frame.visible = False
        await omni.kit.app.get_app().next_update_async()

        result = widget.decorated_callback()
        self.assertEqual(result, SKIPPED, "Should skip when grandparent is invisible")
        self.assertEqual(widget.callback_count, 1)  # Should not increment

        window.destroy()

    async def test_skips_when_window_frame_invisible(self):
        """Test that decorator skips when the window.frame itself is invisible"""
        window = ui.Window("test_window_frame", width=400, height=300)
        with window.frame:
            widget = TestWidget()

        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        # Window frame visible - should execute
        result = widget.decorated_callback()
        self.assertEqual(widget.callback_count, 1)
        self.assertEqual(result, "executed")

        # Hide window frame - should skip
        window.frame.visible = False
        await omni.kit.app.get_app().next_update_async()

        result = widget.decorated_callback()
        self.assertEqual(result, SKIPPED, "Should skip when window frame is invisible")
        self.assertEqual(widget.callback_count, 1)  # Should not increment

        window.destroy()

    async def test_skips_when_window_invisible(self):
        """Test that decorator skips when the window itself is invisible"""
        window = ui.Window("test_window_frame", width=400, height=300)
        with window.frame:
            widget = TestWidget()

        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        # Window frame visible - should execute
        result = widget.decorated_callback()
        self.assertEqual(widget.callback_count, 1)
        self.assertEqual(result, "executed")

        # Hide window frame - should skip
        window.visible = False
        await omni.kit.app.get_app().next_update_async()

        result = widget.decorated_callback()
        self.assertEqual(result, SKIPPED, "Should skip when window is invisible")
        self.assertEqual(widget.callback_count, 1)  # Should not increment

        window.destroy()
