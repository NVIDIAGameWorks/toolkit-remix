"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from pathlib import Path

import omni.kit.usd.layers as _layers
import omni.usd
from omni.flux.service.factory import get_instance as get_service_factory_instance
from omni.flux.utils.common.api import send_request
from omni.flux.utils.widget.resources import get_test_data
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage
from omni.services.core import main
from pxr import Sdf, Usd


class TestLayerManagerService(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.project_path = get_test_data("usd/project_example/combined.usda")

        self.context = omni.usd.get_context()
        await open_stage(self.project_path)

        factory = get_service_factory_instance()

        # Register the service in the app
        self.service = factory.get_plugin_from_name("LayerManagerService")()
        main.register_router(router=self.service.router, prefix=self.service.prefix)

    # After running each test
    async def tearDown(self):
        main.deregister_router(router=self.service.router, prefix=self.service.prefix)

        self.service = None

        if self.context.can_close_stage():
            await self.context.close_stage_async()

        self.context = None
        self.project_path = None

    async def test_get_layers_no_args_returns_project_layers(self):
        # Arrange
        project_dir = Path(get_test_data("usd/project_example"))

        # Act
        response = await send_request("GET", f"{self.service.prefix}/")

        # Assert
        self.assertEqual(
            str(response).lower(),
            str(
                {
                    "layers": [
                        {
                            "layer_id": str(project_dir / "combined.usda"),
                            "layer_type": "workfile",
                            "children": [
                                {
                                    "layer_id": str(project_dir / "replacements.usda"),
                                    "layer_type": "replacement",
                                    "children": [],
                                },
                                {
                                    "layer_id": str(project_dir / ".deps" / "captures" / "capture.usda"),
                                    "layer_type": "capture",
                                    "children": [],
                                },
                            ],
                        }
                    ]
                }
            ).lower(),
        )

    async def test_get_layers_layer_types_args_returns_project_layers_of_type(self):
        # Arrange
        project_dir = Path(get_test_data("usd/project_example"))

        # Act
        response = await send_request("GET", f"{self.service.prefix}/?layer_types=workfile&layer_types=replacement")

        # Assert
        layers = response.get("layers") or []
        self.assertEqual(
            str(sorted(layers, key=lambda i: i.get("layer_id"))).lower(),  # Sort the layers to remove flakiness
            str(
                [
                    {
                        "layer_id": str(project_dir / "combined.usda"),
                        "layer_type": "workfile",
                        "children": [],
                    },
                    {
                        "layer_id": str(project_dir / "replacements.usda"),
                        "layer_type": "replacement",
                        "children": [],
                    },
                ]
            ).lower(),
        )

    async def test_get_layers_layer_count_args_returns_n_project_layers(self):
        # Arrange
        project_dir = Path(get_test_data("usd/project_example"))

        # Act
        response = await send_request("GET", f"{self.service.prefix}/?layer_types=workfile&layer_count=1")

        # Assert
        self.assertEqual(
            str(response).lower(),
            str(
                {
                    "layers": [
                        {
                            "layer_id": str(project_dir / "combined.usda"),
                            "layer_type": "workfile",
                            "children": [],
                        }
                    ]
                }
            ).lower(),
        )

    async def test_get_sublayers_returns_layer_sublayers(self):
        # Arrange
        project_dir = Path(get_test_data("usd/project_example"))
        project_layer = (project_dir / "combined.usda").as_posix().replace("/", "%2F")

        # Act
        response = await send_request("GET", f"{self.service.prefix}/{project_layer}/sublayers")

        # Assert
        self.assertEqual(
            str(response).lower(),
            str(
                {
                    "layers": [
                        {
                            "layer_id": str(project_dir / "replacements.usda"),
                            "layer_type": "replacement",
                            "children": [],
                        },
                        {
                            "layer_id": str(project_dir / ".deps" / "captures" / "capture.usda"),
                            "layer_type": "capture",
                            "children": [],
                        },
                    ],
                }
            ).lower(),
        )

    async def test_get_layer_types_returns_expected_layer_types(self):
        # Arrange
        pass

        # Act
        response = await send_request("GET", f"{self.service.prefix}/types")

        # Assert
        self.assertEqual(
            response, {"layer_types": ["autoupscale", "capture_baker", "capture", "replacement", "workfile"]}
        )

    async def test_get_edit_target_returns_expected_edit_target(self):
        # Arrange
        expected_target = Path(get_test_data("usd/project_example/replacements.usda"))

        target_layer = Sdf.Layer.FindOrOpen(expected_target.as_posix())
        self.context.get_stage().SetEditTarget(Usd.EditTarget(target_layer))

        # Act
        response = await send_request("GET", f"{self.service.prefix}/target")

        # Assert
        self.assertEqual(str(response).lower(), str({"layer_id": str(expected_target)}).lower())

    async def test_layer_manipulations_should_work_as_expected(self):
        stage = self.context.get_stage()

        project_dir = Path(get_test_data("usd/project_example"))
        new_layer_path_01 = project_dir / "new_layer_01.usda"
        new_layer_path_02 = project_dir / "new_layer_02.usda"
        mod_layer_path = project_dir / "replacements.usda"

        # Clean up previous tests
        new_layer_path_01.unlink(missing_ok=True)
        new_layer_path_02.unlink(missing_ok=True)

        try:
            # CREATE SUBLAYER
            response = await send_request(
                "POST",
                f"{self.service.prefix}/",
                json={
                    "layer_path": str(new_layer_path_01),
                    "layer_type": "autoupscale",
                    "parent_layer_id": str(mod_layer_path),
                },
            )

            self.assertEqual(response, "OK")

            response = await send_request(
                "POST",
                f"{self.service.prefix}/",
                json={
                    "layer_path": str(new_layer_path_02),
                    "sublayer_position": 0,
                    "set_edit_target": True,
                    "parent_layer_id": str(mod_layer_path),
                },
            )

            self.assertEqual(response, "OK")
            self.assertEqual(
                self.context.get_stage().GetEditTarget().GetLayer().realPath.lower(), str(new_layer_path_02).lower()
            )

            mod_layer = self.context.get_stage().GetLayerStack()[2]  # replacements.usda
            self.assertListEqual(list(mod_layer.subLayerPaths), ["./new_layer_02.usda", "./new_layer_01.usda"])

            # MOVE SUBLAYER
            response = await send_request(
                "PUT",
                f"{self.service.prefix}/{str(new_layer_path_02)}/move",
                json={
                    "current_parent_layer_id": str(mod_layer_path),
                    "new_parent_layer_id": str(new_layer_path_01),
                },
            )

            self.assertEqual(response, "OK")

            mod_layer = self.context.get_stage().GetLayerStack()[2]  # replacements.usda
            new_layer_01 = self.context.get_stage().GetLayerStack()[3]  # new_layer_01.usda
            self.assertListEqual(list(mod_layer.subLayerPaths), ["./new_layer_01.usda"])
            self.assertListEqual(list(new_layer_01.subLayerPaths), ["./new_layer_02.usda"])

            # LOCK SUBLAYER
            response = await send_request(
                "PUT",
                f"{self.service.prefix}/{str(new_layer_path_01)}/lock",
                json={"value": True},
            )

            self.assertEqual(response, "OK")

            state = _layers.get_layers(self.context).get_layers_state()
            self.assertTrue(state.is_layer_locked(new_layer_path_01.as_posix()))
            self.assertFalse(state.is_layer_locked(new_layer_path_02.as_posix()))  # in USD, lock state is not inherited

            # MUTE SUBLAYER
            response = await send_request(
                "PUT",
                f"{self.service.prefix}/{str(new_layer_path_01)}/mute",
                json={"value": True},
            )

            self.assertEqual(response, "OK")

            self.assertTrue(stage.IsLayerMuted(new_layer_path_01.as_posix()))
            self.assertFalse(stage.IsLayerMuted(new_layer_path_02.as_posix()))  # in USD, mute state is not inherited

            # SET SUBLAYER AS EDIT TARGET
            response = await send_request(
                "PUT",
                f"{self.service.prefix}/target/{str(mod_layer_path)}",
            )

            self.assertEqual(response, "OK")
            self.assertEqual(
                self.context.get_stage().GetEditTarget().GetLayer().realPath.lower(), str(mod_layer_path).lower()
            )

            # SAVE SUBLAYER
            response = await send_request(
                "POST",
                f"{self.service.prefix}/{str(new_layer_path_01)}/save",
            )

            self.assertEqual(response, "OK")
            self.assertNotIn(
                new_layer_path_01.as_posix().lower(),
                [i.lower() for i in _layers.get_layers_state().get_dirty_layer_identifiers()],
            )

            # REMOVE SUBLAYER
            response = await send_request(
                "DELETE",
                f"{self.service.prefix}/{str(new_layer_path_01)}",
                json={"parent_layer_id": str(mod_layer_path)},
            )

            self.assertEqual(response, "OK")

            mod_layer = self.context.get_stage().GetLayerStack()[2]  # replacements.usda
            self.assertListEqual(list(mod_layer.subLayerPaths), [])
        except Exception as e:
            raise e
        finally:
            # Clean up
            new_layer_path_01.unlink(missing_ok=True)
            new_layer_path_02.unlink(missing_ok=True)
