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

__all__ = (
    "copy",
    "iter_clipboard_changes",
    "paste",
)

import json
from collections.abc import Iterable, Iterator

import omni.kit.clipboard
import omni.kit.undo
from omni.flux.utils.common import Serializer as _Serializer

from .model import Item as _Item

SERIALIZER = _Serializer()


def iter_clipboard_changes(items: Iterable[_Item]) -> Iterator[tuple[_Item, dict]]:
    """
    Yields items from relevant serialized items from the clipboard.

    This method pairs chunks of clipboard data along with the relevant item from `items`.
    """
    try:
        datas = SERIALIZER.loads(omni.kit.clipboard.paste())
    except (TypeError, json.decoder.JSONDecodeError):
        return

    if not isinstance(datas, list):
        return

    for item in items:
        for data in datas:
            if item.matches_serialized_data(data):
                yield item, data
                break


def copy(items: Iterable[_Item]) -> None:
    """
    Copy the model items to the clipboard.
    """
    data = [x.serialize() for x in items]
    omni.kit.clipboard.copy(SERIALIZER.dumps(data))


def paste(items: Iterable[_Item]):
    """
    Paste clipboard data to relevant model items.
    """
    with omni.kit.undo.group():
        for item, serialized_item in iter_clipboard_changes(items):
            item.apply_serialized_data(serialized_item)
