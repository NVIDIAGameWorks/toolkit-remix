"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

CurveEditorLayout -- Standard dict schema for the curve editor's hierarchy panel.

The curve editor is agnostic of USD, property panels, or any domain.
Consumers build a CurveEditorLayout dict describing the hierarchy of curves
to display. The editor uses it to render a TreeView with native channel selection
and colored labels. Curve IDs are opaque strings passed to GroupedKeysModel as-is.
"""

from __future__ import annotations

from typing import TypedDict


class _CurveEntryRequired(TypedDict):
    id: str
    display_name: str


class CurveEntry(_CurveEntryRequired, total=False):
    """A leaf curve with a normal color and an optional label style name.

    ``display_color`` uses 0xAABBGGRR and overrides inherited label and curve colors.
    ``label_style_name`` selects a label style without resolving the normal color.
    """

    display_color: int
    label_style_name: str


class CurveEditorLayout(TypedDict, total=False):
    """Recursive node in the curve hierarchy.

    Each node can have sub-groups (``children``) and/or leaf curves (``curves``).
    ``display_color`` is inherited by descendants that don't override it.
    """

    display_name: str
    tooltip: str
    display_color: int
    children: dict[str, CurveEditorLayout]
    curves: list[CurveEntry]
