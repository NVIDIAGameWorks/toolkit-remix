"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import weakref
from typing import Union

import omni.client
import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from omni.kit.property.usd.prim_selection_payload import PrimSelectionPayload
from omni.kit.property.usd.references_widget import DEFAULT_PRIM_TAG, PayloadReferenceWidget
from omni.kit.property.usd.usd_property_widget import UsdPropertiesWidget
from pxr import Sdf, Tf, Usd


class MeshAssetWidget(PayloadReferenceWidget):
    def __init__(self, title: str, parent_widget):
        super().__init__()
        self._title = title
        self.__parent_widget = parent_widget
        self._correcting_prim_path = False

    @property
    def title(self):
        return str(self._title)

    def clean(self):
        self.__parent_widget = None
        super().clean()

    def on_new_payload(self, payloads):
        if len(payloads) == 0:
            super().on_new_payload(payloads)
            return False

        stage = payloads.get_stage()

        # the reference widget can only handle one selection
        payload = payloads[0]
        mesh_path = None
        prim = stage.GetPrimAtPath(payload)
        if prim.IsValid() and str(payload).startswith(constants.MESH_PATH):
            mesh_path = payload
        if mesh_path is None:
            return False
        return super().on_new_payload(
            PrimSelectionPayload(weakref.ref(stage), [] if mesh_path is None else [mesh_path])
        )

    def _select_prototype(self):
        paths = [str(p) for p in self._payload]
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(paths, True)

    def build_items(self):
        with ui.VStack(spacing=8):
            ui.Label(
                "Replacing this reference will affect all instances using this mesh.",
                name="label",
                alignment=ui.Alignment.LEFT_TOP,
            )
            super().build_items()
            ui.Button(
                "Select prototype",
                clicked_fn=self._select_prototype,
                tooltip="Select the parent for the scenegraph shared by its associated instance prims",
            )

    def _on_payload_reference_edited(
        self,
        model_or_item,
        stage: Usd.Stage,
        prim_path: Sdf.Path,
        payref: Union[Sdf.Reference, Sdf.Payload],
        intro_layer: Sdf.Layer,
    ):
        if self._correcting_prim_path:
            return False
        new_asset_path = self._ref_dict[payref].asset_path_field.model.get_value_as_string()

        # if the asset path is changing, reset the default prim
        if omni.client.normalize_url(str(payref.assetPath)) != omni.client.normalize_url(new_asset_path):
            self._correcting_prim_path = True
            self._ref_dict[payref].prim_path_field.model.set_value(DEFAULT_PRIM_TAG)
            self._correcting_prim_path = False

        result = super()._on_payload_reference_edited(model_or_item, stage, prim_path, payref, intro_layer)
        # we rebuild the frame of the frame of the parent will still show old stuffs
        self.__parent_widget.request_rebuild()
        return result  # noqa R504


class MeshAssetsWidget(UsdPropertiesWidget):
    def __init__(self, title: str):
        super().__init__(title=title, collapsed=False)
        self.__children_widgets = []
        self.__prototypes_data = {}
        self._listener = None

    def on_new_payload(self, payloads):
        self.__prototypes_data = {}
        self.__children_widgets = []

        if len(payloads) == 0:
            super().on_new_payload(payloads)
            return False

        stage = payloads.get_stage()
        for p in payloads:  # noqa PLR1702
            prim = stage.GetPrimAtPath(p)
            if prim.IsValid():
                if str(p).startswith(constants.INSTANCE_PATH):
                    refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
                    for (ref, _) in refs_and_layers:
                        if not ref.assetPath:
                            if (
                                ref.primPath in self.__prototypes_data
                                and prim.GetPath() not in self.__prototypes_data[ref.primPath]
                            ):
                                self.__prototypes_data[ref.primPath].append(prim.GetPath())
                            else:
                                self.__prototypes_data[ref.primPath] = [prim.GetPath()]

                elif str(p).startswith(constants.MESH_PATH):
                    self.__prototypes_data[p] = [p]

        if not self.__prototypes_data:
            return False

        for proto in self.__prototypes_data:
            widget = MeshAssetWidget(proto, self)
            widget.on_new_payload(PrimSelectionPayload(weakref.ref(stage), [proto]))
            self.__children_widgets.append(widget)
        return super().on_new_payload(payloads)

    def build_items(self):
        self._collapsable_frame.name = "groupFrame"  # to have dark background
        with ui.VStack(spacing=8):
            for widget in self.__children_widgets:
                with ui.CollapsableFrame(
                    title=str(widget.title),
                ):
                    widget.build_items()

        # recreate the tf notice
        if not self._payload:
            return
        last_prim = self._get_prim(self._payload[-1])
        if not last_prim:
            return

        stage = last_prim.GetStage()
        if not stage:
            return
        self._listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_changed, stage)

    def _on_usd_changed(self, notice, stage):
        super()._on_usd_changed(notice, stage)
        if notice.GetResyncedPaths():
            self.request_rebuild()

    def reset(self):
        super().reset()
        self._disable_listener()

    def _disable_listener(self):
        if self._listener:
            self._listener.Revoke()
        self._listener = None

    def clean(self):
        self._disable_listener()
        for children_widget in self.__children_widgets:
            children_widget.clean()
        self.__children_widgets = []
        super().clean()
