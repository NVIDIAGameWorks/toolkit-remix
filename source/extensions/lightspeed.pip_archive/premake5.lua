local ext = get_current_extension_info()

project_ext (ext)

repo_build.prebuild_link { "$root/_build/target-deps/lss_pip_prebundle", ext.target_dir.."/pip_prebundle" }
repo_build.prebuild_link { "lightspeed", ext.target_dir.."/lightspeed" }
repo_build.prebuild_link { "docs", ext.target_dir.."/docs" }
repo_build.prebuild_link { "data", ext.target_dir.."/data" }

