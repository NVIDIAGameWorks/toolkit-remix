-- Use folder name to build extension name and tag. Version is specified explicitly.
local ext = get_current_extension_info()

-- Link the current "target" folders into the extension target folder:
project_ext (ext)
repo_build.prebuild_link {
    { "apps", ext.target_dir.."/apps" },
    { "bin", ext.target_dir.."/bin" },
    { "lightspeed", ext.target_dir.."/lightspeed" },
    { "docs", ext.target_dir.."/docs" },
    { "data", ext.target_dir.."/data" },
}

local args_cli = args or {}
args_cli.subfolder = "exts/lightspeed.trex.project_wizard.core/apps"
define_app("lightspeed.app.trex.project_wizard_cli", args_cli)
