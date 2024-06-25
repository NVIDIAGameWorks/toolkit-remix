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
from typing import Optional, Tuple

import omni.ui as ui
import omni.usd
from omni.flux.utils.common import async_wrap as _async_wrap

from .text_to_image import Rotation as _Rotation
from .text_to_image import generate_image_from_text as _generate_image_from_text


def __generate_image(
    text: str,
    style_name: str,
    remove_offset: bool = True,
    offset_divider: int = 1,
    max_width: int = 0,
    max_height: int = 0,
    font_size_multiply: float = 1.0,
    multiline_if_max_width: bool = True,
    quality_multiplier: int = 2,
    ext_name: Optional[str] = None,
    rotation: _Rotation = None,
):
    text = "" if text is None else str(text)
    dpi = ui.Workspace.get_dpi_scale()

    style = ui.Style.get_instance()
    font_size = int(style.default[f"ImageWithProvider::{style_name}"]["font_size"])
    font = style.default[f"ImageWithProvider::{style_name}"]["image_url"]
    (width_image, height_image), image, size = _generate_image_from_text(
        text,
        font,
        int(font_size * font_size_multiply),
        remove_offset=remove_offset,
        offset_divider=offset_divider,
        max_width=max_width,
        max_height=max_height,
        size_multiplier=dpi * quality_multiplier,
        multiline_if_max_width=multiline_if_max_width,
        ext_name=ext_name,
        rotation=rotation,
    )

    pixels = [int(c) for p in image.getdata() for c in p]
    size = (size[0] / (dpi * quality_multiplier), size[1] / (dpi * quality_multiplier))
    return width_image, height_image, pixels, size


@omni.usd.handle_exception
async def __deferred_create_label_with_font(
    text: str,
    style_name: str,
    image: ui.ImageWithProvider,
    images_provider: ui.ByteImageProvider,
    remove_offset: bool = True,
    offset_divider: int = 1,
    max_width: int = 0,
    max_height: int = 0,
    custom_image_height: ui.Length = None,
    font_size_multiply: float = 1.0,
    multiline_if_max_width: bool = True,
    quality_multiplier: int = 2,
    ext_name: Optional[str] = None,
    rotation: _Rotation = None,
):
    def do_it():
        return __generate_image(
            text,
            style_name,
            remove_offset=remove_offset,
            offset_divider=offset_divider,
            max_width=max_width,
            max_height=max_height,
            font_size_multiply=font_size_multiply,
            quality_multiplier=quality_multiplier,
            multiline_if_max_width=multiline_if_max_width,
            ext_name=ext_name,
            rotation=rotation,
        )

    wrapped_fn = _async_wrap(do_it)
    result_width_image, result_height_image, result_pixels, result_size = await wrapped_fn()
    image.width = ui.Pixel(result_size[0])
    image.height = ui.Pixel(result_size[1]) if custom_image_height is None else custom_image_height
    images_provider.set_bytes_data(result_pixels, [result_width_image, result_height_image])


def create_label_with_font(
    text: str,
    style_name: str,
    remove_offset: bool = True,
    offset_divider: int = 1,
    max_width: int = 0,
    max_height: int = 0,
    custom_image_height: ui.Length = None,
    font_size_multiply: float = 1.0,
    deferred: bool = False,
    multiline_if_max_width: bool = True,
    tooltip: str = None,
    quality_multiplier: int = 2,
    ext_name: Optional[str] = None,
    rotation: _Rotation = None,
) -> Tuple[ui.ByteImageProvider, ui.ImageWithProvider, Optional[asyncio.Task]]:
    """
    Create a label with a custom font

    Args:
        text: the text to show
        style_name: the style name of the text label used with an ui.ImageWithProvider
        remove_offset: remove the offset on the top and left of the text
        offset_divider: divide the offset length on the top and left of the text
        max_width: the max width of the final widget
        max_height: the max height of the final widget
        custom_image_height: set a custom height of the final widget
        font_size_multiply: multiply the font size by this number
        deferred: build the widget async
        multiline_if_max_width: if max_width is specify and the text is longer, create a multiline
        tooltip: tool tip to add on the widget
        quality_multiplier: internal multiplier of the text size to have a better quality
        ext_name: the name of the resource extension. If not specify,
            /exts/omni.flux.utils.widget/default_resources_ext setting will be used.
        rotation: rotate the text or not

    Returns:
        The image provider, the image, and the task if "deferred" is True
    """
    if deferred:
        images_provider = ui.ByteImageProvider()
        image = ui.ImageWithProvider(images_provider, name=style_name)
        image.set_computed_content_size_changed_fn(lambda: (images_provider))
        if tooltip:
            image.set_tooltip(tooltip)
        task_object = asyncio.ensure_future(
            __deferred_create_label_with_font(
                text,
                style_name,
                image,
                images_provider,
                remove_offset=remove_offset,
                offset_divider=offset_divider,
                max_width=max_width,
                max_height=max_height,
                custom_image_height=custom_image_height,
                font_size_multiply=font_size_multiply,
                quality_multiplier=quality_multiplier,
                multiline_if_max_width=multiline_if_max_width,
                ext_name=ext_name,
                rotation=rotation,
            )
        )
        return images_provider, image, task_object
    width_image, height_image, pixels, size = __generate_image(
        text,
        style_name,
        remove_offset=remove_offset,
        offset_divider=offset_divider,
        max_width=max_width,
        max_height=max_height,
        font_size_multiply=font_size_multiply,
        quality_multiplier=quality_multiplier,
        multiline_if_max_width=multiline_if_max_width,
        ext_name=ext_name,
        rotation=rotation,
    )
    images_provider = ui.ByteImageProvider()
    image = ui.ImageWithProvider(
        images_provider,
        width=size[0],
        height=size[1] if custom_image_height is None else custom_image_height,
        name=style_name,
    )
    image.set_computed_content_size_changed_fn(lambda: (images_provider))
    if tooltip:
        image.set_tooltip(tooltip)
    images_provider.set_bytes_data(pixels, [width_image, height_image])
    return images_provider, image, None
