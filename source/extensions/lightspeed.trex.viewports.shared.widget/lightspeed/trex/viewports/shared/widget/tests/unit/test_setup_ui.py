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
from unittest.mock import AsyncMock, MagicMock, call, patch

import omni.kit.test
import lightspeed.trex.viewports.shared.widget.extension as _extension
import lightspeed.trex.viewports.shared.widget.setup_ui as _setup_ui
from lightspeed.hydra.remix.core import RemixSupport as _RemixSupport

_ENSURE_EDITABLE = "lightspeed.trex.viewports.shared.widget.setup_ui._ensure_editable_camera"
_FRAME_SELECTION = "lightspeed.trex.viewports.shared.widget.setup_ui._frame_viewport_selection"


class TestSetupUIGameCameraBoundary(omni.kit.test.AsyncTestCase):
    async def test_mouse_press_focuses_viewport_without_redirecting_game_camera(self):
        """Clicking into a viewport should not leave the game camera unless the camera is being moved."""
        setup_ui = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup_ui._viewport_layers = SimpleNamespace(viewport_api=MagicMock())
        setup_ui.set_active = MagicMock()

        with patch(_ENSURE_EDITABLE) as mock_ensure_editable:
            setup_ui._on_viewport_frame_mouse_pressed(0.0, 0.0, 0, 0)

        mock_ensure_editable.assert_not_called()
        setup_ui.set_active.assert_called_once_with(True)

    async def test_frame_selection_redirects_game_camera_before_framing(self):
        """Frame/focus commands still switch away from the game camera before mutating the view."""
        viewport_api = MagicMock()
        setup_ui = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup_ui._viewport_layers = SimpleNamespace(viewport_api=viewport_api)

        with (
            patch(_ENSURE_EDITABLE, return_value=True) as mock_ensure_editable,
            patch(_FRAME_SELECTION) as mock_frame_selection,
        ):
            setup_ui.frame_viewport_selection()

        mock_ensure_editable.assert_called_once_with(viewport_api, "Frame/focus")
        mock_frame_selection.assert_called_once_with(viewport_api=viewport_api)

    async def test_frame_selection_cancels_when_game_camera_redirect_fails(self):
        """Frame/focus commands should not mutate the read-only game camera if redirect fails."""
        viewport_api = MagicMock()
        setup_ui = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup_ui._viewport_layers = SimpleNamespace(viewport_api=viewport_api)

        with (
            patch(_ENSURE_EDITABLE, return_value=False) as mock_ensure_editable,
            patch(_FRAME_SELECTION) as mock_frame_selection,
        ):
            setup_ui.frame_viewport_selection()

        mock_ensure_editable.assert_called_once_with(viewport_api, "Frame/focus")
        mock_frame_selection.assert_not_called()


class _DestroyedViewport:
    destroyed = True


class _LiveViewport:
    destroyed = False

    def __init__(self, context_name: str = ""):
        self.context_name = context_name


class _ValidPrim:
    def IsValid(self):  # noqa: N802 - Match USD prim API.
        return True


