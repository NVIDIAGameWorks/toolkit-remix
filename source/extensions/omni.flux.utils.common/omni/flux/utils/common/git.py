"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

__all__ = [
    "get_branch",
    "clone_repository",
    "open_repository",
    "initialize_submodules",
    "pull_repository",
    "rebase_repository",
    "get_remote_commit",
    "get_local_commit",
    "has_uncommitted_changes",
    "get_remote_ahead_behind",
    "has_local_changes",
    "GitError",
]

from pathlib import Path
from typing import Callable, Optional

import carb
import pygit2

# Forward the GitError type from pygit2
from pygit2 import GitError


def clone_repository(
    repository_url: str,
    output_directory: str,
    branch: str | None = None,
    depth: int | None = None,
    recurse_submodules: bool = False,
    validation_callback: Callable[[str], bool] | None = None,
) -> Optional[pygit2.Repository]:
    """
    Clone a git repository to a local directory.

    Args:
        repository_url: The repository URL to clone from.
        output_directory: Destination directory.
        branch: Optional branch name to check out after clone.
        depth: Optional shallow clone depth (e.g., 1 for latest snapshot).
        recurse_submodules: If True, recursively clone all submodules.
        validation_callback: An optional callback function that validates the repository root.

    Raises:
        ValueError: If the repository URL does not end with .git

    Returns:
        A Repository instance, or None if the clone fails.
    """
    # Ensure the output directory ends with the repository name
    output_directory = _validate_output_directory(repository_url, output_directory)

    try:
        # Clone the repository
        repo = pygit2.clone_repository(
            repository_url,
            output_directory,
            checkout_branch=branch,
            depth=depth if depth is not None else 0,
        )
    except pygit2.GitError as e:
        carb.log_error(e)
        return None

    # For submodules, we need to handle them separately after clone
    submodules_initialized = True
    if repo and recurse_submodules:
        submodules_initialized = initialize_submodules(repo)

    if not submodules_initialized or (validation_callback is not None and not validation_callback(repo.workdir)):
        if not submodules_initialized:
            details = "Submodules failed to initialize."
        else:
            details = "Repository validation failed"
        carb.log_error(f"The repository or its submodules failed to clone: {repo.workdir}. {details}")
        repo.free()
        return None

    return repo


def open_repository(
    repo_root: str | None = None, validation_callback: Callable[[str], bool] | None = None
) -> Optional[pygit2.Repository]:
    """
    Discover and open the current git repository.

    Args:
        repo_root: The root directory of the repository to open. If None, the current working directory or any parent
                   directory containing a .git directory is used.
        validation_callback: An optional callback function that validates the repository root.

    Returns:
        A Repository instance, or None if discovery/open fails.
    """
    if repo_root is None:
        repo_root = pygit2.discover_repository(str(Path.cwd()))
        if not repo_root:
            return None

    if validation_callback is not None and not validation_callback(repo_root):
        return None

    try:
        repo = pygit2.Repository(repo_root)
    except pygit2.GitError as e:
        carb.log_error(e)
        return None

    return repo


def initialize_submodules(repository: Optional[pygit2.Repository]) -> bool:
    """
    Initialize and update all the submodules in the repository.

    Args:
        repository: The repository instance to initialize submodules for.

    Returns:
        True if the submodules were initialized and updated successfully, False otherwise.
    """
    if repository is None:
        return False

    try:
        repository.submodules.init()
        repository.submodules.update()
    except pygit2.GitError as e:
        carb.log_error(f"Failed to initialize submodules: {e}")
        return False

    return True


def rebase_repository(repository: Optional[pygit2.Repository], local_oid: pygit2.Oid, remote_oid: pygit2.Oid) -> bool:
    """
    Rebase local commits onto a remote branch using cherry-pick operations.

    This function performs a manual rebase by:
    1. Finding the merge base (common ancestor) between local and remote
    2. Collecting all local commits that need to be rebased
    3. Resetting to the remote branch
    4. Cherry-picking each local commit onto the new base

    The operation is atomic - if any step fails, the repository is restored to its original state.

    Args:
        repository: The repository instance to rebase.
        local_oid: The OID of the local HEAD (starting point).
        remote_oid: The OID of the remote HEAD (target base).

    Returns:
        True if the rebase was successful, False if the rebase failed (e.g., conflicts detected, no common ancestor
        found).
    """
    if repository is None:
        return False

    # Save original HEAD for rollback in case of failure
    original_head = local_oid

    try:
        # 1. Find the merge base (common ancestor)
        merge_base_oid = repository.merge_base(local_oid, remote_oid)

        # Handle the case where there's no common history
        if merge_base_oid is None:
            carb.log_error("Cannot rebase: no common ancestor found between local and remote branches")
            return False

        # 2. Collect all local commits that need to be rebased
        commits_to_rebase = []
        walker = repository.walk(local_oid)
        walker.hide(merge_base_oid)
        for commit in walker:
            commits_to_rebase.append(commit)
        commits_to_rebase.reverse()  # Apply oldest commits first

        # 3. Reset to remote branch
        repository.reset(remote_oid, pygit2.GIT_RESET_HARD)

        # 4. Cherry-pick each local commit
        for cherry in commits_to_rebase:
            # Get the base tree (parent of the commit being cherry-picked)
            base_tree = cherry.parents[0].tree if cherry.parents else repository[repository.head.target].tree

            # Get the current branch head tree
            current_head = repository.head.target
            current_tree = repository[current_head].tree

            # Perform three-way merge
            index = repository.merge_trees(base_tree, current_tree, cherry.tree)

            # Check for conflicts
            if index.conflicts is not None:
                raise pygit2.GitError(f"Conflict detected during rebase of commit: {cherry.id}")

            # Create the rebased commit
            repository.create_commit(
                "HEAD",
                cherry.author,
                repository.default_signature,
                cherry.message,
                index.write_tree(repository),
                [current_head],
            )

        # Reset index and working tree to match the new HEAD. This ensures the index is clean after the rebase
        repository.reset(repository.head.target, pygit2.GIT_RESET_HARD)

        return True

    except pygit2.GitError as e:
        # Rollback: restore original HEAD state
        repository.reset(original_head, pygit2.GIT_RESET_HARD)

        carb.log_error(f"Rebase failed, rolled back to original state: {e}")
        return False


