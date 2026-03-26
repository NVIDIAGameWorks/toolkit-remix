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

Sandbox: single Placer + Rectangle. Learn Placer behavior.
"""

import asyncio
import unittest

import omni.kit.app
import omni.kit.test
from omni import ui

__all__ = ["TestPlacerSandbox"]


@unittest.skip("Interactive sandbox — run manually, not in CI")
class TestPlacerSandbox(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._exit = False
        self.window = None

    async def tearDown(self):
        if self.window:
            self.window.destroy()
            self.window = None

    async def test_placer_sandbox(self):
        """Single draggable Placer with a Rectangle."""

        def move_hidden_placer(placer: ui.Placer, new_val, is_x: bool):
            if is_x:
                new_x = min(max(100, new_val.value), 400 - 100)
                placer.offset_x = new_x
            else:
                new_y = min(max(100, new_val.value), 300 - 100)
                placer.offset_y = new_y

        self.window = ui.Window("Placer Sandbox", width=420, height=360)
        with self.window.frame:
            with ui.CanvasFrame(width=400, height=300):
                with ui.ZStack():
                    self.other_placer = ui.Placer(
                        offset_x=200, offset_y=150, width=30, height=30, draggable=False, stable_size=True
                    )
                    with self.other_placer:
                        self.other_rect = ui.Rectangle(style={"background_color": 0xFF0000FF})

                    self.hidden_placer = ui.Placer(
                        offset_x=200,
                        offset_y=180,
                        width=30,
                        height=30,
                        draggable=False,
                        stable_size=True,
                        style={"margin": 5},
                    )
                    with self.hidden_placer:
                        self.hidden_rect = ui.Rectangle(style={"background_color": 0xFF00FF00, "margin": 0})

                    with ui.Placer(
                        offset_x=100,
                        offset_y=150,
                        width=30,
                        height=30,
                        draggable=True,
                        stable_size=False,
                        offset_x_changed_fn=lambda x: move_hidden_placer(self.hidden_placer, x, True),
                        offset_y_changed_fn=lambda y: move_hidden_placer(self.hidden_placer, y, False),
                    ):
                        ui.Rectangle(style={"background_color": 0xFFFFFF00})

                    self.line = ui.FreeLine(
                        self.other_rect, self.hidden_rect, style={"color": 0xFF0000FF}, alignment=ui.Alignment.UNDEFINED
                    )

        await omni.kit.app.get_app().next_update_async()
        while not self._exit:
            await asyncio.sleep(0.1)
