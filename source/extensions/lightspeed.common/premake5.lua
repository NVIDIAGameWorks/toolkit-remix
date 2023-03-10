-- Use folder name to build extension name and tag. Version is specified explicitly.
local ext = get_current_extension_info()

-- That will also link whole current "target" folder into as extension target folder:
project_ext(ext)
    os.execute 'git clone https://gitlab-master.nvidia.com/lightspeedrtx/lss-externals/lss-pytorch-CycleGAN-and-pix2pix/ ./lightspeed/common/tools/pytorch-CycleGAN-and-pix2pix'

    -- Only clone the material super resolution model for internal builds
    if os.getenv("RTX_REMIX_INTERNAL") ~= nil then
        -- Clone the MatSR repo
        os.execute 'git clone https://gitlab-master.nvidia.com/lightspeedrtx/lss-externals/mat-sr/ ./lightspeed/common/tools/mat-sr'
        -- Install the MatSR dependencies
        if package.config:sub(1,1) == '\\' then
            os.execute 'call ./lightspeed/common/tools/mat-sr/tools/install.bat'
        else
            os.execute 'sh ./lightspeed/common/tools/mat-sr/tools/install.sh'
        end

        -- Clone the MatSR Artifacts repo
        os.execute 'git clone https://gitlab-master.nvidia.com/lightspeedrtx/lss-externals/mat-sr-artifacts/ ./lightspeed/common/tools/mat-sr-artifacts'
    end

    repo_build.prebuild_link {
        { "data", ext.target_dir.."/data" },
        { "docs", ext.target_dir.."/docs" },
        { "lightspeed", ext.target_dir.."/lightspeed" },
    }
