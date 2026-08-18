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

__all__ = ["TextureResolverBase"]

import dataclasses
import pathlib
from typing import ClassVar

from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from pxr import Usd

from ...enums import RemixType
from ...texture import iter_texture_paths_for_prim
from ..base import ResolverParameter, ResolverValueError, ValueResolver

# The dropdown offers real texture inputs only; OTHER is a diffuse fallback, not a selectable type.
SELECTABLE_TEXTURE_TYPES = tuple(
    texture_type for texture_type in TextureTypes if texture_type is not TextureTypes.OTHER
)


@dataclasses.dataclass
class TextureResolverBase(ValueResolver[pathlib.Path]):
    """Resolve exactly one material texture path from a prim's shader inputs.

    Concrete texture getters share this per-material resolution and differ only in
    which materials a submission runs against. The ``texture_type`` field selects
    which material input to read and defaults to the canonical diffuse input used
    by the current workflows. Add a new texture getter by subclassing this base,
    setting ``name`` and ``label``, and registering it in
    ``resolvers.textures.TEXTURE_RESOLVER_PLUGINS``.
    """

    remix_types: ClassVar[tuple[RemixType, ...]] = (RemixType.TEXTURE_FILE_PATH,)
    texture_type: TextureTypes = TextureTypes.DIFFUSE
    context_name: str | None = None

    @classmethod
    def create(cls, default_value: object, context_name: str | None = None) -> "TextureResolverBase":
        """Create a texture resolver bound to its owning USD context.

        Args:
            default_value: Authored workflow value unused by semantic texture resolution.
            context_name: USD context containing the selected material.

        Returns:
            Texture resolver bound to the supplied context.
        """
        return cls(context_name=context_name)

    @property
    def parameters(self) -> tuple[ResolverParameter[TextureTypes], ...]:
        """Return the editable texture type binding.

        Returns:
            Single binding that selects the material texture input to resolve.
        """
        return (
            ResolverParameter(
                "texture_type",
                TextureTypes,
                lambda: self.texture_type,
                self._set_texture_type,
                SELECTABLE_TEXTURE_TYPES,
                "Texture Type",
                tooltip="The material texture type to read and send to the workflow.",
            ),
        )

    def _set_texture_type(self, value: TextureTypes) -> None:
        """Store the material texture type selected by the user.

        Args:
            value: Material texture type to resolve from future selections.
        """
        self.texture_type = value

    def __call__(self, prim: Usd.Prim) -> pathlib.Path:
        """Resolve exactly one material texture path.

        Args:
            prim: USD prim whose bound material supplies the texture.

        Returns:
            Resolved path of the material texture.

        Raises:
            ResolverValueError: If the resolver has no context or the texture count is not exactly one.
        """
        if self.context_name is None:
            raise ResolverValueError("The selected texture could not be read. Reopen the project and try again.")
        prim_path = str(prim.GetPath())
        input_name = TEXTURE_TYPE_INPUT_MAP.get(self.texture_type)
        if input_name is None:
            raise ResolverValueError(
                "The selected texture type is not supported. Choose a different texture type and try again."
            )
        texture_paths = tuple(
            dict.fromkeys(
                iter_texture_paths_for_prim(
                    prim_path,
                    context_name=self.context_name,
                    texture_type=input_name,
                )
            )
        )
        texture_label = self.texture_type.value
        if " - " in texture_label:
            texture_name, texture_variant = texture_label.split(" - ", maxsplit=1)
            texture_label = f"{texture_name} ({texture_variant})"
        texture_label = texture_label[0].lower() + texture_label[1:]
        if not texture_paths:
            raise ResolverValueError(f"This material has no {texture_label} texture.")
        if len(texture_paths) > 1:
            raise ResolverValueError(
                f"This material has {len(texture_paths)} {texture_label} textures. "
                "Choose a getter that returns one texture file."
            )
        return pathlib.Path(texture_paths[0])