def pull_repository(repository: Optional[pygit2.Repository], force: bool = False) -> bool:
    """
    Pull the latest changes from the remote repository.

    This function follows a simple workflow:
    1. Stash any uncommitted changes (unless force=True)
    2. If not ahead of remote: fast-forward to remote
    3. If ahead of remote: rebase local commits onto remote
    4. Unstash changes

    The operation is atomic - either succeeds completely or leaves the repository
    in its original state with original uncommitted changes intact.

    Args:
        repository: A Repository instance, or None if discovery/open fails.
        force: If True, discards all local changes and commits, performing a hard reset
               to remote. If False (default), attempts to preserve and rebases local commits.

    Returns:
        True if the pull was successful or already up to date, False if the pull failed.
        On failure, errors are logged and the repository is restored to its original state.
    """
    if repository is None:
        return False

    try:
        ahead, behind = get_remote_ahead_behind(repository)
    except ValueError as e:
        carb.log_error(f"Failed to get ahead and behind counts: {e}")
        return False

    # Already up to date with remote
    if behind == 0:
        return True

    local_oid = get_local_commit(repository)
    remote_oid = get_remote_commit(repository)

    # Force mode: discard everything and hard reset to remote
    if force:
        repository.reset(remote_oid, pygit2.GIT_RESET_HARD)
        return True

    stash_oid = None
    success = True

    try:
        # Step 1: Stash uncommitted changes
        if has_uncommitted_changes(repository):
            stash_oid = repository.stash(repository.default_signature, message="Auto-stash before pull")

        # Step 2: Fast-forward if not ahead
        if ahead == 0:
            repository.reset(remote_oid, pygit2.GIT_RESET_HARD)

        # Step 3: Rebase if ahead
        else:
            success = rebase_repository(repository, local_oid, remote_oid)

        # Step 4: Unstash
        if stash_oid is not None and not _pop_stash(repository, stash_oid):
            # If stash pop failed after a successful rebase or fast-forward, roll back to original state
            repository.reset(local_oid, pygit2.GIT_RESET_HARD)
            # Try to pop the stash again at the original state
            _pop_stash(repository, stash_oid)
            return False

    except pygit2.GitError as e:
        # Ensure we restore stashed changes on any failure
        if stash_oid is not None:
            _pop_stash(repository, stash_oid)
        carb.log_error(f"Pull failed: {e}")
        return False

    return success


def get_branch(repository: Optional[pygit2.Repository]) -> str | None:
    """
    Get the current git branch.

    Args:
        repository: A Repository instance, or None if discovery/open fails.

    Returns:
        The git branch, or None if the branch cannot be found. Returns "HEAD" if detached.
    """
    if repository is None:
        return None

    if repository.head_is_detached:
        return "HEAD"

    # Get the branch name from HEAD
    head_ref = repository.references.get("HEAD")
    target = head_ref.target
    if target.startswith("refs/heads/"):
        return target.replace("refs/heads/", "")

    return "HEAD"


def get_local_commit(repository: Optional[pygit2.Repository]) -> Optional[pygit2.Oid]:
    """
    Return the local commit (HEAD) as a pygit2.Oid or None.

    Args:
        repository: A Repository instance, or None if discovery/open fails.

    Returns:
        The Oid for the HEAD commit
    """
    if repository is None:
        return None

    if repository.head_is_unborn:
        return None

    return repository.head.target


def get_remote_commit(repository: Optional[pygit2.Repository]) -> Optional[pygit2.Oid]:
    """
    Fetch and return the latest remote commit for the current branch (origin/<branch>)
    as a pygit2.Oid, or None if unavailable.

    Args:
        repository: A Repository instance, or None if discovery/open fails.

    Raises:
        pygit2.GitError: If the remote commit cannot be fetched.

    Returns:
        The Oid for the latest remote commit on the current branch
    """
    if repository is None:
        return None

    # Fetch from origin
    remote = repository.remotes["origin"]
    remote.fetch()

    # Get current branch name
    if repository.head_is_detached or repository.head_is_unborn:
        return None

    branch_name = get_branch(repository)
    if not branch_name or branch_name == "HEAD":
        return None

    # Get the remote tracking branch
    remote_ref_name = f"refs/remotes/origin/{branch_name}"
    try:
        remote_ref = repository.references.get(remote_ref_name)
        if remote_ref:
            return remote_ref.target
    except KeyError:
        return None

    return None


