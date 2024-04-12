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
from typing import List

import omni.kit.commands
from pxr import Sdf, Usd

__registered = [False]  # match the number of commands to register


def _commands_changed():
    global __registered
    if all(__registered):
        return
    command_list = omni.kit.commands.get_commands()
    if "ReferenceCommandBase" in command_list:
        __registered = [True]

        class SetExplicitReferencesCommand(omni.kit.commands.get_command_class("ReferenceCommandBase")):
            def __init__(self, stage, prim_path: "Sdf.Path", reference: "Sdf.Reference", to_set: List["Sdf.Reference"]):
                super().__init__(stage, prim_path, reference)
                self.__to_set = to_set

            def do(self):
                references = self._get_references()
                if references:
                    self._save_current_reference_list()
                    references.SetReferences(self.__to_set)

            def undo(self):
                self._restore_saved_reference_list()
                self._restore_empty_spec()

            def _restore_empty_spec(self):
                stage = self._stage()
                if stage:
                    prim_spec = stage.GetEditTarget().GetLayer().GetPrimAtPath(self._prim_path)
                    if (
                        prim_spec
                        and self._reference_list
                        and not self._reference_list.explicitItems[:]
                        and not self._reference_list.addedItems[:]
                        and not self._reference_list.prependedItems[:]
                        and not self._reference_list.appendedItems[:]
                        and not self._reference_list.deletedItems[:]
                        and not self._reference_list.orderedItems[:]
                    ):
                        prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, Sdf.ReferenceListOp())

        omni.kit.commands.register(SetExplicitReferencesCommand)


def __register():
    omni.kit.commands.subscribe_on_change(_commands_changed)


__register()


class SetPrimTypeName(omni.kit.commands.Command):
    """
    Set the type of a prim

    Args:
        prim (Usd.Prim): Prim to be changed.
        type_name (str): the type to set the prim to (i.e. "Xform")
    """

    def __init__(self, prim: Usd.Prim, type_name: str):
        self._prim = prim
        self._type_name = type_name
        self._old_type_name = None

    def do(self):
        if self._prim:
            self._old_type_name = self._prim.GetTypeName()
            self._prim.SetTypeName(self._type_name)

    def undo(self):
        self._prim.SetTypeName(self._old_type_name)
