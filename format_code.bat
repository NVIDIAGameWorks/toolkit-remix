@echo off
setlocal enabledelayedexpansion

REM Enhanced format_code.bat with file-specific formatting support
REM Usage: format_code.bat [options] [files...]
REM
REM Additional options:
REM   -f, --files FILE1 FILE2 ...  Format specific files (overrides other filters)
REM   --help                        Show this help message and repo format help
REM
REM All other options are passed through to 'repo format'

REM Store the script directory early
set "SCRIPT_DIR=%~dp0"

REM Check for help flag first
if "%~1"=="--help" goto show_help
if "%~1"=="-h" goto show_help

REM Parse arguments to check for -f or --files
set "FILES_MODE="
set "FILE_LIST="
set "OTHER_ARGS="
set "COLLECTING_FILES="

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

    echo Formatting specific files:!FILE_LIST!
    echo.

    REM Format with black
    call "%SCRIPT_DIR%repo.bat" format python-black --args="!OTHER_ARGS!!FILE_LIST!"

    if errorlevel 1 (
        echo.
        echo Error: Black formatting failed
        exit /b 1
    )

    echo.
    echo Done!
) else (
    REM Pass through to standard repo format
    call "%SCRIPT_DIR%repo.bat" format !OTHER_ARGS!
)

goto end

:show_help
echo Enhanced format_code.bat - Format code with additional file-specific options
echo.
echo Usage: format_code.bat [options] [files...]
echo.
echo Additional options:
echo   -f, --files FILE1 FILE2 ...  Format specific files (supports multiple files)
echo                                 Example: format_code.bat -f file1.py file2.py
echo                                 Example: format_code.bat -f --check file.py
echo.
echo Standard repo format options:
echo ============================================================
call "%SCRIPT_DIR%repo.bat" format --help
goto end

:show_usage
echo Usage: format_code.bat [options]
echo        format_code.bat -f FILE1 [FILE2 ...]
echo        format_code.bat --files FILE1 [FILE2 ...]
echo.
echo Run 'format_code.bat --help' for more information
exit /b 1

:end
endlocal
