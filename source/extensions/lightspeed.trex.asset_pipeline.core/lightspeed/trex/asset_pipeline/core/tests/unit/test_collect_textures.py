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

import pathlib

import omni.kit.test
from omni.flux.asset_pipeline.core import PipelineStepState

from lightspeed.trex.asset_pipeline.core import MaterialType, RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import CollectTexturesStep


class TestCollectTextures(omni.kit.test.AsyncTestCase):
    async def test_should_run_returns_false_after_collection_ran(self):
        """Textureless models do not force repeated collection scans in one run context."""
        # Arrange
        item = RemixAssetItem.from_model(pathlib.Path("/models/textureless.usd"), MaterialType.OPAQUE)
        context = RemixAssetPipelineContext(items=[item])
        step = CollectTexturesStep()
        context.execution_state[step.name] = PipelineStepState(step_name=step.name, did_run=True)

        # Act
        should_run = step.should_run(context)

        # Assert
        self.assertFalse(should_run)

    async def test_should_run_returns_true_before_textureless_model_collection(self):
        """Textureless model items still run once so collection can verify the stage."""
        # Arrange
        item = RemixAssetItem.from_model(pathlib.Path("/models/textureless.usd"), MaterialType.OPAQUE)
        context = RemixAssetPipelineContext(items=[item])

        # Act
        should_run = CollectTexturesStep().should_run(context)

        # Assert
        self.assertTrue(should_run)
