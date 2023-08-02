"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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
