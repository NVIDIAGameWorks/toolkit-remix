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


## 2. Change project name

In `repo.toml` change project name:

```toml
# Reposiory Name.
name = "kit-my-funny-project"
```

That name is used in many other places, like solution name or package name.

You can build, test and push that change:

`> build.bat -r`

`> repo.bat test`


## 3. Duplicate the TeamCity project

All TC configs are stored in repo under `.teamcity` folder, so you only need to setup root project with correct VCS url and everything else will show up in TC UI upon first build. But it is easier to just copy this project, change VCS settings and run a build to achieve the same result:

1. Go to [https://teamcity.nvidia.com/project/Omniverse_KitExtensions_KitTemplate?mode=builds](https://teamcity.nvidia.com/project/Omniverse_KitExtensions_KitTemplate?mode=builds)

2. Click _Edit Project..._, -> _Actions_ -> _Copy project..._ on the upper right-hand corner of the page. And perform copy. We recommend that namespace on TC matches one on gitlab. E.g. `Omniverse/kit-extensions/kit-my-funny-project` .

3. Go into the new project settings -> VCS Roots. And click to edit previous `gitlab-master-omniverse-kit-extensions-kit-template`. Here change _VCS root name_ and _Fetch URL_ (replace `kit-template` with your `kit-my-funny-project`).

4. Go into _Build and validation_ job and run to make sure all works as expected.

**Note:** If you don't see the _Actions_ menu at the top of the page, navigate to [https://dlrequest](https://dlrequest/GroupID/Groups/MyGroups#MyMemberships) and validate that you are a member of the `carbon-dev` and `omniverse-dev` groups.

## 4. What's next?

Your new extension project is ready to use. It still builds the same demo extensions that were in `kit-template`. So first step would be to rename or remove them. Create your own extensions and update application kit file to load them, update `[repo_publish_exts]` of `repo.toml` to publish them. 

