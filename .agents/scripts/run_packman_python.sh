#!/usr/bin/env bash
set -u

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT" || exit 2

PLATFORM="$(uname -s 2>/dev/null || true):${OSTYPE:-}"
case "$PLATFORM" in
    *MINGW*|*MSYS*|*CYGWIN*|*mingw*|*msys*|*cygwin*)
        if command -v cygpath >/dev/null 2>&1; then
            ROOT_WIN=$(cygpath -w "$ROOT")
        else
            ROOT_WIN=$(pwd -W)
        fi
        WIN_ARGS=("$ROOT_WIN\\.agents\\scripts\\run_packman_python.cmd")
        for ARG in "$@"; do
            if [ -e "$ARG" ] && command -v cygpath >/dev/null 2>&1; then
                WIN_ARGS+=("$(cygpath -w "$ARG")")
            else
                WIN_ARGS+=("$ARG")
            fi
        done
        MSYS2_ARG_CONV_EXCL='*' exec cmd.exe /d /c "${WIN_ARGS[@]}"
        ;;
esac

TMPDIR_RUNNER=$(mktemp -d "${TMPDIR:-/tmp}/lightspeed-packman-python.XXXXXX") || exit 2
cleanup() {
    rm -rf "$TMPDIR_RUNNER"
}
trap cleanup EXIT

OUT="$TMPDIR_RUNNER/out"
ERR="$TMPDIR_RUNNER/err"
CODE="$TMPDIR_RUNNER/code"
BOOT="$TMPDIR_RUNNER/boot"

"$ROOT/tools/packman/python.sh" "$ROOT/.agents/scripts/packman_python_entry.py" --stdout-file "$OUT" --stderr-file "$ERR" --exit-code-file "$CODE" -- "$@" >"$BOOT" 2>&1
PM_CODE=$?

[ -f "$OUT" ] && cat "$OUT"
[ -f "$ERR" ] && cat "$ERR" >&2
if [ -f "$CODE" ]; then
    SCRIPT_CODE=$(cat "$CODE")
    case "$SCRIPT_CODE" in
        ''|*[!0-9]*)
            SCRIPT_CODE=1
            ;;
    esac
else
    cat "$BOOT" >&2
    SCRIPT_CODE=$PM_CODE
fi

exit "$SCRIPT_CODE"
