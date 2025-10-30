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

import omni.graph.core as og
import omni.graph.core.tests as ogts


class TestRemixLogicGraph(ogts.OmniGraphTestCase):
    """Using OmniGraphTestCase as the base ensures that the graph environment is clean for your test"""

    async def test_set_compute_incomplete(self):
        """Simple test illustrating how to use the Controller to run tests."""
        # Unless you are explicitly testing undo turning it off makes the test run faster
        controller = og.Controller(undoable=False)
        keys = og.Controller.Keys

        # Create a simple graph consisting of one node with one input attribute on it set to a known value
        (
            _,
            (anim_float_node, sphere_light_node),
            _,
            _,
        ) = controller.edit(
            "/RemixLogicGraph",
            {
                keys.CREATE_NODES: [
                    ("AnimatedFloat", "lightspeed.trex.logic.AnimatedFloat"),
                    (
                        "SphereLightOverride",
                        "lightspeed.trex.logic.SphereLightOverride",
                    ),
                ],
                keys.SET_VALUES: ("AnimatedFloat.inputs:initialValue", 7.5),
                keys.CONNECT: [
                    (
                        "AnimatedFloat.outputs:currentValue",
                        "SphereLightOverride.inputs:radius",
                    )
                ],
            },
        )

        # Wait for evaluation and then confirm that the output has the correctly computed result.
        # This is essentially what the tests generated from the .ogn file's "tests" section does as well.
        await controller.evaluate()

        # REMIX: We don't really care about the compute() results since the runtime runs the logic for us.
        value_out = controller.attribute("outputs:currentValue", anim_float_node)
        self.assertEqual(controller.get(value_out), 0.0)  # will be 0.0 with dummy implementation
        radius_in = controller.attribute("inputs:radius", sphere_light_node)
        self.assertEqual(controller.get(radius_in), 0.0)
