-- Use folder name to build extension name and tag. Version is specified explicitly.
local ext = get_current_extension_info()

project_ext (ext)
repo_build.prebuild_link {
    { "docs", ext.target_dir.."/docs" },
    { "lightspeed", ext.target_dir.."/lightspeed" },
    -- RTXIO tool binaries fetched via packman (rtx-remix-rtxio).
    { "${target_deps}/rtxio", ext.target_dir.."/deps/rtxio" },
}
