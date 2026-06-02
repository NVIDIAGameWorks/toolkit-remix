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

import omni.kit.test
from lightspeed.trex.packaging.core.repair.authoring import RepairAuthoringCore
from pxr import Sdf


class TestRepairAuthoringCore(omni.kit.test.AsyncTestCase):
    async def test_replace_reference_list_item_missing_reference_should_not_author_new_reference(self):
        # Arrange
        layer = Sdf.Layer.CreateAnonymous()
        prim_spec = Sdf.CreatePrimInLayer(layer, Sdf.Path("/Root"))
        existing_ref = Sdf.Reference("existing.usda")
        missing_ref = Sdf.Reference("missing.usda")
        replacement_ref = Sdf.Reference("replacement.usda")

        reference_list_op = Sdf.ReferenceListOp()
        reference_list_op.prependedItems = [existing_ref]
        prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, reference_list_op)

        # Act
        result = RepairAuthoringCore._replace_reference_list_item(prim_spec, missing_ref, replacement_ref)

        # Assert
        self.assertFalse(result)
        result_list_op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
        self.assertEqual([existing_ref], list(result_list_op.prependedItems))
