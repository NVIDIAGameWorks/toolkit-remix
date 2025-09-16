import json
import re
from pathlib import Path


def load_json_safe(text: str) -> dict:
    # Remove // line comments
    text = re.sub(r"(^|\s)//.*$", "", text, flags=re.MULTILINE)
    # Remove /* block comments */
    text = re.sub(r"/\*([\s\S]*?)\*/", "", text, flags=re.MULTILINE)
    # Remove trailing commas before } or ]
    text = re.sub(r",(?=\s*[}\]])", "", text)
    return json.loads(text)


def read_vscode_settings(settings_path: Path) -> dict:
    if not settings_path.exists():
        raise FileNotFoundError(f"VSCode settings not found at: {settings_path}")
    with settings_path.open("r", encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return load_json_safe(text)


def normalize_extra_paths(extra_paths: list[str], workspace_root: Path) -> list[str]:
    normalized: set[str] = set()
    workspace_marker = "${workspaceFolder}"
    for raw_path in extra_paths:
        # Expand ${workspaceFolder} if present, otherwise keep paths relative to workspace root
        if isinstance(raw_path, str) and raw_path:
            if raw_path.startswith(workspace_marker):
                if raw_path.startswith(workspace_marker + "/") or raw_path.startswith(workspace_marker + "\\"):
                    rel = raw_path[len(workspace_marker) + 1:]
                elif raw_path == workspace_marker:
                    rel = ""
                else:
                    # Handle malformed ${workspaceFolder} usage
                    rel = raw_path[len(workspace_marker):]
                search_path = (workspace_root / rewrite_build_exts_path(rel))
                if search_path.exists():
                    normalized.add(search_path.as_posix())
            else:
                # Store as POSIX-style relative path for pyrightconfig.json
                search_path = (workspace_root / rewrite_build_exts_path(raw_path))
                if search_path.exists():
                    normalized.add(search_path.as_posix())
    return sorted(list(normalized))


def rewrite_build_exts_path(path_str: str) -> str:
    """If path starts with _build/<platform>/<config>/exts/, replace that prefix with source/extensions/."""
    posix = path_str.replace("\\", "/")
    match = re.match(r"^_build/[^/]+/[^/]+/exts/(.*)$", posix)
    if match:
        return "source/extensions/" + match.group(1)
    return posix


def build_config(extra_paths: list[str]) -> dict:
    return {
        "typeCheckingMode": "standard",
        "executionEnvironments": [
            {
                "root": ".",
                "extraPaths": extra_paths,
            }
        ],
        "include": ["source"],
    }


def write_config(config_path: Path, config: dict) -> None:
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def main() -> int:
    workspace_root = Path(__file__).resolve().parents[2]
    settings_path = workspace_root / ".vscode" / "settings.json"
    config_path = workspace_root / "pyrightconfig.json"

    settings = read_vscode_settings(settings_path)
    extra_paths_setting = settings.get("python.analysis.extraPaths", [])
    extra_paths = normalize_extra_paths(extra_paths_setting, workspace_root)

    config = build_config(extra_paths)
    write_config(config_path, config)

    print(f"Wrote {config_path.relative_to(workspace_root)} with {len(extra_paths)} extraPaths entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
