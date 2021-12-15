import jetbrains.buildServer.configs.kotlin.v2019_2.*
import jetbrains.buildServer.configs.kotlin.v2019_2.buildFeatures.commitStatusPublisher
import jetbrains.buildServer.configs.kotlin.v2019_2.buildFeatures.freeDiskSpace
import jetbrains.buildServer.configs.kotlin.v2019_2.buildSteps.script
import jetbrains.buildServer.configs.kotlin.v2019_2.failureConditions.BuildFailureOnMetric
import jetbrains.buildServer.configs.kotlin.v2019_2.failureConditions.failOnMetricChange
import jetbrains.buildServer.configs.kotlin.v2019_2.triggers.finishBuildTrigger
import jetbrains.buildServer.configs.kotlin.v2019_2.triggers.schedule
import jetbrains.buildServer.configs.kotlin.v2019_2.triggers.vcs
import jetbrains.buildServer.configs.kotlin.v2019_2.vcs.GitVcsRoot

/*
The settings script is an entry point for defining a TeamCity
project hierarchy. The script should contain a single call to the
project() function with a Project instance or an init function as
an argument.

VcsRoots, BuildTypes, Templates, and subprojects can be
registered inside the project using the vcsRoot(), buildType(),
template(), and subProject() methods respectively.

To debug settings scripts in command-line, run the

    mvnDebug org.jetbrains.teamcity:teamcity-configs-maven-plugin:generate

command and attach your debugger to the port 8000.

To debug in IntelliJ Idea, open the 'Maven Projects' tool window (View
-> Tool Windows -> Maven Projects), find the generate task node
(Plugins -> teamcity-configs -> teamcity-configs:generate), the
'Debug' option is available in the context menu for the task.
*/

version = "2021.1"

project {
    description = "Omniverse TRex App"

    params {
        param("env.OV_BRANCH_NAME", "no need")
    }

    subProject(Master)
}

object Master : Project({
    name = "master"

    buildType(Master_BuildAndValidation)
    buildType(Master_PublishExtensions)

    subProject(Master_BuildAndPackagingPublishing)
    subProject(Master_Testing)
    subProject(Master_BuildAndPackaging)
})

object Master_BuildAndValidation : BuildType({
    name = "build and validation"

    type = BuildTypeSettings.Type.COMPOSITE
    buildNumberPattern = "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs.buildNumber}"

    vcs {
        root(RelativeId("GitlabMaster"))

        showDependenciesChanges = true
    }

    triggers {
        vcs {
            branchFilter = """
                +:<default>
                +:merge-requests*
                +:release/*
            """.trimIndent()
        }
    }

    dependencies {
        snapshot(Master_BuildAndPackaging_GenerateBuildNumber) {
            reuseBuilds = ReuseBuilds.NO
            onDependencyFailure = FailureAction.FAIL_TO_START
        }
        snapshot(Master_BuildAndPackaging_LauncherPackageLinuxX8664) {
            onDependencyFailure = FailureAction.FAIL_TO_START
            onDependencyCancel = FailureAction.FAIL_TO_START
        }
        snapshot(Master_BuildAndPackaging_LauncherPackageWindowsX8664) {
            onDependencyFailure = FailureAction.FAIL_TO_START
            onDependencyCancel = FailureAction.FAIL_TO_START
        }
        snapshot(Master_Testing_LinuxX8664) {
            onDependencyFailure = FailureAction.FAIL_TO_START
            onDependencyCancel = FailureAction.FAIL_TO_START
        }
        snapshot(Master_Testing_WindowsX8664) {
            onDependencyFailure = FailureAction.FAIL_TO_START
            onDependencyCancel = FailureAction.FAIL_TO_START
        }
    }
})

