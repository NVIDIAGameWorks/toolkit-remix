import repoman

repoman.bootstrap()
import omni.repo.man
import omni.repo.format


CPP_FILES_TO_FORMAT = [
    "include/**/*.h",
    "include/**/*.inl",
    "include/**/*.cpp",
    "include/**/*.c",
    "source/**/*.h",
    "source/**/*.inl",
    "source/**/*.cpp",
    "source/**/*.c",
]


def main():
    omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64"])
    repo_folders = omni.repo.man.get_repo_paths()
    omni.repo.format.main(repo_folders=repo_folders, cpp_file_patterns=CPP_FILES_TO_FORMAT)


if __name__ == "__main__":
    main()
