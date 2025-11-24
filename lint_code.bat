@echo off
setlocal enabledelayedexpansion

REM Enhanced lint_code.bat with file-specific linting support
REM Usage: lint_code.bat [linter] [options] [files...]
REM
REM Additional options:
REM   -f, --files FILE1 FILE2 ...  Lint specific files (lints each file separately)
REM   --help                        Show this help message and repo lint help
REM
REM All other options are passed through to 'repo lint'

REM Store the script directory early
set "SCRIPT_DIR=%~dp0"

REM Check for help flag first
if "%~1"=="--help" goto show_help
if "%~1"=="-h" goto show_help

REM Default linter
set "LINTER=flake8"
set "LINTER_SET="
set "FILES_MODE="
set "FILE_LIST="
set "OTHER_ARGS="
set "COLLECTING_FILES="

REM Check if first arg is a linter name
if "%~1"=="all" (
    set "LINTER=all"
    set "LINTER_SET=1"
    shift
)
if "%~1"=="gitlint" (
    set "LINTER=gitlint"
    set "LINTER_SET=1"
    shift
)
if "%~1"=="ruff" (
    set "LINTER=ruff"
    set "LINTER_SET=1"
    shift
)
if "%~1"=="flake8" (
    set "LINTER=flake8"
    set "LINTER_SET=1"
    shift
)
if "%~1"=="mypy" (
    set "LINTER=mypy"
    set "LINTER_SET=1"
    shift
)

:parse_loop
if "%~1"=="" goto done_parsing

if "%~1"=="-f" (
    set "FILES_MODE=1"
    set "COLLECTING_FILES=1"
    shift
    goto parse_loop
)

if "%~1"=="--files" (
    set "FILES_MODE=1"
    set "COLLECTING_FILES=1"
    shift
    goto parse_loop
)

REM If we're collecting files and hit another flag, stop collecting
if defined COLLECTING_FILES (
    if "%~1:~0,1%"=="-" (
        set "COLLECTING_FILES="
    )
)

REM Collect files or other args
if defined COLLECTING_FILES (
    set "FILE_LIST=!FILE_LIST! %~1"
) else (
    set "OTHER_ARGS=!OTHER_ARGS! %~1"
)

shift
goto parse_loop

:done_parsing

REM Execute based on mode
if defined FILES_MODE (
    if "!FILE_LIST!"=="" (
        echo Error: -f/--files requires at least one file path
        echo.
        goto show_usage
    )

    echo Linting specific files with %LINTER%:!FILE_LIST!
    echo.

    REM Lint each file separately for clearer output
    for %%f in (!FILE_LIST!) do (
        echo.
        echo === Linting: %%f ===
        call "%SCRIPT_DIR%repo.bat" lint %LINTER% !OTHER_ARGS! "%%f"
        if errorlevel 1 (
            set "HAD_ERRORS=1"
        )
    )

    if defined HAD_ERRORS (
        echo.
        echo Some files have linting errors.
        exit /b 1
    )

    echo.
    echo All files passed linting!
) else (
    REM Pass through to standard repo lint
    call "%SCRIPT_DIR%repo.bat" lint %LINTER% !OTHER_ARGS!
)

goto end

:show_help
echo Enhanced lint_code.bat - Lint code with additional file-specific options
echo.
echo Usage: lint_code.bat [linter] [options] [files...]
echo.
echo Linters: all, gitlint, ruff, flake8 (default), mypy
echo.
echo Additional options:
echo   -f, --files FILE1 FILE2 ...  Lint specific files (lints each separately)
echo                                 Example: lint_code.bat -f file1.py file2.py
echo                                 Example: lint_code.bat flake8 -f file.py
echo                                 Example: lint_code.bat ruff -f file1.py file2.py
echo.
echo Standard repo lint options:
echo ============================================================
call "%SCRIPT_DIR%repo.bat" lint --help
echo.
echo.
echo For linter-specific options:
call "%SCRIPT_DIR%repo.bat" lint flake8 --help
goto end

:show_usage
echo Usage: lint_code.bat [linter] [options]
echo        lint_code.bat [linter] -f FILE1 [FILE2 ...]
echo        lint_code.bat [linter] --files FILE1 [FILE2 ...]
echo.
echo Run 'lint_code.bat --help' for more information
exit /b 1

:end
endlocal
