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

from __future__ import annotations

__all__ = ["RemixAssetPipelineConfig"]

import pathlib
from dataclasses import dataclass

from omni.flux.asset_importer.core.data_models import TextureTypes


@dataclass(frozen=True)
class RemixAssetPipelineConfig:
    """Constructor configuration shared by Remix asset pipeline steps.

    Callers must pass explicit constructor options when building a pipeline.
    This is intentionally small; do not turn step configuration into an
    auto-discovered schema or a generic metadata dictionary.

    Attributes:
        output_dir: Local directory receiving final pipeline outputs.
        texture_type: Semantic used only when synthesizing a missing texture record.
    """

    output_dir: pathlib.Path
    texture_type: TextureTypes | None
