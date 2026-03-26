@echo off
:: Run the manual property panel playground from any working directory.
:: This script navigates to the repo root automatically.

pushd "%~dp0\..\..\..\..\"

.\_build\windows-x86_64\release\kit\kit.exe ^
    --enable omni.flux.property_widget_builder.model.usd ^
    --ext-folder "./_build/windows-x86_64/release/exts" ^
    --ext-folder "./_build/windows-x86_64/release/extscache" ^
    --portable-root "./_build/windows-x86_64/release" ^
    --exec "source/extensions/omni.flux.property_widget_builder.delegates/bin/manual_property_panel_playground.py"

popd
