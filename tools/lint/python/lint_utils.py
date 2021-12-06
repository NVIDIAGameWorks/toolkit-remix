import datetime
import os
import re
import subprocess
import sys

import packmanapi

_git_path = None


def _get_platform() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    else:
        return "windows"


def is_windows() -> bool:
    return _get_platform() == "windows"


def _get_git_path() -> str:
    global _git_path
    if not _git_path:
        if is_windows():
            deps = packmanapi.install("git", "2.28.0-windows-x86_64")
            return os.path.join(deps["git"], "bin", "git.exe")
        else:
            return "git"
    return _git_path


def get_last_commit():
    git_path = _get_git_path()
    p = subprocess.Popen([git_path, "rev-parse", "HEAD"], stdout=subprocess.PIPE, encoding="utf8")
    for f in p.stdout:
        return f.strip()
    return None


def get_stagged_files():
    git_path = _get_git_path()
    p = subprocess.Popen([git_path, "diff", "--name-only"], stdout=subprocess.PIPE, encoding="utf8")
    return [f.strip() for f in p.stdout]


def get_merge_base_commit():
    git_path = _get_git_path()
    p = subprocess.Popen([git_path, "merge-base", "--fork-point", "origin"], stdout=subprocess.PIPE, encoding="utf8")
    for f in p.stdout:
        return f.strip()
    return None


def get_modified_files():
    git_path = _get_git_path()
    target_branch = os.environ.get("CI_MERGE_REQUEST_DIFF_BASE_SHA")
    if target_branch is None:
        target_branch = get_merge_base_commit()
    last_commit = os.environ.get("CI_COMMIT_SHA")
    if last_commit is None:
        last_commit = get_last_commit()
    if last_commit is None:
        print("Can't get last commit")
        sys.exit(1)

    # get only stagged file. I want all modified files, even committed one
    # p = subprocess.Popen([git_path, "status", "-s"], stdout=subprocess.PIPE, encoding="utf8")
    p = subprocess.Popen(
        [git_path, "diff-tree", "--no-commit-id", "--name-only", "-r", target_branch, "-r", last_commit],
        stdout=subprocess.PIPE,
        encoding="utf8",
    )
    files = get_stagged_files()
    for f in p.stdout:
        file_path = f.strip()
        if file_path not in files:
            files.append(file_path)
    return files


def get_file_years(filename: str):
    git_path = _get_git_path()
    years = []
    p = subprocess.Popen([git_path, "log", "--follow", filename], stdout=subprocess.PIPE, encoding="utf8")
    for line in p.stdout:
        if "Date" in line:
            search = "(20[0-9]+) -[0-9]+"
            year = re.search(search, line)
            if year:
                years.append(year.group(1))

    if years:
        return min(years), max(years)

    now = datetime.datetime.utcnow().year
    return now, now
