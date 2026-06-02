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

__all__ = [
    "accept_asset_if_valid_for_replacement",
    "open_asset_file_picker",
    "open_replacement_asset_file_picker",
]

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING

import omni.client
import omni.kit.app
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared.data_models import (
    AssetReplacementsValidators as _AssetReplacementsValidators,
    ReplacementAssetType,
)
from lightspeed.trex.asset_replacements.core.shared.usd_copier import copy_non_usd_asset, copy_usd_asset
from omni.flux.utils.widget.file_pickers import open_file_picker
from pxr import Sdf

from .message_dialog import TrexMessageDialog

if TYPE_CHECKING:
    from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore


def open_asset_file_picker(
    title: str,
    asset_type: ReplacementAssetType,
    callback: Callable[[str], None],
    callback_cancel: Callable[[str], None],
    current_file: str | None = None,
    fallback: bool = False,
):
    """Open the shared asset file picker for a replacement asset type.

    Args:
        title: File picker title.
        asset_type: Asset type accepted by the picker.
        callback: Callback receiving the selected asset.
        callback_cancel: Callback invoked when the picker is cancelled.
        current_file: Optional file or folder to select initially.
        fallback: Whether the remembered file picker folder should override ``current_file``.
    """
    valid_extensions = _AssetReplacementsValidators.get_replacement_asset_extensions(asset_type)
    open_file_picker(
        title,
        callback=callback,
        callback_cancel=callback_cancel,
        current_file=current_file,
        fallback=fallback,
        file_extension_options=[(_format_file_extensions(valid_extensions), "Compatible Assets")],
        validate_selection=partial(_is_valid_asset_selection, asset_type=asset_type),
        validation_failed_callback=partial(_show_invalid_asset_selection, valid_extensions=valid_extensions),
    )


def open_replacement_asset_file_picker(
    title: str,
    unresolved_asset_path: str,
    callback: Callable[[str], None],
    callback_cancel: Callable[[str], None],
    current_file: str | None = None,
):
    """Open the shared replacement asset file picker.

    Args:
        title: File picker title.
        unresolved_asset_path: Original unresolved asset path used to choose compatible replacement types.
        callback: Callback receiving the selected replacement asset.
        callback_cancel: Callback invoked when the picker is cancelled.
        current_file: Optional file or folder to select initially.
    """
    open_asset_file_picker(
        title,
        _AssetReplacementsValidators.get_replacement_asset_type(unresolved_asset_path),
        callback=callback,
        callback_cancel=callback_cancel,
        current_file=current_file,
    )


def accept_asset_if_valid_for_replacement(
    asset_path: str,
    layer: Sdf.Layer,
    asset_core: "AssetReplacementsCore",
    context: omni.usd.UsdContext,
    accept_handler: Callable[[str], None],
    ignore_ingestion_handler: Callable[[str], None] | None = None,
    cancel_handler: Callable[[], None] | None = None,
    go_to_ingest_handler: Callable[[], None] | None = None,
) -> bool:
    """Accept an asset path or show the shared replacement validation dialogs.

    Args:
        asset_path: Selected asset path.
        layer: Layer the selected asset path is relative to.
        asset_core: Object exposing asset replacement core validation methods.
        context: USD context used when copying external assets.
        accept_handler: Callback receiving the accepted asset path.
        ignore_ingestion_handler: Optional callback used when the user bypasses ingestion validation.
        cancel_handler: Optional callback used when the user cancels the validation dialog.
        go_to_ingest_handler: Optional callback used by the dialog's ingest action.

    Returns:
        ``True`` if the asset was accepted immediately, ``False`` if user input is required.
    """
    abs_asset_path = omni.client.normalize_url(layer.ComputeAbsolutePath(asset_path))
    if not asset_core.is_file_path_valid(abs_asset_path, layer, log_error=False):
        accept_handler(asset_path)
        return True

    asset_in_project = asset_core.asset_is_in_project_dir(abs_asset_path, layer)
    if not asset_core.was_the_asset_ingested(abs_asset_path):
        _show_ingestion_dialog(
            asset_path,
            asset_in_project,
            accept_handler=ignore_ingestion_handler or accept_handler,
            cancel_handler=cancel_handler,
            go_to_ingest_handler=go_to_ingest_handler,
        )
        return False

    if not asset_in_project:
        _show_outside_project_dialog(abs_asset_path, context, accept_handler, cancel_handler)
        return False

    accept_handler(asset_path)
    return True


def _format_file_extensions(extensions: tuple[str, ...]) -> str:
    return ", ".join(f"*{extension}" for extension in extensions)


def _get_selected_path(dirname: str, filename: str) -> str:
    if not dirname:
        return omni.client.normalize_url(filename)
    directory = dirname.rstrip("/\\")
    return omni.client.normalize_url(f"{directory}/{filename}")


def _is_valid_asset_selection(dirname: str, filename: str, asset_type: ReplacementAssetType) -> bool:
    return _AssetReplacementsValidators.is_valid_replacement_asset(
        _get_selected_path(dirname, filename),
        asset_type,
    )


def _show_invalid_asset_selection(dirname: str, filename: str, valid_extensions: tuple[str, ...]):
    TrexMessageDialog(
        title="Invalid Selection",
        message=(
            f"{_get_selected_path(dirname, filename)} is not a valid replacement asset.\n\n"
            f"Supported file types: {', '.join(valid_extensions)}"
        ),
        disable_cancel_button=True,
    )


def _show_ingestion_dialog(
    asset_path: str,
    asset_in_project: bool,
    accept_handler: Callable[[str], None],
    cancel_handler: Callable[[], None] | None = None,
    go_to_ingest_handler: Callable[[], None] | None = None,
):
    ingest_enabled = bool(
        go_to_ingest_handler
        and omni.kit.app.get_app()
        .get_extension_manager()
        .get_enabled_extension_id("lightspeed.trex.control.ingestcraft")
    )
    TrexMessageDialog(
        title=constants.ASSET_NEED_INGEST_WINDOW_TITLE,
        message=constants.ASSET_NEED_INGEST_MESSAGE,
        ok_handler=partial(accept_handler, asset_path),
        ok_label=constants.ASSET_NEED_INGEST_WINDOW_OK_LABEL,
        cancel_handler=cancel_handler,
        on_window_closed_fn=cancel_handler,
        disable_ok_button=not asset_in_project,
        disable_cancel_button=False,
        disable_middle_button=not ingest_enabled,
        middle_label=constants.ASSET_NEED_INGEST_WINDOW_MIDDLE_LABEL,
        middle_handler=go_to_ingest_handler,
    )


def _show_outside_project_dialog(
    asset_path: str,
    context: omni.usd.UsdContext,
    accept_handler: Callable[[str], None],
    cancel_handler: Callable[[], None] | None = None,
):
    copy_asset = (
        copy_usd_asset
        if _AssetReplacementsValidators.get_replacement_asset_type(asset_path) == ReplacementAssetType.MESH
        else copy_non_usd_asset
    )
    TrexMessageDialog(
        title=constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE,
        message=constants.ASSET_OUTSIDE_OF_PROJ_DIR_MESSAGE,
        disable_ok_button=False,
        ok_label=constants.ASSET_OUTSIDE_OF_PROJ_DIR_OK_LABEL,
        ok_handler=partial(
            copy_asset,
            context=context,
            asset_path=asset_path,
            callback_func=accept_handler,
        ),
        disable_middle_button=True,
        disable_cancel_button=False,
        cancel_handler=cancel_handler,
        on_window_closed_fn=cancel_handler,
    )