object Master_PublishExtensions : BuildType({
    name = "publish extensions"

    type = BuildTypeSettings.Type.COMPOSITE

    vcs {
        root(RelativeId("GitlabMaster"))

        showDependenciesChanges = true
    }

    triggers {
        finishBuildTrigger {
            buildType = "${Master_BuildAndValidation.id}"
            successfulOnly = true
            branchFilter = """
                +:<default>
                +:daily
                +:release/*
            """.trimIndent()
        }
    }

    dependencies {
        snapshot(Master_BuildAndPackagingPublishing_PublishExtensionsWindowsX8664) {
            onDependencyFailure = FailureAction.FAIL_TO_START
        }
        snapshot(Master_BuildAndValidation) {
            onDependencyFailure = FailureAction.FAIL_TO_START
        }
    }
})


object Master_BuildAndPackaging : Project({
    name = "Build and Packaging"

    buildType(Master_BuildAndPackaging_LauncherPackageWindowsX8664)
    buildType(Master_BuildAndPackaging_GenerateBuildNumber)
    buildType(Master_BuildAndPackaging_LauncherPackageLinuxX8664)

    params {
        param("env.OMNI_USER", "%nucleus.service.ov-content.user%")
        param("env.OMNI_PASS", "%nucleus.service.ov-content.pass%")
    }
})

