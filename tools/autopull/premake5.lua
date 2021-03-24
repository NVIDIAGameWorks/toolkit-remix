-- Setup tool to automatically pull kit
-- We need packman, dependency, script, batch files. Batch files are per config. Depepdency includes kit sdk path override.
repo_build.prebuild_link {
    { "${root}/tools/packman", bin_dir.."/dev/packman" },
}
repo_build.prebuild_copy {
    { "pull_kit_sdk.py", bin_dir },
    { "./${config}/pull_kit_sdk*", bin_dir },
    { "${root}/deps/kit-sdk.packman.xml", bin_dir.."/dev/deps" },
    { "kit-sdk-override.packman.xml", bin_dir.."/dev/deps" },
}
