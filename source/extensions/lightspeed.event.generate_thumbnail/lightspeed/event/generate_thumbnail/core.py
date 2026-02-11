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

import io
import tempfile
import time
import uuid
from asyncio import ensure_future

import carb
import omni.client
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.trex.viewports.shared.widget import get_viewport_api
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit.widget.viewport.capture import MultiAOVFileCapture
from PIL import Image

_CONTEXT = "/exts/lightspeed.event.generate_thumbnail/context"


class EventGenerateThumbnailCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_stage_event_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = carb.settings.get_settings().get(_CONTEXT) or ""

    @property
    def name(self) -> str:
        """Name of the event"""
        return "GenerateThumbnail"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._context = omni.usd.get_context(self._context_name)
        self._stage_event_sub = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageEventListener"
        )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._layer_event_sub = None

    def __on_stage_event(self, event):
        if event.type != int(omni.usd.StageEventType.SAVED):
            return

        ensure_future(self.__generate_thumbnail())

    @omni.usd.handle_exception
    async def __generate_thumbnail(self):
        class HdrCaptureHelper(MultiAOVFileCapture):
            def __init__(self, file_path: str, is_hdr: bool, format_desc: dict = None):
                super().__init__(["HdrColor" if is_hdr else "LdrColor"], [file_path])

            def __del__(self):
                pass

            def capture_aov(self, file_path, aov):
                self.save_aov_to_file(file_path, aov)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = str(OmniUrl(temp_dir) / f"{str(uuid.uuid4())[:8]}.png")
            get_viewport_api(self._context_name).schedule_capture(HdrCaptureHelper(temp_file, False))

            delay = 5
            timeout = time.time() + delay
            while time.time() < timeout:
                if OmniUrl(temp_file).exists:
                    break
                await omni.kit.app.get_app().next_update_async()
            else:
                carb.log_error(f"Unable to capture frame within {delay} seconds. {temp_file}")
                return

            self.__crop_and_resize_image(temp_file, (256, 256))

    def __crop_and_resize_image(self, temp_path: str, resolution: tuple[int, int]):
        """
        For a given image and resolution image is resized and stored under a .thumbs directory along the current path.
        """
        stage_url = OmniUrl(self._context.get_stage_url())
        output_path = str(
            OmniUrl(stage_url.parent_url) / ".thumbs" / f"{resolution[0]}x{resolution[1]}" / f"{stage_url.name}.png"
        )

        # Crop the center of the image
        result, _, content = omni.client.read_file(temp_path)
        if result != omni.client.Result.OK:
            carb.log_error("Could not open the temporary thumbnail image file.")
            return

        with Image.open(io.BytesIO(content)) as im:
            width, height = im.size  # Get dimensions
            if width > height:
                left = (width - height) / 2
                right = width - left
                top = 0
                bottom = height
            else:
                left = 0
                right = width
                top = (height - width) / 2
                bottom = height - top

            im = im.crop((left, top, right, bottom))
            im.thumbnail(resolution, Image.LANCZOS)

            thumbnail_bytes = io.BytesIO()
            im.save(thumbnail_bytes, format="PNG")

        result = omni.client.write_file(output_path, thumbnail_bytes.getvalue())
        if result != omni.client.Result.OK:
            carb.log_error("Could not write the thumbnail image file.")
            return

    def destroy(self):
        _reset_default_attrs(self)
