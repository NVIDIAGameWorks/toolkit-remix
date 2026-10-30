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

import omni.kit.commands
import omni.kit.test
import omni.kit.undo
from pxr import Sdf


class TestCommandsE2E(omni.kit.test.AsyncTestCase):
    """Run the registered asset pipeline commands through the Kit command and undo stacks."""

    async def test_undo_removes_only_the_created_owner_branch(self):
        """Undo removes the owner spec and its new ancestors, and keeps the specs that existed before."""
        layer = Sdf.Layer.CreateAnonymous()
        Sdf.CreatePrimInLayer(layer, "/World/Existing")
        Sdf.CreatePrimInLayer(layer, "/Unrelated")
        original = layer.ExportToString()

        # The owner and its Group ancestor are missing. World and the unrelated specs already exist.
        omni.kit.commands.execute(
            "CreateReferenceOwnerSpecCommand", layer=layer, prim_path=Sdf.Path("/World/Group/Owner")
        )
        self.assertIsNotNone(layer.GetPrimAtPath("/World/Group/Owner"))

        omni.kit.undo.undo()

        self.assertEqual(layer.ExportToString(), original)