def has_uncommitted_changes(repository: Optional[pygit2.Repository]) -> bool:
    """
    Check if the repository has uncommitted changes (modified or staged files).

    This checks for differences between HEAD and the index, and between the index
    and the working directory. Untracked files are intentionally ignored.

    Args:
        repository: A Repository instance, or None if discovery/open fails.

    Returns:
        True if there are uncommitted changes, False otherwise.
    """
    if repository is None:
        return False

    # Check for staged changes (index vs HEAD)
    # diff(cached=True) compares index to HEAD
    staged_diff = repository.diff(cached=True)
    if len(staged_diff) > 0:
        return True

    # Check for unstaged changes (working directory vs index)
    # diff() with no arguments compares working directory to index
    unstaged_diff = repository.diff()
    if len(unstaged_diff) > 0:
        return True

    return False


def get_remote_ahead_behind(repository: Optional[pygit2.Repository]) -> tuple[int, int]:
    """
    Get the number of commits the local branch is ahead and behind the remote branch.

    Args:
        repository: A Repository instance, or None if discovery/open fails.

    Raises:
        ValueError: if the comparison cannot be made (e.g., no remote configured, no network, or commits are equal).
        pygit2.GitError: If the remote commit cannot be fetched.

    Returns:
        A tuple of (ahead, behind) counts
    """
    if repository is None:
        raise ValueError("Repository does not exist")

    local_oid = get_local_commit(repository)
    remote_oid = get_remote_commit(repository)

    # If we can't get remote (e.g., no remote configured or no network), we can't determine the relationship
    if not local_oid or not remote_oid:
        raise ValueError("No local or remote commit found. Cannot determine ahead and behind counts.")

    if local_oid == remote_oid:
        return (0, 0)

    # Use ahead_behind to determine relationship
    return repository.ahead_behind(local_oid, remote_oid)


def has_local_changes(repository: Optional[pygit2.Repository]) -> bool:
    """
    Check if the repository has local changes (uncommitted changes or non-pushed commits).

    This is a convenience method that combines has_uncommitted_changes() and is_ahead_of_remote().

    Args:
        repository: A Repository instance, or None if discovery/open fails.

    Returns:
        True if there are uncommitted changes or non-pushed commits, False otherwise.
    """
    ahead, _ = get_remote_ahead_behind(repository)
    return has_uncommitted_changes(repository) or ahead > 0


def _pop_stash(repository: Optional[pygit2.Repository], stash_oid: pygit2.Oid) -> bool:
    """
    Find a stash by its OID, apply it, and drop it.

    Args:
        repository: The repository instance.
        stash_oid: The OID of the stash to apply and drop.

    Returns:
        True if the stash was successfully applied and dropped, False otherwise.
    """
    if repository is None:
        return False

    try:
        # Find the stash index by OID
        stash_list = repository.listall_stashes()
        stash_index = None
        for index in range(len(stash_list)):
            try:
                # Get the stash commit at this index
                stash_commit = repository.revparse_single(f"stash@{{{index}}}")
                if stash_commit.id == stash_oid:
                    stash_index = index
                    break
            except (KeyError, pygit2.GitError):
                continue

        if stash_index is None:
            carb.log_error("Failed to find stashed changes. The stash may have been removed.")
            return False

        # Apply the stash
        repository.stash_apply(index=stash_index)

        # Check for conflicts after applying
        index = repository.index
        if index.conflicts is not None:
            carb.log_error("Conflict detected when applying stashed changes.")
            # Clean up the conflicted state
            repository.state_cleanup()
            return False

        # If no conflicts, drop the stash
        repository.stash_drop(index=stash_index)
        return True

    except pygit2.GitError as e:
        carb.log_error(f"Failed to apply stashed changes: {e}")
        carb.log_warn("Your stashed changes are still saved. Use 'git stash pop' manually to restore them.")
        return False


def _validate_output_directory(repository_url: str, output_directory: str) -> str:
    """
    Validate the output directory for a repository clone. Ensures the output directory ends with the repository name.

    Args:
        repository_url: The repository URL to clone from.
        output_directory: The output directory to clone the repository to.

    Raises:
        ValueError: If the repository URL does not end with .git

    Returns:
        The validated output directory.
    """
    if not repository_url.endswith(".git"):
        raise ValueError("Repository URL must end with .git")

    # Get the repository name by removing the .git extension
    repository_name = repository_url.split("/")[-1][:-4]
    # If the output directory doesn't end with the repository name, add it
    output_path = Path(output_directory)
    if output_path.parts[-1] != repository_name:
        output_path = output_path / repository_name

    return str(output_path)