object Master_BuildAndPackaging_GenerateBuildNumber : BuildType({
    name = "generate build number"

    params {
        param("env.OV_BRANCH_NAME", "%vcsroot.branch%")
        param("env.buildbranch", "%teamcity.build.branch%")
        param("env.FINAL_BUILD_NUMBER", "0")
    }

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
    }

    steps {
        script {
            scriptContent = """call tools\ci\build-and-packaging\generate-build-number\step.bat"""
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    requirements {
        contains("system.agent.name", "WIN10-2021", "RQ_3320")
        exists("system.feature.windows.version")
        doesNotExist("system.feature.nvidia.gpu.count")
    }

    disableSettings("RQ_3320")
})

object Master_BuildAndPackaging_LauncherPackageLinuxX8664 : BuildType({
    name = "build linux-x86_64"

    buildNumberPattern = "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs.buildNumber}"

    params {
        param("env.BUILD_NUMBER", "%build.number%")
        param("env.FINAL_BUILD_NUMBER", "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs["env.FINAL_BUILD_NUMBER"]}")
    }

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
    }

    steps {
        script {
            scriptContent = "./tools/ci/build-and-packaging/launcher-package-linux-x86_64/step.sh"
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    failureConditions {
        executionTimeoutMin = 30
    }

    features {
        commitStatusPublisher {
            publisher = gitlab {
                gitlabApiUrl = "https://gitlab-master.nvidia.com/api/v4"
                accessToken = "%env.GITLAB_AUTH_TOKEN%"
            }
        }
    }

    dependencies {
        snapshot(Master_BuildAndPackaging_GenerateBuildNumber) {
            onDependencyFailure = FailureAction.FAIL_TO_START
            onDependencyCancel = FailureAction.FAIL_TO_START
        }
    }

    requirements {
        contains("teamcity.agent.jvm.os.name", "Linux")
        doesNotContain("teamcity.agent.name", "stl-test")
        doesNotExist("system.feature.nvidia.gpu.count")
        moreThan("system.feature.agent.maxFreeDisksizeMb", "30000")
        moreThan("teamcity.agent.work.dir.freeSpaceMb", "20000")
    }
})

object Master_BuildAndPackaging_LauncherPackageWindowsX8664 : BuildType({
    name = "build windows-x86_64"

    buildNumberPattern = "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs.buildNumber}"

    params {
        param("env.BUILD_NUMBER", "%build.number%")
        param("env.FINAL_BUILD_NUMBER", "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs["env.FINAL_BUILD_NUMBER"]}")
    }

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
    }

    steps {
        script {
            scriptContent = """call tools\ci\build-and-packaging\launcher-package-windows-x86_64\step.bat"""
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    failureConditions {
        executionTimeoutMin = 30
    }

    features {
        freeDiskSpace {
            requiredSpace = "30gb"
            failBuild = false
        }
        commitStatusPublisher {
            publisher = gitlab {
                gitlabApiUrl = "https://gitlab-master.nvidia.com/api/v4"
                accessToken = "%env.GITLAB_AUTH_TOKEN%"
            }
        }
    }


    dependencies {
        snapshot(Master_BuildAndPackaging_GenerateBuildNumber) {
            reuseBuilds = ReuseBuilds.NO
            onDependencyFailure = FailureAction.FAIL_TO_START
            onDependencyCancel = FailureAction.FAIL_TO_START
        }
    }

    requirements {
        contains("system.agent.name", "WIN10-2021", "RQ_3299")
        moreThan("system.feature.agent.maxFreeDisksizeMb", "30000")
        doesNotExist("system.feature.nvidia.gpu.count")
        contains("teamcity.agent.jvm.os.name", "Windows")
    }
})


object Master_BuildAndPackagingPublishing : Project({
    name = "Publishing"

    buildType(Master_BuildAndPackagingPublishing_PublishLauncherPackages)
    buildType(Master_BuildAndPackagingPublishing_SignWindowsBinaries)
    buildType(Master_BuildAndPackagingPublishing_PublishExtensionsWindowsX8664)
    buildType(Master_BuildAndPackagingPublishing_PublishDocs)
})

object Master_BuildAndPackagingPublishing_PublishExtensionsWindowsX8664 : BuildType({
    name = "publish extensions (windows-x86_64)"

    buildNumberPattern = "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs.buildNumber}"

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
    }

    steps {
        script {
            scriptContent = """tools\ci\publishing\publish-extensions-windows-x86_64\step.bat"""
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    dependencies {
        dependency(Master_BuildAndPackaging_LauncherPackageWindowsX8664) {
            snapshot {
                onDependencyFailure = FailureAction.FAIL_TO_START
            }

            artifacts {
                cleanDestination = true
                artifactRules = """
                    *.zip => _build/packages
                """.trimIndent()
            }
        }
    }

    requirements {
        contains("teamcity.agent.jvm.os.name", "Windows")
        contains("system.agent.name", "WIN10-2021")
    }
})

object Master_BuildAndPackagingPublishing_PublishLauncherPackages : BuildType({
    name = "publish launcher packages"

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
    }

    steps {
        script {
            scriptContent = """call tools\ci\publishing\publish-launcher-packages\step.bat"""
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    triggers {
        vcs {
            enabled = true
            triggerRules = "+:VERSION.md"
            branchFilter = """
                +:main
                +:release/*
                +:daily
                +:daily-rtx
            """.trimIndent()
        }
    }

    dependencies {
        dependency(Master_BuildAndPackagingPublishing_SignWindowsBinaries) {
            snapshot {
                onDependencyFailure = FailureAction.FAIL_TO_START
                onDependencyCancel = FailureAction.FAIL_TO_START
            }

            artifacts {
                cleanDestination = true
                artifactRules = """
                    code-launcher*.signed.zip => _build/packages
                """.trimIndent()
            }
        }
        dependency(Master_BuildAndPackaging_LauncherPackageLinuxX8664) {
            snapshot {
                onDependencyFailure = FailureAction.IGNORE
                onDependencyCancel = FailureAction.IGNORE
            }

            artifacts {
                cleanDestination = true
                artifactRules = "code-launcher* => _build/packages"
            }
        }
        snapshot(Master_Testing_LinuxX8664) {
            onDependencyFailure = FailureAction.IGNORE
            onDependencyCancel = FailureAction.IGNORE
        }
        snapshot(Master_Testing_WindowsX8664) {
            onDependencyFailure = FailureAction.IGNORE
            onDependencyCancel = FailureAction.IGNORE
        }
    }

    requirements {
        contains("teamcity.agent.jvm.os.name", "Windows")
        contains("system.agent.name", "WIN10-2021", "RQ_2107")
        doesNotExist("system.feature.nvidia.gpu.count")
        doesNotContain("system.agent.name", "signer")
    }

    params {
        param("env.TREX_PIPELINE_TOKEN", "%omni.release-pipeline-token%")
    }


    disableSettings("RQ_2107")
})

object Master_BuildAndPackagingPublishing_SignWindowsBinaries : BuildType({
    name = "sign windows binaries"

    buildNumberPattern = "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs.buildNumber}"

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
    }

    steps {
        script {
            scriptContent = """call tools\ci\publishing\sign-windows-binaries\step.bat"""
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    triggers {
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_Nucleus_Dev_Publishing_BuildAndSignInstallerWindows"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_AssetConverterService_Releases_Master_Publishing_BuildAndSignInstaller"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_CacheService_Master_BuildAndSignInstaller_BuildAndSignInstallerWindows"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_OmniAuth_Installer_Windows"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_DiscoveryService_Publishing_WindowsInstaller"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_IndexingService_Releases_Master_Publishing_BuildAndSignInstaller"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_SnapshotService_Master_Publishing_BuildAndSignInstallerWindows"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_ThumbnailService_Master_Publishing_BuildAndSignInstallerWindows"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_WebService_Master_Publishing_BuildAndSignInstallerWindows"
        }
        finishBuildTrigger {
            enabled = false
            buildType = "Omniverse_SystemMonitor_Master_Publishing_BuildAndSignInstaller"
        }
        vcs {
            enabled = false
        }
    }

    failureConditions {
        executionTimeoutMin = 60
        failOnMetricChange {
            metric = BuildFailureOnMetric.MetricType.ARTIFACT_SIZE
            units = BuildFailureOnMetric.MetricUnit.DEFAULT_UNIT
            comparison = BuildFailureOnMetric.MetricComparison.LESS
            compareTo = value()
            param("metricThreshold", "1KB")
            param("anchorBuild", "lastSuccessful")
        }
    }

    dependencies {
        dependency(Master_BuildAndPackaging_LauncherPackageWindowsX8664) {
            snapshot {
                onDependencyFailure = FailureAction.FAIL_TO_START
                onDependencyCancel = FailureAction.FAIL_TO_START
            }

            artifacts {
                cleanDestination = true
                artifactRules = "code-launcher@*.release.zip => _unsignedpackages"
            }
        }
    }

    requirements {
        contains("teamcity.agent.jvm.os.name", "Windows 10")
        contains("teamcity.agent.name", "signer")
    }
})

object Master_BuildAndPackagingPublishing_PublishDocs : BuildType({
    name = "publish docs"

    buildNumberPattern = "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs.buildNumber}"

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
        showDependenciesChanges = true
    }

    steps {
        script {
            scriptContent = """tools\ci\publishing\publish-docs\step.bat"""
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    features {
        freeDiskSpace {
            failBuild = false
        }
    }

    dependencies {
        dependency(Master_BuildAndPackaging_LauncherPackageWindowsX8664) {
            snapshot {
                onDependencyFailure = FailureAction.FAIL_TO_START
                onDependencyCancel = FailureAction.FAIL_TO_START
            }

            artifacts {
                artifactRules = """
                    docs*.7z!** => .
                """.trimIndent()
            }
        }
    }

    requirements {
        doesNotExist("system.feature.nvidia.gpu.driver.major")
        exists("system.feature.windows.version")
    }

    params {
        param("env.AWS_ACCESS_KEY_ID", "%omniverse-docs.AWS_ACCESS_KEY_ID%")
        param("env.AWS_SECRET_ACCESS_KEY", "%omniverse-docs.AWS_SECRET_ACCESS_KEY%")
    }
})


object Master_Testing : Project({
    name = "Testing"

    buildType(Master_Testing_LinuxX8664)
    buildType(Master_Testing_WindowsX8664)
})

object Master_Testing_LinuxX8664 : BuildType({
    name = "linux-x86_64"

    artifactRules = """
        *.dmp => crash_dumps
        crash_*.txt => crash_dumps
        **/*.log => logs
    """.trimIndent()
    buildNumberPattern = "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs.buildNumber}"

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
    }

    steps {
        script {
            scriptContent = "./tools/ci/testing/linux-x86_64/step.sh"
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    triggers {
        vcs {
            enabled = false
        }
    }

    failureConditions {
        executionTimeoutMin = 15
    }

    features {
        commitStatusPublisher {
            publisher = gitlab {
                gitlabApiUrl = "https://gitlab-master.nvidia.com/api/v4"
                accessToken = "%env.GITLAB_AUTH_TOKEN%"
            }
        }
    }

    dependencies {
        dependency(Master_BuildAndPackaging_LauncherPackageLinuxX8664) {
            snapshot {
                onDependencyFailure = FailureAction.FAIL_TO_START
                onDependencyCancel = FailureAction.FAIL_TO_START
            }

            artifacts {
                cleanDestination = true
                artifactRules = """
                    *.zip => _build/packages
                """.trimIndent()
            }
        }
    }

    requirements {
        contains("teamcity.agent.jvm.os.name", "Linux")
        exists("system.feature.nvidia.gpu.driver.major")
        contains("teamcity.agent.jvm.os.arch", "amd64")
        doesNotContain("teamcity.agent.name", "cl1-trx40-05")
        doesNotContain("teamcity.agent.name", "cl1-trx40-06")
        doesNotContain("teamcity.agent.name", "cl1-trx40-07")
        doesNotContain("teamcity.agent.name", "cl1-trx40-08")
        doesNotContain("teamcity.agent.name", "cl1-trx40-09")
        doesNotContain("teamcity.agent.name", "cl1-trx40-10")
        doesNotContain("teamcity.agent.name", "cl1-trx40-11 ")
    }
})

object Master_Testing_WindowsX8664 : BuildType({
    name = "windows-x86_64"

    artifactRules = """
        *.dmp => crash_dumps
        crash_*.txt => crash_dumps
        **/*.log => logs
    """.trimIndent()
    buildNumberPattern = "${Master_BuildAndPackaging_GenerateBuildNumber.depParamRefs.buildNumber}"

    vcs {
        root(RelativeId("GitlabMaster"))

        cleanCheckout = true
    }

    steps {
        script {
            scriptContent = """call tools\ci\testing\windows-x86_64\step.bat"""
            param("org.jfrog.artifactory.selectedDeployableServer.downloadSpecSource", "Job configuration")
            param("org.jfrog.artifactory.selectedDeployableServer.useSpecs", "false")
            param("org.jfrog.artifactory.selectedDeployableServer.uploadSpecSource", "Job configuration")
        }
    }

    failureConditions {
        executionTimeoutMin = 15
    }

    features {
        commitStatusPublisher {
            publisher = gitlab {
                gitlabApiUrl = "https://gitlab-master.nvidia.com/api/v4"
                accessToken = "%env.GITLAB_AUTH_TOKEN%"
            }
        }
    }

    dependencies {
        dependency(Master_BuildAndPackaging_LauncherPackageWindowsX8664) {
            snapshot {
                onDependencyFailure = FailureAction.FAIL_TO_START
                onDependencyCancel = FailureAction.FAIL_TO_START
            }

            artifacts {
                cleanDestination = true
                artifactRules = """
                    *.zip => _build/packages
                """.trimIndent()
            }
        }
    }

    requirements {
        contains("teamcity.agent.jvm.os.name", "Windows")
        moreThan("system.feature.nvidia.gpu.driver.major", "429")
        doesNotContain("system.agent.name", "colossus", "RQ_3934")
    }

    disableSettings("RQ_3934")
})
