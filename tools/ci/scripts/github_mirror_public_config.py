"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

# Body of the git-filter-repo --commit-callback used by github_mirror_sync.sh; git-filter-repo supplies `commit` and
# `FileChange`. Commits exported before this file was introduced keep their exact identity so the mirror push stays a
# fast-forward. From that commit on, the exported packman config is the public one, which has no internal remotes.
config_path = b"tools/packman/config.packman.xml"
public_path = b"tools/packman/external_config.packman.xml"
# Path this file was first committed at. Keep it even if the file moves; another value rewrites exported history.
activation_path = b"tools/ci/scripts/github_mirror_public_config.py"

states = globals().setdefault("_github_mirror_public_config_states", {})
active, public_blob = states.get(commit.parents[0], (False, None)) if commit.parents else (False, None)
for change in commit.file_changes:
    if change.type != b"M":
        continue
    if change.filename == public_path:
        public_blob = change.blob_id
    elif change.filename == activation_path:
        active = True
states[commit.id] = (active, public_blob)
if active and public_blob is not None:
    commit.file_changes = [change for change in commit.file_changes if change.filename != config_path]
    commit.file_changes.append(FileChange(b"M", config_path, public_blob, b"100644"))
