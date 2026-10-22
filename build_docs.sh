#!/bin/bash
set -e
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export PYTHONNOUSERSITE="${PYTHONNOUSERSITE:-1}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
DOCS_PYTHON="$SCRIPT_DIR/_build/target-deps/python/bin/python3"
if [ ! -x "$DOCS_PYTHON" ]; then
    DOCS_PYTHON="$SCRIPT_DIR/_build/target-deps/python/python"
fi
if [ ! -x "$DOCS_PYTHON" ]; then
    echo "Docs Python not found in $SCRIPT_DIR/_build/target-deps/python. Run build.sh before build_docs.sh."
    exit 1
fi
export PM_PYTHON_EXT="$DOCS_PYTHON"
# Use the app pydantic version (deps/pip_flux.toml) so autodoc imports the extensions the same way.
"$DOCS_PYTHON" "$SCRIPT_DIR/tools/utils/docs_constraints.py" > "$SCRIPT_DIR/_build/docs_constraints.txt"
"$DOCS_PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.docs.txt" -c "$SCRIPT_DIR/_build/docs_constraints.txt"
"$SCRIPT_DIR/repo.sh" docs "$@"
