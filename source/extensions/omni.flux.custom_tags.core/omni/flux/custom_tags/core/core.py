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

import re
from contextlib import nullcontext

import omni.kit.commands
import omni.kit.undo
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

# Required to register commands
from omni.kit.core.collection import commands as _usd_commands  # noqa F401
from pxr import Sdf, Usd


class CustomTagsCore:
    def __init__(self, context_name: str = ""):
        self._default_attrs = {
            "_context_name": None,
            "_stage": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._stage = omni.usd.get_context(self._context_name).get_stage()

    @staticmethod
    def get_tag_name(tag_path: Sdf.Path) -> str | None:
        """
        Get the tag name from the Prim Path

        Args:
            tag_path: The prim path to the tag (USD Collection)

        Returns:
            The tag name if one is found, None otherwise
        """
        tag_name = Sdf.Path.StripNamespace(tag_path.name)
        return tag_name if tag_name != tag_path.name else None

    @staticmethod
    def increment_tag_name(new_tag_name: str, existing_tag_names: list[str]) -> str:
        """
        Increment the tag name to a unique name if required, otherwise return the same tag name.

        Incremented tag names will have the format: `tag_name_01` where `_01` is the incremented suffix.

        Args:
            new_tag_name: The desired tag name for the new collection
            existing_tag_names: A list of existing tag names

        Returns:
            A unique tag name
        """
        while new_tag_name in existing_tag_names:
            match = re.search(r"(.*?)(?:_(\d+))?$", new_tag_name)
            prefix, number = match.groups()

            if number is None:
                new_tag_name = f"{prefix}_01"
            else:
                incremented_number = int(number) + 1
                new_tag_name = f"{prefix}_{incremented_number:02}"

        return new_tag_name

    def get_unique_tag_path(
        self,
        new_tag_name: str,
        current_tag_path: Sdf.Path | None = None,
        existing_tag_paths: list[Sdf.Path] | None = None,
    ) -> Sdf.Path:
        """
        Get a unique tag path based on a tag name.

        Can also be used to get a renamed tag's path.

        Will ensure that the returned path is unused if the `existing_tag_paths` argument is provided.

        Args:
            new_tag_name: The new tag's desired name
            current_tag_path: The full Prim Path to the tag to be renamed
            existing_tag_paths: The list of existing tags to compare against when incrementing the new tag's name

        Returns:
             A unique Prim Path for the new tag
        """
        if existing_tag_paths:
            new_tag_name = self.increment_tag_name(
                new_tag_name, [self.get_tag_name(tag_path) for tag_path in existing_tag_paths]
            )

        if current_tag_path:
            return current_tag_path.ReplaceName(
                current_tag_path.name.replace(self.get_tag_name(current_tag_path), new_tag_name)
            )

        return self._get_tags_base_path().AppendProperty(f"collection:{new_tag_name}")

    def get_all_tags(self) -> list[Sdf.Path]:
        """
        Get all available tags in the current stage

        Returns:
            A list of Prim Paths for the existing Tags (USD Collections)
        """
        if not self._stage:
            return []

        tags_prim = self._stage.GetPrimAtPath(self._get_tags_base_path())
        if not tags_prim.IsValid():
            return []
        return [collection.GetCollectionPath() for collection in Usd.CollectionAPI.GetAllCollections(tags_prim)]

    def get_prim_tags(self, prim: Usd.Prim) -> list[Sdf.Path]:
        """
        Get all the tags assigned to a given prim

        Args:
            prim: The prim to get tags for

        Returns:
            A list of Prim Paths for the tags (USD Collections) assigned to the prim
        """
        item_tags = []

        if not self._stage:
            return item_tags

        for tag_path in self.get_all_tags():
            if not self.prim_has_tag(prim, tag_path):
                continue
            item_tags.append(tag_path)

        return item_tags

    def prim_has_tag(self, prim: Usd.Prim, tag_path: Sdf.Path) -> bool:
        """
        A utility function to check if a prim was assigned a given tag

        Args:
            prim: The prim to evaluate
            tag_path: The Prim Path to the tag to evaluate

        Returns:
            True if the prim is assigned the given tag, False otherwise
        """
        if not prim:
            return False
        return (
            Usd.CollectionAPI.GetCollection(self._stage, tag_path)
            .ComputeMembershipQuery()
            .IsPathIncluded(prim.GetPath())
        )

    def create_tag(self, tag_name: str, use_undo_group: bool = True):
        """
        Create a new tag in the current stage.

        This method will also create the `/CustomTags` prim if it doesn't exist,

        Args:
            tag_name: The name of the tag (USD Collection) to create
            use_undo_group: Whether an undo group should be used or not.
                            If the method if already part of an undo group, this should be set to False.
        """
        with Usd.EditContext(self._stage, self._stage.GetRootLayer()):
            with omni.kit.undo.group() if use_undo_group else nullcontext():
                # If the base prim doesn't already exist, create it
                path = str(self._get_tags_base_path())
                prim = self._stage.GetPrimAtPath(path)
                if not prim.IsValid():
                    omni.kit.commands.execute(
                        "CreatePrimCommand",
                        prim_path=path,
                        prim_type="Scope",
                        select_new_prim=False,
                        context_name=self._context_name,
                    )
                # Create the collection
                _, collection_path = omni.kit.commands.execute(
                    "CreateCollection",
                    prim_path=path,
                    collection_name=tag_name,
                    usd_context_name=self._context_name,
                )
                # Set the expansion rule to not automatically include children
                Usd.CollectionAPI.GetCollection(self._stage, collection_path).CreateExpansionRuleAttr("explicitOnly")

    def rename_tag(self, tag_path: Sdf.Path | str, new_tag_name: str):
        """
        Rename an existing tag (USD Collection)

        Args:
            tag_path: The existing tag's Prim Path
            new_tag_name: The new name that should be given to the existing tag
        """
        with Usd.EditContext(self._stage, self._stage.GetRootLayer()):
            omni.kit.commands.execute(
                "RenameCollection",
                old_collection_path=str(tag_path),
                new_collection_name=new_tag_name,
                usd_context_name=self._context_name,
            )

    def delete_tags(self, tag_paths: list[Sdf.Path | str], use_undo_group: bool = True):
        """
        Delete some tags available in the current stage

        Args:
            tag_paths: A list of Prim Paths to the tags (USD Collection) to delete
            use_undo_group: Whether an undo group should be used or not.
                            If the method if already part of an undo group, this should be set to False.
        """
        with Usd.EditContext(self._stage, self._stage.GetRootLayer()):
            with omni.kit.undo.group() if use_undo_group else nullcontext():
                for tag_path in tag_paths:
                    omni.kit.commands.execute(
                        "DeleteCollection", collection_path=str(tag_path), usd_context_name=self._context_name
                    )

    def add_tag_to_prim(self, prim_path: Sdf.Path | str, tag_path: Sdf.Path | str):
        """
        Assign a tag to a given prim

        This will add the prim to the tag's USD Collection

        Args:
            prim_path: The prim to assign the tag to
            tag_path: The Prim Path of the tag to assign
        """
        with Usd.EditContext(self._stage, self._stage.GetRootLayer()):
            omni.kit.commands.execute(
                "AddItemToCollection",
                path_to_add=str(prim_path),
                collection_path=str(tag_path),
                usd_context_name=self._context_name,
            )

    def remove_tag_from_prim(self, prim_path: Sdf.Path | str, tag_path: Sdf.Path | str):
        """
        Unassign a tag from a given prim

        This will remove the prim from the tag's USD Collection

        Args:
            prim_path: The prim to unassign the tag from
            tag_path: The Prim Path of the tag to unassign
        """
        with Usd.EditContext(self._stage, self._stage.GetRootLayer()):
            omni.kit.commands.execute(
                "RemoveItemFromCollection",
                prim_or_prop_path=str(prim_path),
                collection_path=str(tag_path),
                usd_context_name=self._context_name,
            )

    def _get_tags_base_path(self) -> Sdf.Path:
        """
        Get the Prim Path to the tag's Prim

        Returns:
            A Path to the Prim holding all the tags (USD Collections)
        """
        suffix = "/CustomTags"

        if not self._stage:
            return Sdf.Path(suffix)

        return Sdf.Path(
            f"{str(self._stage.GetDefaultPrim().GetPath()) if self._stage.HasDefaultPrim() else ''}{suffix}"
        )

    def destroy(self):
        _reset_default_attrs(self)
