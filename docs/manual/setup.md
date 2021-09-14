# Setting up New Repo

To get started, you will need to do a few things:

## 1. Duplicate the template (kit-template repo)


* Fork [https://gitlab-master.nvidia.com/omniverse/kit-extensions/kit-template](https://gitlab-master.nvidia.com/omniverse/kit-extensions/kit-template) into your own space (i.e https://gitlab-master.nvidia.com/your_username result should look like below


![alt_text](../../data/readme_images/new_repo1.png "new_repository")


* Rename the project and it’s path to be what you want 


![alt_text](../../data/readme_images/new_repo2.png "new_repository")

* Transfer the project back to the kit-extensions group with it’s new name


![alt_text](../../data/readme_images/transfer_ownership.png "transfer_ownership")


Note that if you have permissions problems transferring back, you should ask or another maintainer to give you permissions.

Note that the new project still has a fork relationship with kit-template, which means it’s possible to submit and merge MRs across the forks. One disadvantage of this, is that when you submit a new MR, the target branch will be by default in kit-template (maybe it’s possible to change this)


## 2. Modify the build/repo/toolchain configuration files

In `repo.toml` change project name:

```toml
# Reposiory Name.
name = "kit-template"
```

That name is used in many other places, like solution name or package name.

+ if you have a fork, can do a normal MR too, cherry-pick changes etc..
+ Alternatively just copy them over from kit-template like this: 

```
cp -R build.bat build.sh .clang-format deps/ docs/ .editorconfig format_code.bat format_code.sh .gitattributes .gitignore package.toml premake5.lua repo.bat repo.sh repo.toml setup.sh tools/ .vscode/ ../kit-usd/
```

## 3. Duplicate the TeamCity project

This is mostly just a question of:
1. Navigating to [https://teamcity.nvidia.com/project/Omniverse_KitExtensions_KitTemplate?mode=builds](https://teamcity.nvidia.com/project/Omniverse_KitExtensions_KitTemplate?mode=builds)
2. Clicking _Edit Project..._, then _Actions_ > _Copy project..._ on the upper right-hand corner of the page.
**Note:** Should you not see the _Actions_ menu at the top of the page, navigate to [https://dlrequest](https://dlrequest/GroupID/Groups/MyGroups#MyMemberships) and validate that you are a member of the `carbonite-dev` and `omniverse-dev` groups. If not, request access and once it has been granted, wait a few minutes before refreshing the TeamCity page.
3. From the _Copy Project_ modal dialog, modify the _VCS Root ID_ in order to match the name of the new project, and save it under another name.
As a general rule of thumb, replace every instance of `KitTemplate` with the name of your project, to ensure some kind of uniqueness.
4. (Optional) You may choose to uncheck the _Copy build configurations' build counters_ option should you wish to start your new TeamCity project builds from `1`.
5. Clicking the _Copy_ button of the dialog.
