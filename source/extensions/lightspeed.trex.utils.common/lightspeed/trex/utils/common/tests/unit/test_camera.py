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

from unittest.mock import MagicMock, patch

import omni.kit.test
from lightspeed.common import constants
from lightspeed.trex.utils.common.camera import (
    PERSPECTIVE_CAMERA_PATH,
    PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS,
    _get_camera_translation,
    clear_game_camera_overrides,
    configure_pseudo_orthographic_perspective_cameras,
    copy_capture_camera_to_perspective,
    copy_composed_game_camera_to_perspective,
    ensure_editable_camera_for_navigation,
    ensure_perspective_camera_for_navigation,
    find_capture_game_camera_path,
    is_pseudo_orthographic_camera_path,
    lock_pseudo_orthographic_camera_orientation,
)
from pxr import Gf, Sdf, Usd, UsdGeom


class _ViewportAPI:
    def __init__(self, stage: Usd.Stage, camera_path: str):
        self.stage = stage
        self.camera_path = Sdf.Path(camera_path)


def _create_stage_with_capture_layer() -> tuple[Usd.Stage, Sdf.Layer]:
    root_layer = Sdf.Layer.CreateAnonymous("root.usda")
    capture_layer = Sdf.Layer.CreateAnonymous("capture.usda")
    root_layer.subLayerPaths.append(capture_layer.identifier)
    return Usd.Stage.Open(root_layer), capture_layer


def _define_camera(stage: Usd.Stage, layer: Sdf.Layer, path: str, translate: Gf.Vec3d):
    with Usd.EditContext(stage, layer):
        camera = UsdGeom.Camera.Define(stage, path)
        xformable = UsdGeom.Xformable(camera.GetPrim())
        xformable.ClearXformOpOrder()
        xformable.AddTranslateOp().Set(translate)
        return camera


def _define_mesh(stage: Usd.Stage, layer: Sdf.Layer, path: str):
    with Usd.EditContext(stage, layer):
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(10.0)
        return cube


def _assert_matrix4d_almost_equal(test_case: omni.kit.test.AsyncTestCase, actual: Gf.Matrix4d, expected: Gf.Matrix4d):
    for row in range(4):
        for column in range(4):
            test_case.assertAlmostEqual(actual[row][column], expected[row][column], places=7)


