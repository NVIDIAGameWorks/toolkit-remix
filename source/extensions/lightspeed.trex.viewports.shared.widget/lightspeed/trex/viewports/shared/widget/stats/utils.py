"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb


# XXX: Move to omni.kit.viewport.serialization
def resolve_hud_visibility(viewport_api, setting_key: str, isettings: carb.settings.ISettings, dflt_value: bool = True):
    # Resolve initial visibility based on persitent settings or app defaults
    visible_key = "/app/viewport/{vp_section}" + (f"/hud/{setting_key}/visible" if setting_key else "/hud/visible")
    vp_visible = visible_key.format(vp_section=viewport_api.id)
    setting_key = "/persistent" + vp_visible
    visible = isettings.get(setting_key)
    if visible is None:
        visible = isettings.get(vp_visible)
        if visible is None:
            visible = isettings.get(visible_key.format(vp_section="defaults"))
            if visible is None:
                visible = dflt_value

        # XXX: The application defaults need to get pushed into persistent data now (for display-menu)
        isettings.set_default(setting_key, visible)

    return setting_key, visible


def human_readable_size(size: int, binary: bool = True, decimal_places: int = 1):
    def calc_human_readable(size, scale, *units):
        n_units = len(units)
        for i in range(n_units):
            if (size < scale) or (i == n_units):
                return f"{size:.{decimal_places}f} {units[i]}"
            size /= scale
        return ""

    if binary:
        return calc_human_readable(size, 1024, "B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")
    return calc_human_readable(size, 1000, "B", "KB", "MB", "GB", "TB", "PB", "EB")
