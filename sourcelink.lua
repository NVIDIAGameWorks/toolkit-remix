require('vstudio')
local gitinfo
function sourcelink(cfg)
    -- This adds support for linker option /sourcelink
    -- https://docs.microsoft.com/en-us/cpp/build/reference/sourcelink?view=vs-2019
    if _ACTION < "vs2017" then return end -- Not supported prior to 2017
    -- TODO: It's only supported in 2017 update 8, so check linker version to see if it supports it
    -- probably involves invoking link.exe and checking version >= 14.15.26730.0
    -- This may be unnecessary because running on previous versions merely spits out a linker warning.

    -- If we haven't read info from git yet, go ahead and do that
    -- It's run in a pcall() wrapper so that if it fails to parse for whatever reason we fail gracefully
    if not gitinfo then
        local status
        status, gitinfo = pcall(function ()
            local repo = io.popen('git config --get remote.origin.url'):read('*l'):sub(1, -5) -- remove .git from the end
            local hash = io.popen('git rev-parse HEAD'):read("*l")
            local localrepo = path.normalize(io.popen('git rev-parse --show-toplevel'):read("*l"))
            return {['remotepath'] = repo, ['hash'] = hash, ['localpath'] = localrepo}
        end)
        if not status then
            print('Failed to read values from git')
            gitinfo = {} 
        end
    end
    -- Ignore if we couldn't read info from git
    if not gitinfo.remotepath then return end

    local m = premake.vstudio.vc2010
    local groups = m.categorizeSources(cfg.project)
    local sl = {}
    for _, group in ipairs(groups) do
        for _, f in ipairs(group.files) do
            if f.abspath:sub(1, #gitinfo.localpath) == gitinfo.localpath then
                local endcount = f.relpath:reverse():find('/')
                if endcount then
                    local relpath = f.relpath:sub(1, -endcount) .. '*'
                    if not sl[relpath] then
                        sl[relpath] = gitinfo.remotepath .. '/raw/' .. gitinfo.hash .. '/' .. f.abspath:sub(#gitinfo.localpath + 2, -endcount) .. '*'
                    end
                else
                    sl[f.relpath] = gitinfo.remotepath .. '/raw/' .. gitinfo.hash .. '/' .. f.abspath:sub(#gitinfo.localpath + 2)
                end
            end
        end
    end
    local filename = cfg.objdir .. '/sourcelink.json'
    io.writefile(filename, json.encode_pretty({['documents']=sl}))
    table.insert(cfg.linkoptions, "/sourcelink:$(IntDir)sourcelink.json")
end

premake.override(premake.vstudio.vc2010, "additionalLinkOptions", function(base, cfg)
    sourcelink(cfg)
    return base(cfg)
end)
