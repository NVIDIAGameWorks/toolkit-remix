local ext = get_current_extension_info()

project_ext (ext)

-- Link only those files and folders into the extension target directory
repo_build.prebuild_link {
    {"python/lightspeed/", ext.target_dir.."/lightspeed"},
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
    { "icons", ext.target_dir.."/icons" }
}
repo_build.prebuild_copy { "docs/jxnblk-LICENSE.md", ext.target_dir.."/PACKAGE-LICENSES/jxnblk-LICENSE.md" }
