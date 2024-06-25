 -- Use folder name to build extension name and tag. Version is specified explicitly.
local ext = get_current_extension_info()

-- That will also link whole current "target" folder into as extension target folder:
project_ext (ext)
    repo_build.prebuild_link {
        { "docs", ext.target_dir.."/docs" },
        { "data", ext.target_dir.."/data" },
        { "omni", ext.target_dir.."/omni" },
        { "apps", ext.target_dir.."/apps" },
        { "bin", ext.target_dir.."/bin" },
    }

local args = args or {}
args.subfolder = "exts/omni.flux.validator.manager.window/apps"
define_app("omni.flux.app.validator", args)
