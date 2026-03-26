"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

CurveEditorLayout -- Standard dict schema for the curve editor's hierarchy panel.

The curve editor is agnostic of USD, property panels, or any domain.
Consumers build a CurveEditorLayout dict describing the hierarchy of curves
to display. The editor uses it to render a TreeView with visibility toggles
and color swatches. Curve IDs are opaque strings passed to CurveModel as-is.
"""

from __future__ import annotations

from typing import TypedDict


class _CurveEntryRequired(TypedDict):
    id: str
    display_name: str


class CurveEntry(_CurveEntryRequired, total=False):
    """A leaf curve in the hierarchy."""

    display_color: int  # optional -- 0xAARRGGBB, overrides inherited color


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
