local ext_name = "example.python_extension"
local ext_version = "1.0.0"
local ext_tag = "tag"
local ext_id = ext_name.."-"..ext_version.."-"..ext_tag
local ext_source_path = "%{root}/source/extensions/"..ext_name

group ("extensions/"..ext_id)

    repo_build.prebuild_link {
        { "source/extensions/"..ext_name, "_build/$platform/$config/exts/"..ext_id },
    }

    -- Example of python extension. Contains python sources, doesn't build or run, only for MSVS.
    if os.target() == "windows" then
        project "example.python_extension"
            kind "None"
            --add_impl_folder("")

            vpaths { ["*"] = ext_source_path }
            files { ext_source_path.."/**.py" }
            files { ext_source_path.."/**.toml" }
        
    end
