-- Shared build scripts from repo_build package
repo_build = require("omni/repo/build")

-- Repo root
root = repo_build.get_abs_path(".")

-- Kit 110 bundles USD 25.11 inside Kit SDK and does not publish C++ headers separately.
-- premake5-public.lua (shipped with Kit SDK) hardcodes USD_ROOT = root.."/_build/target-deps/usd/"
-- and calls use_usd(), which calls get_usd_version() expecting pxr.h at that path.
-- Without pxr.h, get_usd_version() returns nil and premake crashes at the nil < "24.11" comparison.
-- This repo is Python-only and never compiles against USD headers; we create a minimal stub
-- so the version check resolves to "25.11" and the premake build proceeds correctly.
local pxr_h_dir = root .. "/_build/target-deps/usd/release/include/pxr"
if not os.isfile(pxr_h_dir .. "/pxr.h") then
    os.mkdir(pxr_h_dir)
    local f = io.open(pxr_h_dir .. "/pxr.h", "w")
    if f then
        f:write("// Kit 110 USD 25.11 stub: headers not separately distributed; only premake version detection needs this.\n")
        f:write("#define PXR_MINOR_VERSION 25\n")
        f:write("#define PXR_PATCH_VERSION 11\n")
        f:close()
    end
end

-- Insert kit template premake configuration, it creates solution, finds extensions.. Look inside for more details.
dofile("_repo/deps/repo_kit_tools/kit-template/premake5.lua")

repo_build.prebuild_copy {
    { "source/shell/*${shell_ext}", bin_dir },
}

repo_build.prebuild_link {
    { "${root}/tools/migrations", bin_dir.."/tools/migrations" },
}

define_app("lightspeed.app.trex")
define_app("lightspeed.app.trex.ingestcraft")
define_app("lightspeed.app.trex.stagecraft")
define_app("lightspeed.app.trex_dev")