class TestSetupUI(omni.kit.test.AsyncTestCase):
    """Unit coverage for renderer-startup helpers; full viewport/widget interaction stays in E2E tests."""

    async def setUp(self):
        super().setUp()
        self._original_viewport_manager = dict(_extension._VIEWPORT_MANAGER_INSTANCE)
        _extension._VIEWPORT_MANAGER_INSTANCE.clear()
        _setup_ui._REMIX_FAILURE_DIALOG_SHOWN = False

    async def tearDown(self):
        _setup_ui._REMIX_FAILURE_DIALOG_SHOWN = False
        _extension._VIEWPORT_MANAGER_INSTANCE.clear()
        _extension._VIEWPORT_MANAGER_INSTANCE.update(self._original_viewport_manager)
        super().tearDown()

    async def test_show_remix_failure_dialog_requests_exit_only_dialog_when_enabled(self):
        # Arrange
        settings = MagicMock()
        settings.get_as_bool.return_value = True
        app = MagicMock()

        with (
            patch("lightspeed.trex.viewports.shared.widget.setup_ui.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.viewports.shared.widget.setup_ui.omni.kit.app.get_app", return_value=app),
            patch("lightspeed.trex.viewports.shared.widget.setup_ui._TrexMessageDialog") as mock_dialog,
        ):
            # Act
            shown = _setup_ui._show_remix_failure_dialog("Driver unsupported")
            dialog_kwargs = mock_dialog.call_args.kwargs
            dialog_kwargs["ok_handler"]()

        # Assert
        self.assertTrue(shown)
        self.assertEqual("RTX Remix Renderer failed to initialize", dialog_kwargs["title"])
        self.assertEqual("Driver unsupported", dialog_kwargs["message"])
        self.assertEqual("Exit", dialog_kwargs["ok_label"])
        self.assertTrue(dialog_kwargs["disable_cancel_button"])
        app.post_quit.assert_called_once_with(0)

    async def test_show_remix_failure_dialog_is_suppressed_when_setting_is_disabled(self):
        # Arrange
        settings = MagicMock()
        settings.get_as_bool.return_value = False

        with (
            patch("lightspeed.trex.viewports.shared.widget.setup_ui.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.trex.viewports.shared.widget.setup_ui._TrexMessageDialog") as mock_dialog,
        ):
            # Act
            shown = _setup_ui._show_remix_failure_dialog("Driver unsupported")

        # Assert
        self.assertFalse(shown)
        mock_dialog.assert_not_called()

    async def test_retry_remix_support_shows_dialog_when_retry_still_fails(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup.viewport_id = "Viewport0"

        with (
            patch(
                "lightspeed.trex.viewports.shared.widget.setup_ui._is_remix_supported",
                side_effect=[
                    (_RemixSupport.NOT_SUPPORTED, "Remix initialization timeout"),
                    (_RemixSupport.NOT_SUPPORTED, "Driver unsupported"),
                ],
            ),
            patch(
                "lightspeed.trex.viewports.shared.widget.setup_ui._retry_remix_support_async",
                new=AsyncMock(return_value=15),
            ),
            patch("lightspeed.trex.viewports.shared.widget.setup_ui._show_remix_failure_dialog") as mock_dialog,
        ):
            # Act
            await setup._retry_remix_support_after_renderer_activation("stage-opened")

        # Assert
        mock_dialog.assert_called_once_with("Driver unsupported")

    async def test_activate_remix_viewport_renderer_reapplies_engine_when_renderer_selected(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup.viewport_id = "Viewport0"
        stage = MagicMock()
        stage.GetPrimAtPath.return_value = _ValidPrim()
        viewport_api = MagicMock()
        viewport_api.id = "Viewport0"
        viewport_api.usd_context_name = ""
        viewport_api.hydra_engine = "pxr"
        viewport_api.render_mode = "HdRemixRendererPlugin"
        viewport_api.render_product_path = "/Render/Product"
        viewport_api.camera_path = "/OmniverseKit_Persp"
        viewport_api.frame_info = {"viewport_handle": 1}
        viewport_api.stage = stage
        setup._viewport_layers = MagicMock(viewport_api=viewport_api)

        with patch.object(_setup_ui.SetupUI, "_should_activate_remix_renderer", return_value=True):
            # Act
            activated = setup._activate_remix_viewport_renderer("stage-opened-stable")

        # Assert
        self.assertTrue(activated)
        viewport_api.set_hd_engine.assert_called_once_with("pxr", "HdRemixRendererPlugin")

    async def test_activate_remix_viewport_renderer_reapplies_engine_without_render_product(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup.viewport_id = "Viewport0"
        stage = MagicMock()
        stage.GetPrimAtPath.return_value = None
        viewport_api = MagicMock()
        viewport_api.id = "Viewport0"
        viewport_api.usd_context_name = ""
        viewport_api.hydra_engine = "pxr"
        viewport_api.render_mode = "HdRemixRendererPlugin"
        viewport_api.render_product_path = "/Render/Product"
        viewport_api.camera_path = "/OmniverseKit_Persp"
        viewport_api.frame_info = {"viewport_handle": 1}
        viewport_api.stage = stage
        setup._viewport_layers = MagicMock(viewport_api=viewport_api)

        with patch.object(_setup_ui.SetupUI, "_should_activate_remix_renderer", return_value=True):
            # Act
            activated = setup._activate_remix_viewport_renderer("stage-opened")

        # Assert
        self.assertTrue(activated)
        viewport_api.set_hd_engine.assert_called_once_with("pxr", "HdRemixRendererPlugin")

    async def test_activate_remix_viewport_renderer_sets_engine_when_inactive(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup.viewport_id = "Viewport0"
        stage = MagicMock()
        stage.GetPrimAtPath.return_value = _ValidPrim()
        viewport_api = MagicMock()
        viewport_api.id = "Viewport0"
        viewport_api.usd_context_name = ""
        viewport_api.hydra_engine = "Storm"
        viewport_api.render_mode = "StormRenderer"
        viewport_api.render_product_path = "/Render/Product"
        viewport_api.camera_path = "/OmniverseKit_Persp"
        viewport_api.frame_info = {"viewport_handle": 1}
        viewport_api.stage = stage
        setup._viewport_layers = MagicMock(viewport_api=viewport_api)

        with patch.object(_setup_ui.SetupUI, "_should_activate_remix_renderer", return_value=True):
            # Act
            activated = setup._activate_remix_viewport_renderer("stage-opened-stable")

        # Assert
        self.assertTrue(activated)
        viewport_api.set_hd_engine.assert_called_once_with("pxr", "HdRemixRendererPlugin")

    async def test_activate_remix_viewport_renderer_shows_dialog_when_activation_fails(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup.viewport_id = "Viewport0"
        viewport_api = MagicMock()
        viewport_api.set_hd_engine.side_effect = RuntimeError("activation failed")
        setup._viewport_layers = MagicMock(viewport_api=viewport_api)

        with (
            patch.object(_setup_ui.SetupUI, "_should_activate_remix_renderer", return_value=True),
            patch("lightspeed.trex.viewports.shared.widget.setup_ui._show_remix_failure_dialog") as mock_dialog,
        ):
            # Act
            activated = setup._activate_remix_viewport_renderer("stage-opened-stable")

        # Assert
        self.assertFalse(activated)
        mock_dialog.assert_called_once()

    async def test_is_remix_viewport_renderer_selected_does_not_require_render_product(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        viewport_api = MagicMock()
        viewport_api.hydra_engine = "pxr"
        viewport_api.render_mode = "HdRemixRendererPlugin"
        viewport_api.render_product_path = "/Render/Product"
        viewport_api.stage.GetPrimAtPath.return_value = None

        # Act / Assert
        self.assertTrue(setup._is_remix_viewport_renderer_selected(viewport_api))

        # Act
        viewport_api.render_mode = "StormRenderer"

        # Assert
        self.assertFalse(setup._is_remix_viewport_renderer_selected(viewport_api))

    async def test_apply_remix_renderer_settings_skips_settings_that_are_already_current(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        settings = MagicMock()
        settings.get.side_effect = {
            "/renderer/enabled": "pxr",
            "/renderer/active": "pxr",
            "/pxr/rendermode": "HdRemixRendererPlugin",
            "/pxr/renderers": "HdRemixRendererPlugin:Remix",
        }.get

        with patch(
            "lightspeed.trex.viewports.shared.widget.setup_ui.carb.settings.get_settings", return_value=settings
        ):
            # Act
            setup._apply_remix_renderer_settings()

        # Assert
        settings.set.assert_not_called()

    async def test_apply_remix_renderer_settings_sets_missing_values(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        settings = MagicMock()
        settings.get.side_effect = {
            "/renderer/enabled": "Storm",
            "/renderer/active": "Storm",
            "/pxr/rendermode": "StormRenderer",
            "/pxr/renderers": "",
        }.get

        with patch(
            "lightspeed.trex.viewports.shared.widget.setup_ui.carb.settings.get_settings", return_value=settings
        ):
            # Act
            setup._apply_remix_renderer_settings()

        # Assert
        self.assertEqual(
            [
                call("/renderer/enabled", "pxr"),
                call("/renderer/active", "pxr"),
                call("/pxr/rendermode", "HdRemixRendererPlugin"),
                call("/pxr/renderers", "HdRemixRendererPlugin:Remix"),
            ],
            settings.set.call_args_list,
        )

    async def test_get_instance_discards_destroyed_viewport(self):
        # Arrange
        _extension._VIEWPORT_MANAGER_INSTANCE[""] = _DestroyedViewport()

        # Act
        viewport = _extension.get_instance("")

        # Assert
        self.assertIsNone(viewport)
        self.assertNotIn("", _extension._VIEWPORT_MANAGER_INSTANCE)

    async def test_create_instance_returns_existing_live_viewport_for_existing_context(self):
        # Arrange
        existing_viewport = _LiveViewport()
        _extension._VIEWPORT_MANAGER_INSTANCE[""] = existing_viewport

        with patch.object(_extension, "_ViewportSetupUI") as setup_ui_mock:
            # Act
            viewport = _extension.create_instance("")

        # Assert
        self.assertIs(existing_viewport, viewport)
        self.assertIs(existing_viewport, _extension.get_instance(""))
        setup_ui_mock.assert_not_called()

    async def test_activate_remix_renderer_async_uses_setting_not_test_mode(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup.viewport_id = "Viewport1"
        settings = MagicMock()
        settings.get.return_value = True
        settings.get_as_int.return_value = 1

        with (
            patch("lightspeed.trex.viewports.shared.widget.setup_ui.carb.settings.get_settings", return_value=settings),
            patch.object(setup, "_apply_remix_renderer_settings"),
            patch.object(setup, "_should_activate_remix_renderer", return_value=True),
            patch.object(setup, "_wait_for_stable_viewport", new=AsyncMock(return_value=("ready",) * 9)),
            patch.object(setup, "_viewport_signature_ready", return_value=True),
            patch.object(setup, "_activate_remix_viewport_renderer", return_value=True),
            patch.object(setup, "_viewport_signature", return_value=("ready",) * 9),
            patch.object(setup, "_retry_remix_support_after_renderer_activation", new=AsyncMock()) as mock_retry,
            patch("lightspeed.trex.viewports.shared.widget.setup_ui.omni.kit.app.get_app") as mock_app,
        ):
            mock_app.return_value.next_update_async = AsyncMock()
            # Act
            await setup._activate_remix_renderer_async("stage-opened")

        # Assert
        mock_app.return_value.next_update_async.assert_awaited_once()
        mock_retry.assert_awaited_once_with("stage-opened")

    async def test_activate_remix_renderer_async_skips_activation_when_disabled(self):
        # Arrange
        setup = _setup_ui.SetupUI.__new__(_setup_ui.SetupUI)
        setup.viewport_id = "Viewport0"

        with (
            patch.object(setup, "_should_activate_remix_renderer", return_value=False),
            patch.object(setup, "_apply_remix_renderer_settings") as mock_apply_settings,
            patch.object(setup, "_activate_remix_viewport_renderer") as mock_activate_renderer,
        ):
            # Act
            await setup._activate_remix_renderer_async("stage-opened")

        # Assert
        mock_apply_settings.assert_not_called()
        mock_activate_renderer.assert_not_called()

    async def test_integrated_viewport_ui_settings_disable_embedded_kit_viewport_camera(self):
        # Arrange
        settings = MagicMock()

        with patch(
            "lightspeed.trex.viewports.shared.widget.extension.carb.settings.get_settings", return_value=settings
        ):
            # Act
            _extension._apply_integrated_viewport_ui_settings()

        # Assert
        settings.set.assert_any_call("/exts/omni.kit.viewport.window/startup/cameraManipulator/enabled", False)

    async def test_register_scenes_registers_opengl_scene_layers_by_default(self):
        # Arrange
        settings = MagicMock()
        settings.get_as_bool.return_value = True
        extension = _extension.TrexViewportSharedExtension()

        with (
            patch(
                "lightspeed.trex.viewports.shared.widget.extension.carb.settings.get_settings", return_value=settings
            ),
            patch("lightspeed.trex.viewports.shared.widget.extension.RegisterScene", side_effect=lambda *args: args[1]),
            patch(
                "lightspeed.trex.viewports.shared.widget.extension.RegisterViewportLayer",
                side_effect=lambda *args: args[1],
            ),
        ):
            # Act
            extension._TrexViewportSharedExtension__register_scenes()

        # Assert
        self.assertIn("omni.kit.viewport.LightGizmosLayer", extension._TrexViewportSharedExtension__registered)
        self.assertIn("omni.kit.viewport.ParticleGizmosLayer", extension._TrexViewportSharedExtension__registered)
        self.assertIn("omni.kit.viewport.LightManipulatorLayer", extension._TrexViewportSharedExtension__registered)

    async def test_register_scenes_can_skip_opengl_scene_layers_for_headless_tests(self):
        # Arrange
        settings = MagicMock()
        settings.get_as_bool.return_value = False
        extension = _extension.TrexViewportSharedExtension()

        with (
            patch(
                "lightspeed.trex.viewports.shared.widget.extension.carb.settings.get_settings", return_value=settings
            ),
            patch("lightspeed.trex.viewports.shared.widget.extension.RegisterScene", side_effect=lambda *args: args[1]),
            patch(
                "lightspeed.trex.viewports.shared.widget.extension.RegisterViewportLayer",
                side_effect=lambda *args: args[1],
            ),
        ):
            # Act
            extension._TrexViewportSharedExtension__register_scenes()

        # Assert
        self.assertNotIn("omni.kit.viewport.LightGizmosLayer", extension._TrexViewportSharedExtension__registered)
        self.assertNotIn("omni.kit.viewport.ParticleGizmosLayer", extension._TrexViewportSharedExtension__registered)
        self.assertNotIn("omni.kit.viewport.LightManipulatorLayer", extension._TrexViewportSharedExtension__registered)
        self.assertIn("omni.kit.viewport.SceneLayer", extension._TrexViewportSharedExtension__registered)
        self.assertIn("omni.kit.viewport.ViewportTools", extension._TrexViewportSharedExtension__registered)