class TestCameraAuthority(omni.kit.test.AsyncTestCase):
    def test_is_pseudo_orthographic_camera_path_matches_inspection_cameras(self):
        self.assertTrue(is_pseudo_orthographic_camera_path("/OmniverseKit_Top"))
        self.assertTrue(is_pseudo_orthographic_camera_path(Sdf.Path("/OmniverseKit_Front")))
        self.assertFalse(is_pseudo_orthographic_camera_path(PERSPECTIVE_CAMERA_PATH))

    def test_find_capture_game_camera_path_uses_capture_layer_not_composed_stage(self):
        stage, capture_layer = _create_stage_with_capture_layer()
        _define_camera(stage, stage.GetRootLayer(), constants.CAPTURED_CAMERA, Gf.Vec3d(100.0, 0.0, 0.0))
        _define_camera(stage, capture_layer, constants.ROOTNODE_CAMERA, Gf.Vec3d(1.0, 2.0, 3.0))

        result = find_capture_game_camera_path(capture_layer)

        self.assertEqual(result, Sdf.Path(constants.ROOTNODE_CAMERA))

    def test_get_camera_translation_uses_transform_when_translate_has_no_authored_value(self):
        translate_attr = MagicMock()
        translate_attr.HasAuthoredValue.return_value = False
        translate_attr.Get.return_value = Gf.Vec3d(0.0, 0.0, 0.0)
        transform_attr = MagicMock()
        transform_attr.HasAuthoredValue.return_value = True
        transform_attr.Get.return_value = Gf.Matrix4d().SetTranslate(Gf.Vec3d(4.0, 5.0, 6.0))
        camera_prim = MagicMock()
        camera_prim.GetAttribute.side_effect = lambda name: {
            "xformOp:translate": translate_attr,
            "xformOp:transform": transform_attr,
        }[name]

        result = _get_camera_translation(camera_prim)

        self.assertEqual(result, Gf.Vec3d(4.0, 5.0, 6.0))
        translate_attr.Get.assert_not_called()

    def test_get_camera_translation_ignores_transform_when_transform_has_no_authored_value(self):
        translate_attr = MagicMock()
        translate_attr.HasAuthoredValue.return_value = False
        transform_attr = MagicMock()
        transform_attr.HasAuthoredValue.return_value = False
        transform_attr.Get.return_value = Gf.Matrix4d().SetTranslate(Gf.Vec3d(4.0, 5.0, 6.0))
        camera_prim = MagicMock()
        camera_prim.GetAttribute.side_effect = lambda name: {
            "xformOp:translate": translate_attr,
            "xformOp:transform": transform_attr,
        }[name]

        result = _get_camera_translation(camera_prim)

        self.assertEqual(result, Gf.Vec3d(0.0, 0.0, 0.0))
        transform_attr.Get.assert_not_called()

    def test_clear_game_camera_overrides_removes_non_capture_specs(self):
        stage, capture_layer = _create_stage_with_capture_layer()
        session_layer = stage.GetSessionLayer()
        _define_camera(stage, capture_layer, constants.CAPTURED_CAMERA, Gf.Vec3d(1.0, 2.0, 3.0))
        _define_camera(stage, stage.GetRootLayer(), constants.CAPTURED_CAMERA, Gf.Vec3d(100.0, 0.0, 0.0))
        _define_camera(stage, session_layer, constants.CAPTURED_CAMERA, Gf.Vec3d(200.0, 0.0, 0.0))

        removed_layers = clear_game_camera_overrides(stage, capture_layer)

        self.assertEqual(
            {layer.identifier for layer in removed_layers},
            {stage.GetRootLayer().identifier, session_layer.identifier},
        )
        self.assertIsNone(stage.GetRootLayer().GetPrimAtPath(constants.CAPTURED_CAMERA))
        self.assertIsNone(session_layer.GetPrimAtPath(constants.CAPTURED_CAMERA))
        self.assertIsNotNone(capture_layer.GetPrimAtPath(constants.CAPTURED_CAMERA))

    def test_copy_capture_camera_to_perspective_falls_back_to_legacy_capture_camera(self):
        stage, capture_layer = _create_stage_with_capture_layer()
        _define_camera(stage, stage.GetRootLayer(), constants.CAPTURED_CAMERA, Gf.Vec3d(100.0, 0.0, 0.0))
        _define_camera(stage, capture_layer, constants.ROOTNODE_CAMERA, Gf.Vec3d(4.0, 5.0, 6.0))
        UsdGeom.Camera.Define(stage, PERSPECTIVE_CAMERA_PATH)

        result = copy_capture_camera_to_perspective(stage, capture_layer)

        self.assertEqual(result, Sdf.Path(constants.ROOTNODE_CAMERA))
        translate = stage.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH).GetAttribute("xformOp:translate").Get()
        self.assertEqual(translate, Gf.Vec3d(4.0, 5.0, 6.0))

    def test_copy_capture_camera_to_perspective_keeps_capture_center_of_interest(self):
        stage, capture_layer = _create_stage_with_capture_layer()
        camera = _define_camera(stage, capture_layer, constants.CAPTURED_CAMERA, Gf.Vec3d(3.0, 4.0, 0.0))
        with Usd.EditContext(stage, capture_layer):
            camera.GetPrim().CreateAttribute(
                "omni:kit:centerOfInterest", Sdf.ValueTypeNames.Vector3d, True, Sdf.VariabilityUniform
            ).Set(Gf.Vec3d(0.0, 0.0, -12.0))
        UsdGeom.Camera.Define(stage, PERSPECTIVE_CAMERA_PATH)

        result = copy_capture_camera_to_perspective(stage, capture_layer)

        self.assertEqual(result, Sdf.Path(constants.CAPTURED_CAMERA))
        center_of_interest = (
            stage.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH).GetAttribute("omni:kit:centerOfInterest").Get()
        )
        self.assertEqual(center_of_interest, Gf.Vec3d(0.0, 0.0, -12.0))

    def test_copy_composed_game_camera_to_perspective_copies_composed_camera_values(self):
        # Arrange
        stage, capture_layer = _create_stage_with_capture_layer()
        capture_camera = _define_camera(stage, capture_layer, constants.CAPTURED_CAMERA, Gf.Vec3d(1.0, 2.0, 3.0))
        with Usd.EditContext(stage, capture_layer):
            capture_camera.CreateFocalLengthAttr().Set(24.0)
            capture_camera.GetFocalLengthAttr().Set(48.0, Usd.TimeCode(12.0))
            capture_camera.CreateHorizontalApertureAttr().Set(18.0)
            capture_camera.CreateVerticalApertureAttr().Set(9.0)
            capture_camera.CreateClippingRangeAttr().Set(Gf.Vec2f(0.5, 1234.0))
            capture_camera.CreateExposureAttr().Set(1.5)
        _define_camera(stage, stage.GetSessionLayer(), constants.CAPTURED_CAMERA, Gf.Vec3d(9.0, 8.0, 7.0))
        stale_camera = UsdGeom.Camera.Define(stage, PERSPECTIVE_CAMERA_PATH)
        stale_camera.CreateFocalLengthAttr().Set(99.0)
        stale_camera.CreateClippingRangeAttr().Set(Gf.Vec2f(9.0, 9.0))

        # Act
        result = copy_composed_game_camera_to_perspective(stage, constants.CAPTURED_CAMERA)

        # Assert
        perspective_camera = UsdGeom.Camera.Get(stage, PERSPECTIVE_CAMERA_PATH)
        self.assertTrue(result)
        self.assertEqual(perspective_camera.GetFocalLengthAttr().Get(), 24.0)
        self.assertEqual(perspective_camera.GetFocalLengthAttr().Get(Usd.TimeCode(12.0)), 48.0)
        self.assertEqual(perspective_camera.GetHorizontalApertureAttr().Get(), 18.0)
        self.assertEqual(perspective_camera.GetVerticalApertureAttr().Get(), 9.0)
        self.assertEqual(perspective_camera.GetClippingRangeAttr().Get(), Gf.Vec2f(0.5, 1234.0))
        self.assertEqual(perspective_camera.GetExposureAttr().Get(), 1.5)
        self.assertEqual(
            UsdGeom.Xformable(perspective_camera.GetPrim()).GetLocalTransformation().ExtractTranslation(),
            Gf.Vec3d(9.0, 8.0, 7.0),
        )

    def test_copy_composed_game_camera_to_perspective_copies_world_transform(self):
        # Arrange
        stage, capture_layer = _create_stage_with_capture_layer()
        with Usd.EditContext(stage, capture_layer):
            root_xform = UsdGeom.Xform.Define(stage, constants.ROOTNODE)
            UsdGeom.Xformable(root_xform.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(100.0, 0.0, 0.0))
        _define_camera(stage, capture_layer, constants.ROOTNODE_CAMERA, Gf.Vec3d(4.0, 5.0, 6.0))

        # Act
        result = copy_composed_game_camera_to_perspective(stage, constants.ROOTNODE_CAMERA)

        # Assert
        expected_transform = UsdGeom.Imageable(
            stage.GetPrimAtPath(constants.ROOTNODE_CAMERA)
        ).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        actual_transform = UsdGeom.Xformable(stage.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH)).GetLocalTransformation()
        self.assertTrue(result)
        _assert_matrix4d_almost_equal(self, actual_transform, expected_transform)

    def test_ensure_perspective_camera_for_navigation_switches_from_game_camera_at_same_location(self):
        stage, capture_layer = _create_stage_with_capture_layer()
        _define_camera(stage, capture_layer, constants.CAPTURED_CAMERA, Gf.Vec3d(7.0, 8.0, 9.0))
        UsdGeom.Camera.Define(stage, PERSPECTIVE_CAMERA_PATH)
        viewport_api = _ViewportAPI(stage, constants.CAPTURED_CAMERA)

        result = ensure_perspective_camera_for_navigation(viewport_api)

        self.assertTrue(result)
        self.assertEqual(viewport_api.camera_path, Sdf.Path(PERSPECTIVE_CAMERA_PATH))
        translate = (
            UsdGeom.Xformable(stage.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH))
            .GetLocalTransformation()
            .ExtractTranslation()
        )
        self.assertEqual(translate, Gf.Vec3d(7.0, 8.0, 9.0))

    def test_ensure_perspective_camera_for_navigation_authors_center_of_interest(self):
        stage, capture_layer = _create_stage_with_capture_layer()
        _define_camera(stage, capture_layer, constants.CAPTURED_CAMERA, Gf.Vec3d(7.0, 8.0, 9.0))
        UsdGeom.Camera.Define(stage, PERSPECTIVE_CAMERA_PATH)
        viewport_api = _ViewportAPI(stage, constants.CAPTURED_CAMERA)

        result = ensure_perspective_camera_for_navigation(viewport_api)

        self.assertTrue(result)
        center_of_interest = (
            stage.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH).GetAttribute("omni:kit:centerOfInterest").Get()
        )
        self.assertIsNotNone(center_of_interest)
        self.assertGreater(center_of_interest.GetLength(), 0.0)

    def test_ensure_editable_camera_for_navigation_blocks_game_camera_when_redirect_fails(self):
        stage, _capture_layer = _create_stage_with_capture_layer()
        viewport_api = _ViewportAPI(stage, constants.CAPTURED_CAMERA)

        with patch("lightspeed.trex.utils.common.camera.carb.log_warn") as log_warn_mock:
            result = ensure_editable_camera_for_navigation(viewport_api, "Camera gesture")

        self.assertFalse(result)
        self.assertEqual(viewport_api.camera_path, Sdf.Path(constants.CAPTURED_CAMERA))
        log_warn_mock.assert_any_call(
            "Camera gesture was canceled because the capture game camera could not be copied to "
            f"{PERSPECTIVE_CAMERA_PATH}; keeping the capture game camera read-only"
        )

    def test_configure_pseudo_orthographic_perspective_cameras_authors_session_camera_overrides(self):
        stage, _capture_layer = _create_stage_with_capture_layer()
        root_layer = stage.GetRootLayer()
        _define_mesh(stage, root_layer, f"{constants.ROOTNODE_MESHES}/mesh")
        for camera_path in PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS:
            camera = _define_camera(stage, root_layer, str(camera_path), Gf.Vec3d(500.0, 0.0, 0.0))
            camera.CreateProjectionAttr().Set(UsdGeom.Tokens.orthographic)

        result = configure_pseudo_orthographic_perspective_cameras(stage, [constants.ROOTNODE_MESHES])

        self.assertEqual(result, list(PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS))
        for camera_path in PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS:
            camera = UsdGeom.Camera(stage.GetPrimAtPath(camera_path))
            self.assertEqual(camera.GetProjectionAttr().Get(), UsdGeom.Tokens.perspective)
            self.assertGreater(camera.GetFocalLengthAttr().Get(), 500.0)
            self.assertIsNotNone(stage.GetSessionLayer().GetPrimAtPath(camera_path))
            self.assertEqual(
                UsdGeom.Camera.Get(stage, camera_path).GetProjectionAttr().Get(),
                UsdGeom.Tokens.perspective,
            )
            self.assertEqual(
                root_layer.GetPrimAtPath(camera_path).attributes["projection"].default,
                UsdGeom.Tokens.orthographic,
            )

    def test_configure_pseudo_orthographic_perspective_cameras_copies_render_attrs_from_perspective_camera(self):
        # Arrange
        stage, _capture_layer = _create_stage_with_capture_layer()
        _define_mesh(stage, stage.GetRootLayer(), f"{constants.ROOTNODE_MESHES}/mesh")
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            perspective_camera = UsdGeom.Camera.Define(stage, PERSPECTIVE_CAMERA_PATH)
            perspective_camera.CreateFocalLengthAttr().Set(35.0)
            perspective_camera.CreateExposureAttr().Set(1.25)
            perspective_camera.CreateFStopAttr().Set(4.0)
            perspective_camera.CreateFocusDistanceAttr().Set(123.0)
            perspective_camera.CreateShutterOpenAttr().Set(0.1)
            perspective_camera.CreateShutterCloseAttr().Set(0.9)
            perspective_camera.CreateHorizontalApertureOffsetAttr().Set(1.5)
            perspective_camera.CreateVerticalApertureOffsetAttr().Set(-2.5)

        # Act
        configure_pseudo_orthographic_perspective_cameras(stage, [constants.ROOTNODE_MESHES])

        # Assert
        for camera_path in PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS:
            camera = UsdGeom.Camera(stage.GetPrimAtPath(camera_path))
            self.assertAlmostEqual(camera.GetExposureAttr().Get(), 1.25)
            self.assertAlmostEqual(camera.GetFStopAttr().Get(), 4.0)
            self.assertAlmostEqual(camera.GetFocusDistanceAttr().Get(), 123.0)
            self.assertAlmostEqual(camera.GetShutterOpenAttr().Get(), 0.1)
            self.assertAlmostEqual(camera.GetShutterCloseAttr().Get(), 0.9)
            self.assertAlmostEqual(camera.GetHorizontalApertureOffsetAttr().Get(), 1.5)
            self.assertAlmostEqual(camera.GetVerticalApertureOffsetAttr().Get(), -2.5)
            self.assertNotEqual(camera.GetFocalLengthAttr().Get(), 35.0)

    def test_configure_pseudo_orthographic_perspective_cameras_uses_close_near_clip(self):
        # Arrange
        stage, _capture_layer = _create_stage_with_capture_layer()
        _define_mesh(stage, stage.GetRootLayer(), f"{constants.ROOTNODE_MESHES}/mesh")

        # Act
        configure_pseudo_orthographic_perspective_cameras(stage, [constants.ROOTNODE_MESHES])

        # Assert
        for camera_path in PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS:
            clipping_range = UsdGeom.Camera(stage.GetPrimAtPath(camera_path)).GetClippingRangeAttr().Get()
            self.assertAlmostEqual(clipping_range[0], 0.01)
            self.assertGreater(clipping_range[1], 1.0)

    def test_configure_pseudo_orthographic_perspective_cameras_leaves_other_cameras_unchanged(self):
        # Arrange
        stage, _capture_layer = _create_stage_with_capture_layer()
        root_layer = stage.GetRootLayer()
        session_layer = stage.GetSessionLayer()
        _define_mesh(stage, root_layer, f"{constants.ROOTNODE_MESHES}/mesh")
        perspective_camera = _define_camera(stage, root_layer, str(PERSPECTIVE_CAMERA_PATH), Gf.Vec3d(1.0, 2.0, 3.0))
        perspective_camera.CreateExposureAttr().Set(1.5)
        regular_camera = _define_camera(stage, root_layer, "/RegularCamera", Gf.Vec3d(4.0, 5.0, 6.0))
        regular_camera.CreateProjectionAttr().Set(UsdGeom.Tokens.perspective)
        regular_camera.CreateClippingRangeAttr().Set(Gf.Vec2f(7.0, 800.0))

        # Act
        configure_pseudo_orthographic_perspective_cameras(stage, [constants.ROOTNODE_MESHES])

        # Assert
        self.assertIsNone(session_layer.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH))
        self.assertIsNone(session_layer.GetPrimAtPath("/RegularCamera"))
        self.assertEqual(
            stage.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH).GetAttribute("xformOp:translate").Get(),
            Gf.Vec3d(1.0, 2.0, 3.0),
        )
        regular_camera = UsdGeom.Camera.Get(stage, "/RegularCamera")
        self.assertEqual(regular_camera.GetProjectionAttr().Get(), UsdGeom.Tokens.perspective)
        self.assertEqual(regular_camera.GetClippingRangeAttr().Get(), Gf.Vec2f(7.0, 800.0))
        self.assertEqual(
            stage.GetPrimAtPath("/RegularCamera").GetAttribute("xformOp:translate").Get(), Gf.Vec3d(4.0, 5.0, 6.0)
        )

    def test_lock_pseudo_orthographic_camera_orientation_restores_axis_and_keeps_position(self):
        stage, _capture_layer = _create_stage_with_capture_layer()
        camera = UsdGeom.Camera.Define(stage, "/OmniverseKit_Top")
        xformable = UsdGeom.Xformable(camera.GetPrim())
        xformable.ClearXformOpOrder()
        xformable.AddTransformOp().Set(
            Gf.Matrix4d()
            .SetLookAt(
                Gf.Vec3d(30.0, 40.0, 50.0),
                Gf.Vec3d(31.0, 41.0, 49.0),
                Gf.Vec3d(0.0, 1.0, 0.0),
            )
            .GetInverse()
        )

        result = lock_pseudo_orthographic_camera_orientation(stage, "/OmniverseKit_Top")

        expected_transform = (
            Gf.Matrix4d()
            .SetLookAt(
                Gf.Vec3d(30.0, 40.0, 50.0),
                Gf.Vec3d(30.0, 40.0, 49.0),
                Gf.Vec3d(0.0, 1.0, 0.0),
            )
            .GetInverse()
        )
        self.assertTrue(result)
        _assert_matrix4d_almost_equal(
            self,
            UsdGeom.Xformable(camera.GetPrim()).GetLocalTransformation(),
            expected_transform,
        )

    def test_lock_pseudo_orthographic_camera_orientation_refreshes_close_near_clip_and_center_of_interest(self):
        # Arrange
        stage, _capture_layer = _create_stage_with_capture_layer()
        camera = UsdGeom.Camera.Define(stage, "/OmniverseKit_Top")
        camera.CreateClippingRangeAttr().Set(Gf.Vec2f(100.0, 900.0))
        camera.GetPrim().CreateAttribute(
            "omni:kit:centerOfInterest", Sdf.ValueTypeNames.Vector3d, True, Sdf.VariabilityUniform
        ).Set(Gf.Vec3d(0.0, 0.0, -250.0))
        xformable = UsdGeom.Xformable(camera.GetPrim())
        xformable.ClearXformOpOrder()
        xformable.AddTransformOp().Set(
            Gf.Matrix4d()
            .SetLookAt(
                Gf.Vec3d(30.0, 40.0, 50.0),
                Gf.Vec3d(31.0, 41.0, 49.0),
                Gf.Vec3d(0.0, 1.0, 0.0),
            )
            .GetInverse()
        )

        # Act
        result = lock_pseudo_orthographic_camera_orientation(stage, "/OmniverseKit_Top")

        # Assert
        clipping_range = camera.GetClippingRangeAttr().Get()
        center_of_interest = camera.GetPrim().GetAttribute("omni:kit:centerOfInterest").Get()
        self.assertTrue(result)
        self.assertAlmostEqual(clipping_range[0], 0.01)
        self.assertAlmostEqual(clipping_range[1], 900.0)
        self.assertEqual(center_of_interest, Gf.Vec3d(0.0, 0.0, -250.0))

    def test_lock_pseudo_orthographic_camera_orientation_leaves_regular_camera_unchanged(self):
        # Arrange
        stage, _capture_layer = _create_stage_with_capture_layer()
        camera = UsdGeom.Camera.Define(stage, PERSPECTIVE_CAMERA_PATH)
        camera.CreateClippingRangeAttr().Set(Gf.Vec2f(100.0, 900.0))
        camera.GetPrim().CreateAttribute(
            "omni:kit:centerOfInterest", Sdf.ValueTypeNames.Vector3d, True, Sdf.VariabilityUniform
        ).Set(Gf.Vec3d(0.0, 0.0, -250.0))
        xformable = UsdGeom.Xformable(camera.GetPrim())
        xformable.ClearXformOpOrder()
        original_transform = (
            Gf.Matrix4d()
            .SetLookAt(
                Gf.Vec3d(30.0, 40.0, 50.0),
                Gf.Vec3d(31.0, 41.0, 49.0),
                Gf.Vec3d(0.0, 1.0, 0.0),
            )
            .GetInverse()
        )
        xformable.AddTransformOp().Set(original_transform)

        # Act
        result = lock_pseudo_orthographic_camera_orientation(stage, PERSPECTIVE_CAMERA_PATH)

        # Assert
        clipping_range = camera.GetClippingRangeAttr().Get()
        center_of_interest = camera.GetPrim().GetAttribute("omni:kit:centerOfInterest").Get()
        self.assertFalse(result)
        _assert_matrix4d_almost_equal(
            self,
            UsdGeom.Xformable(camera.GetPrim()).GetLocalTransformation(),
            original_transform,
        )
        self.assertEqual(clipping_range, Gf.Vec2f(100.0, 900.0))
        self.assertEqual(center_of_interest, Gf.Vec3d(0.0, 0.0, -250.0))
