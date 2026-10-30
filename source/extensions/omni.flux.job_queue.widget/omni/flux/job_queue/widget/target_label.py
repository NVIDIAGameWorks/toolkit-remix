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

__all__ = ["TargetLabel"]

from omni import ui
from omni.flux.utils.common.path_utils import ElideModes, elide_path

from .constants import ROW_HEIGHT


class TargetLabel(ui.Frame):
    """Show the first target like the Stage Manager, a faded "parent/" then the name, with a bold count of the others.

    When the text does not fit, only the longer of the parent name and the name elides. A tie elides the parent name.
    """

    def __init__(self, targets: tuple[str, ...], identifier: str):
        """Split the first target into its parent name and name.

        Args:
            targets: Full paths returned by the job adapter, all listed in the tooltip.
            identifier: Stable UI lookup identifier of the name label.
        """
        parts = targets[0].replace("\\", "/").rsplit("/", 2) if targets else [""]
        self._ancestor = parts[-2] if len(parts) > 1 else ""
        self._name = parts[-1]
        self._count = f" (+{len(targets) - 1})" if len(targets) > 1 else ""
        self._tooltip = "\n".join(targets)
        self._identifier = identifier
        self._text = self._ancestor
        self._elide_name = False
        self._full_width = 0.0
        self._fitted_width = 0.0
        self._labels: list[ui.Label] = []
        super().__init__(height=ROW_HEIGHT, horizontal_clipping=True, build_fn=self._build)
        self.set_computed_content_size_changed_fn(self._fit)

    def _build(self) -> None:
        """Build the labels. They size to their text, except an elided name, which fills the free space."""
        with ui.HStack(computed_content_size_changed_fn=self._fit):
            self._labels = []
            if self._ancestor:
                self._labels.append(self._build_label(self._text, style_name="FadedLabel", suffix="_ancestor"))
                self._labels.append(self._build_label("/", style_name="FadedLabel", suffix="_slash"))
            if self._name:
                self._labels.append(
                    self._build_label(self._name, style_name="CellLabel", suffix="", elided=self._elide_name)
                )
            if self._count:
                self._labels.append(self._build_label(self._count, style_name="CellLabelBold", suffix="_count"))

    def _build_label(self, text: str, *, style_name: str, suffix: str, elided: bool = False) -> ui.Label:
        """Build one label that sizes to its text, or an elided label that fills the free space.

        Args:
            text: Displayed text.
            style_name: Style name of the label.
            suffix: Suffix appended to the identifier of the target.
            elided: Whether the label elides its text to fit the free space.

        Returns:
            The built label.
        """
        if elided:
            return ui.Label(
                text, name=style_name, elided_text=True, tooltip=self._tooltip, identifier=self._identifier + suffix
            )
        return ui.Label(text, name=style_name, width=0, tooltip=self._tooltip, identifier=self._identifier + suffix)

    def _fit(self) -> None:
        """Elide the longer part when the text does not fit, dropping parent name characters until the row fits."""
        widths = [label.computed_content_width for label in self._labels]
        # Measured once, while nothing is shortened or elided.
        self._full_width = self._full_width or sum(widths)
        if not self._full_width or not self.computed_width:
            return
        text, elide_name = self._ancestor, False
        if self._full_width > self.computed_width:
            if len(self._ancestor) < len(self._name):
                elide_name = True
            elif self.computed_width > self._fitted_width and self._text != self._ancestor:
                # Wider than the last fit: start again from the full parent name.
                self._fitted_width = self.computed_width
            elif sum(widths) > self.computed_width:
                # The parent name sizes to its text, so the slash spacing stays the same as when it fits.
                self._fitted_width = self.computed_width
                text = elide_path(self._ancestor, max(len(self._text) - 1, len("...")), ElideModes.middle)
            else:
                text = self._text
        if (text, elide_name) != (self._text, self._elide_name):
            self._text, self._elide_name = text, elide_name
            self.rebuild()
