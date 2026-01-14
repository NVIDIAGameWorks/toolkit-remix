-- --------------------------------------------------------------------------------------------------------------------
-- Build file for the lightspeed.trex.logic.ogn extension.
--
-- Node implementations (.ogn and .py files) come from target-deps/omni_core_materials/lightspeed.trex.logic
-- Local config (CategoryDefinition.json) is kept in python/nodes/config/
--
-- IMPORTANT: We COPY (not link) the external node files because:
--   1. The nodes directory needs to contain both external .ogn/.py files AND local config/
--   2. You cannot create a symlink inside another symlink's target (config inside nodes)
--   3. Copying allows us to have a unified nodes/ directory with our local config override

-- --------------------------------------------------------------------------------------------------------------------
local ext = get_current_extension_info()

-- --------------------------------------------------------------------------------------------------------------------
-- Set up a variable containing standard configuration information for projects containing OGN files.
-- The string corresponds to the Python module name, in this case lightspeed.trex.logic.ogn.
local ogn = get_ogn_project_information(ext, "lightspeed/trex/logic/ogn")

-- Path to external nodes in target-deps (absolute path for os.matchfiles)
local external_nodes_src = target_deps.."/omni_core_materials/lightspeed.trex.logic"

ext.group = "remix"

-- --------------------------------------------------------------------------------------------------------------------
-- Custom OGN project setup: Process .ogn files from target-deps instead of source tree.
-- We can't use project_ext_ogn() because it uses os.matchfiles("**.ogn") which only searches source.
project_with_location(ogn.ogn_project)
kind "Utility"
dependson { "omni.graph.tools" }

-- Find .ogn files in external location (target-deps)
local ogn_files = os.matchfiles(external_nodes_src.."/*.ogn")

-- Generate node interfaces from .ogn files
make_node_generator_command(ogn, ext.name, ogn_files, { toc="docs/Overview.md" })

-- --------------------------------------------------------------------------------------------------------------------
-- Build project responsible for installing files into the build tree.
project_ext( ext, { generate_ext_project=true })

    -- Add files to the IDE project (local files only)
    add_files("python", "*.py")
    add_files("python/_impl", "python/_impl/**.py")
    add_files("python/nodes/config", "python/nodes/config")
    add_files("python/tests", "python/tests")
    add_files("docs", "docs")
    add_files("data", "data")

    -- Set up OGN build dependencies (C++ flags, includes, etc.) but NOT the python directory linking
    set_up_ogn_dependencies(ogn)

    -- Copy the init script directly into the build tree.
    repo_build.prebuild_copy {
        { "python/__init__.py", ogn.python_target_path },
    }

    -- Link standard directories to the build tree.
    repo_build.prebuild_link {
        { "docs", ext.target_dir.."/docs" },
        { "data", ext.target_dir.."/data" },
        { "python/tests", ogn.python_tests_target_path },
        { "python/_impl", ogn.python_target_path.."/_impl" },
        -- Local config linked to ogn/nodes/config (must come BEFORE the copies below)
        { "python/nodes/config", ogn.python_target_path.."/ogn/nodes/config" },
    }

    -- COPY external node files (.ogn and .py) into the nodes directory.
    -- We use copy instead of link because we need to merge external files with local config.
    -- Glob patterns copy each matching file individually.
    repo_build.prebuild_copy {
        { "${target_deps}/omni_core_materials/lightspeed.trex.logic/*.ogn", ogn.python_target_path.."/ogn/nodes" },
        { "${target_deps}/omni_core_materials/lightspeed.trex.logic/*.py", ogn.python_target_path.."/ogn/nodes" },
    }
