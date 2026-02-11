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

import asyncio
from functools import partial

import omni.kit.test
from omni.flux.utils.widget.search import SearchItem, SearchModel
from omni.kit.search_core import SearchEngineRegistry
from omni.kit.test_suite.helpers import get_test_data_path

CURRENT_PATH = get_test_data_path(__name__, "test_search_files")


async def _wait_model_changed_async(model: SearchModel):
    """Async wait when the model is changed"""

    def _on_item_changed(_item: SearchItem, future: asyncio.Future):
        """Callback set the future when called"""
        if not future.done():
            future.set_result(None)

    f = asyncio.Future()
    # _sub only needs to exist within func scope and until the future is done
    _sub = model.subscribe_item_changed(partial(_on_item_changed, future=f))
    return await f


class TestSearch(omni.kit.test.AsyncTestCase):
    async def test_search(self):
        model_type = SearchEngineRegistry().get_search_model("Search Widget")
        self.assertIs(model_type, SearchModel)

        model = model_type(search_text="test", current_dir=f"{CURRENT_PATH}")
        await _wait_model_changed_async(model)

        # In the current folder we have the file "empty_test_file.py" which will be found with keyword "test"
        self.assertEqual(["empty_test_file.py"], [item.name for item in model.items])
