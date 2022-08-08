"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import collections.abc
import os
from typing import Callable

import carb
import omni.client
import omni.usd
from pxr import Sdf, Usd, UsdUtils


def deep_update_data(d, u):  # noqa PLC0103
    for k, v in u.items():  # noqa PLC0103
        if isinstance(v, collections.abc.Mapping):
            d[k] = deep_update_data(d.get(k, {}), v)
        elif isinstance(v, list):
            d[k] = d.get(k, []) + v
        else:
            d[k] = v
    return d


class PathsToRelative:
    @staticmethod
    def _ref_to_relative(chk, item):
        str_value = str(item.assetPath)
        # check if exist
        skip = False
        if not os.path.exists(str_value):
            # try to find the texture next to the usd or sub folder?
            base_name_text = os.path.basename(str_value)
            if base_name_text[-1:] == "@":
                base_name_text = base_name_text[:-1]
            skip = True
            for root, _, files in os.walk(os.path.dirname(chk)):
                for name in files:
                    if name == base_name_text:
                        str_value = os.path.join(root, name)
                        skip = False
                        break
                if not skip:
                    break
        if not skip:
            # for whatever reason, this doesnt work. Need to use omni.client (?)
            # result = Sdf.ComputeAssetPathRelativeToLayer(layer, str_value)
            result = omni.client.make_relative_url(chk, str_value)
            return Sdf.Reference(
                assetPath=result,
                primPath=item.primPath,
                layerOffset=item.layerOffset,
            )
        return None

    @staticmethod  # noqa C901
    @omni.usd.handle_exception
    async def convert_current_stage(
        context=None,
        progress_callback: Callable[[float], None] = None,
        scan_only: bool = True,
        only_data=None,
        show_print=True,
    ):
        def traverse_instanced_children(prim):
            for child in prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate):
                yield child
                yield from traverse_instanced_children(child)

        usd_path_errors = {}
        mdl_path_errors = {}
        texture_path_errors = {}

        if context is None:
            context = omni.usd.get_context()
        stage = context.get_stage()

        usd = stage.GetRootLayer().identifier
        path = Sdf.AssetPath(usd)
        layers, _, _ = UsdUtils.ComputeAllDependencies(path)
        to_add = 100 / len(layers)
        global_progress = 0.0
        last_progress_int = 0
        if progress_callback:
            progress_callback(global_progress)
        doublon = {}

        data = {}

        save_errors = ""

        for layer in layers:  # noqa PLR1702
            to_save_layer = False
            chk = layer.identifier
            # we skip the root layer if there are sublayers
            if chk == path and len(layers) > 1:
                continue

            if only_data and chk not in only_data:
                continue

            sub_stage = Usd.Stage.Open(chk)
            all_prims = list(traverse_instanced_children(sub_stage.GetPseudoRoot()))

            for prim in all_prims:
                if prim.GetTypeName() in ["Shader"]:
                    if progress_callback:
                        global_progress += to_add / len(all_prims)
                        if int(global_progress) != last_progress_int:
                            await asyncio.sleep(0.001)
                            last_progress_int = int(global_progress)
                            progress_callback(global_progress / 100)

                    for attr in prim.GetAttributes():

                        if only_data and str(attr.GetPath()) not in only_data[chk]:
                            continue

                        layers = [
                            x.layer.identifier
                            for x in attr.GetPropertyStack(Usd.TimeCode.Default())
                            if x.layer.identifier.strip()
                        ]
                        if chk not in layers:
                            # ignore things that are not overridden in the current layer or part of the current layer
                            continue

                        if attr.GetName() == "info:mdl:sourceAsset":
                            if ":/" in str(attr.Get()):
                                # Not relative path
                                key = f"{chk}::{prim.GetPath().pathString}::{attr.GetName()}"
                                mdl_path_errors[key] = f"ERROR: {attr.GetName()} has absolute MDL path: {attr.Get()}"
                                result = os.path.basename(str(attr.Get()))
                                if result[-1:] == "@":
                                    result = result[:-1]
                                if show_print:
                                    carb.log_info(f"From layer {chk}        {prim.GetPath().pathString}\n")
                                    carb.log_info(f"    {attr.Get()}\n  -->\n   {result}\n" + "=" * 30)
                                if not scan_only:
                                    attr.Set(result)
                                deep_update_data(
                                    data, {chk: {"attr": {str(attr.GetPath()): {str(attr.Get()): result}}}}
                                )
                                to_save_layer = True
                            if "\\" in str(attr.Get()):
                                # Incorrect slash direction
                                key = f"{chk}::{prim.GetPath().pathString}::{attr.GetName()}"
                                mdl_path_errors[key] = (
                                    f"ERROR: {attr.GetName()} has incorrect slash(es). "
                                    f"Needs to be forward slash: {attr.Get()}"
                                )
                                result = os.path.basename(str(attr.Get()))
                                if result[-1:] == "@":
                                    result = result[:-1]
                                if show_print:
                                    carb.log_info(f"From layer {chk}        {prim.GetPath().pathString}\n")
                                    carb.log_info(f"    {attr.Get()}\n  -->\n   {result}\n" + "=" * 30)
                                if not scan_only:
                                    attr.Set(result)
                                deep_update_data(
                                    data, {chk: {"attr": {str(attr.GetPath()): {str(attr.Get()): result}}}}
                                )
                                to_save_layer = True
                        else:
                            if ":/" in str(attr.Get()):
                                key = f"{chk}::{prim.GetPath().pathString}::{attr.GetName()}"
                                texture_path_errors[
                                    key
                                ] = f"ERROR: {attr.GetName()} has absolute asset path: {str(attr.Get())}"
                                str_value = str(attr.Get())
                                # check if exist
                                skip = False
                                if not os.path.exists(str_value):
                                    # try to find the texture next to the usd or sub folder?
                                    base_name_text = os.path.basename(str_value)
                                    if base_name_text[-1:] == "@":
                                        base_name_text = base_name_text[:-1]
                                    skip = True
                                    for root, _, files in os.walk(os.path.dirname(chk)):
                                        for name in files:
                                            if name == base_name_text:
                                                str_value = os.path.join(root, name)
                                                skip = False
                                                break
                                        if not skip:
                                            break
                                if not skip:
                                    # for whatever reason, this doesnt work. Need to use omni.client (?)
                                    # result = Sdf.ComputeAssetPathRelativeToLayer(layer, str_value)
                                    result = omni.client.make_relative_url(chk, str_value)
                                    if show_print:
                                        carb.log_info(f"From layer {chk}        {prim.GetPath().pathString}\n")
                                        carb.log_info(f"    {attr.Get()}\n  -->\n   {result}\n" + "=" * 30)
                                    if not scan_only:
                                        attr.Set(result)
                                    deep_update_data(
                                        data, {chk: {"attr": {str(attr.GetPath()): {str(attr.Get()): result}}}}
                                    )
                                    to_save_layer = True
                                    if result not in doublon:
                                        doublon[os.path.basename(result)] = [chk]
                                    else:
                                        doublon[os.path.basename(result)].append(chk)
                                else:  # can't find relative path
                                    if show_print:
                                        carb.log_info(f"From layer {chk}\n")
                                        carb.log_info(
                                            f"    {attr.Get()}\n  -->\n   Can't find relative path\n" + "=" * 30
                                        )
                for primspec in prim.GetPrimStack():
                    if not primspec:
                        continue
                    if not primspec.referenceList:
                        continue
                    if primspec.layer and primspec.layer.identifier != chk:
                        # ignore things that are not overridden in the current layer or part of the current layer
                        continue
                    # Checking USDA
                    items = primspec.referenceList.explicitItems
                    result_items = []
                    new_ref = False
                    for item in items:
                        if item is not None and ":/" in item.assetPath:
                            if only_data and str(prim.GetPath().pathString) + str(item.assetPath) not in only_data[chk]:
                                continue
                            key = f"{chk}::{prim.GetPath().pathString}"
                            usd_path_errors[
                                key
                            ] = f"ERROR: {prim.GetName()} has absolute reference path: {item.assetPath}"
                            result = PathsToRelative._ref_to_relative(chk, item)
                            if result:
                                result_items.append((item, result))
                                new_ref = True
                                if show_print:
                                    carb.log_info(f"From layer {chk}        {prim.GetPath().pathString}\n")
                                    carb.log_info(f"    {item.assetPath}\n  -->\n   {result.assetPath}\n" + "=" * 30)
                            else:  # can't find the relative path, keep
                                result_items.append((item, item))
                        else:
                            result_items.append((item, item))
                        if new_ref:
                            to_save_layer = True
                            if not scan_only:
                                primspec.referenceList.explicitItems = [result_item[1] for result_item in result_items]
                            deep_update_data(
                                data,
                                {
                                    chk: {
                                        "ref": {
                                            prim.GetPath().pathString: {
                                                primspec.referenceList.explicitItems: {
                                                    result_item[0]: result_item[1] for result_item in result_items
                                                }
                                            }
                                        }
                                    }
                                },
                            )

                    # Checking USD
                    items = primspec.referenceList.prependedItems
                    result_items = []
                    new_ref = False
                    for item in items:
                        if item is not None and ":/" in item.assetPath:
                            if only_data and str(prim.GetPath().pathString) + str(item.assetPath) not in only_data[chk]:
                                continue
                            key = f"{chk}::{prim.GetPath().pathString}"
                            usd_path_errors[
                                key
                            ] = f"ERROR: {prim.GetName()} has absolute reference path: {item.assetPath}"

                            result = PathsToRelative._ref_to_relative(chk, item)
                            if result:
                                result_items.append((item, result))
                                new_ref = True
                                if show_print:
                                    carb.log_info(f"From layer {chk}        {prim.GetPath().pathString}\n")
                                    carb.log_info(f"    {item.assetPath}\n  -->\n   {result.assetPath}\n" + "=" * 30)
                            else:  # can't find the relative path, keep
                                result_items.append((item, item))
                        else:
                            result_items.append((item, item))
                        if new_ref:
                            to_save_layer = True
                            if show_print:
                                carb.log_info(("5" * 50), to_save_layer, scan_only)
                            if not scan_only:
                                primspec.referenceList.prependedItems = [result_item[1] for result_item in result_items]
                            deep_update_data(
                                data,
                                {
                                    chk: {
                                        "ref": {
                                            prim.GetPath().pathString: {
                                                primspec.referenceList.prependedItems: {
                                                    result_item[0]: result_item[1] for result_item in result_items
                                                }
                                            }
                                        }
                                    }
                                },
                            )

            if to_save_layer and not scan_only:
                if show_print:
                    carb.log_info(f"Save layer {chk}")
                try:
                    sub_stage.Save()
                except Exception:  # noqa PLW0703
                    save_errors += f"Can't save {chk}. Read only?\n"
        for tex, lays in doublon.items():
            if len(lays) > 1 and show_print:
                carb.log_info(("Doublon", tex, lays))
        # reload
        await context.open_stage_async(usd)
        return data, save_errors
