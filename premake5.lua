-- Shared build scripts from repo_build package
repo_build = require("omni/repo/build")

-- Repo root
root = repo_build.get_abs_path(".")

-- Insert kit template premake configuration, it creates solution, finds extensions.. Look inside for more details.
dofile("_repo/deps/repo_kit_tools/kit-template/premake5.lua")

repo_build.prebuild_copy {
    { "launcher.toml", bin_dir },
    { "source/shell/*${shell_ext}", bin_dir },
}

define_app("lightspeed.app.trex")
define_app("lightspeed.app.trex.stagecraft")
define_app("lightspeed.app.trex.texturecraft")
define_app("lightspeed.app.trex_dev")
define_app("omni.app.lightspeed")
