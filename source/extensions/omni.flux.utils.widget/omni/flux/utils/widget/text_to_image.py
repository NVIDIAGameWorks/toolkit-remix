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

import math
from enum import Enum as _Enum
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .resources import get_font_list as _get_font_list


class Rotation(_Enum):
    LEFT_90 = "Left90"
    RIGHT_90 = "Right90"


def generate_image_from_text(
    text: str,
    font_path: str,
    size: int,
    remove_offset: bool = True,
    offset_divider: int = 1,
    max_width: int = 0,
    max_height: int = 0,
    size_multiplier: float = 1,
    multiline_if_max_width: bool = True,
    ext_name: Optional[str] = None,
    rotation: Rotation = None,
):
    """
    Generate an image from a text

    Args:
        text: the text to show
        font_path: the font path
        size: the size of the font to use
        remove_offset: if True, it will remove the padding at the top of the font
        offset_divider: to add more padding at the top
        max_width: max width of the final text
        max_height: max height of the final text
        size_multiplier: multiply the font size
        multiline_if_max_width: if the text is bigger than the max width, do multiline or not
        ext_name: the name of the resource extension. If not specify,
            /exts/omni.flux.utils.widget/default_resources_ext setting will be used.
        rotation: rotate the text or not
    """
    font_list = _get_font_list(ext_name=ext_name)
    if str(Path(font_path)) not in font_list.values():
        raise ValueError(f"Can't find the font {font_path}")
    # double the size to have a better resolution
    font = ImageFont.truetype(font_path, int(size * size_multiplier))
    _, _, right, bottom = font.getbbox(text)
    default_size = (right, bottom)
    size = default_size
    final_text = ""
    final_off_x, final_off_y = 0, 0
    is_multiline = False
    if max_width != 0 and size[0] > max_width and multiline_if_max_width:
        width_of_line = 0
        for i, token in enumerate(text.split()):
            token += " "
            left, top, _, _ = font.getbbox(token)
            token_width = font.getlength(token)
            offset_value = (left, top)
            if i == 0 and remove_offset and rotation is None:
                final_off_y += offset_value[1]
            if width_of_line + token_width < max_width:
                if max_height != 0 and size[1] + default_size[1] + offset_value[1] > max_height:
                    final_text += "..."
                    width_of_line += font.getlength("...")
                    break
                final_text += token
                width_of_line += token_width
            else:
                is_multiline = True
                if remove_offset and rotation is None:
                    final_off_y += offset_value[1]
                width_of_line = token_width
                final_text += f"\n{token}"
                size = (max_width, size[1] + default_size[1] + offset_value[1])
    elif not multiline_if_max_width:
        end_text_width = font.getlength("...")
        final_text = ""
        current_width = 0
        for letter in text:
            current_width += font.getlength(letter)
            final_text += letter
            if current_width > max_width - end_text_width - font.getlength(letter):
                final_text += "..."
                break
        size = (max_width, size[1])
        if remove_offset and rotation is None:
            final_off_x, final_off_y, _, _ = font.getbbox(final_text)
    else:
        final_text = text
        if remove_offset and rotation is None:
            final_off_x, final_off_y, _, _ = font.getbbox(final_text)
    # round to multiple of 2 to have a sharp text
    size = (2 * math.ceil(size[0] / 2), 2 * math.ceil(size[1] / 2))
    image = Image.new("RGBA", size)
    img_draw = ImageDraw.Draw(image)
    if is_multiline:
        _, top, _, _ = font.getbbox(final_text)
        spacing = top * 2
        img_draw.multiline_text(
            (0 - final_off_x // offset_divider, 0 - final_off_y // offset_divider),
            final_text,
            fill="white",
            spacing=spacing,
            font=font,
        )
    else:
        img_draw.text(
            (0 - final_off_x // offset_divider, 0 - final_off_y // offset_divider), final_text, fill="white", font=font
        )
    if rotation is not None:
        if rotation == Rotation.RIGHT_90:
            image = image.rotate(90, expand=True)
        elif rotation == Rotation.LEFT_90:
            image = image.rotate(-90, expand=True)
        size = (2 * math.ceil(image.size[0] / 2), 2 * math.ceil(image.size[1] / 2))
    return ((size[0] - final_off_x // offset_divider), (size[1] - final_off_y // offset_divider)), image, size
