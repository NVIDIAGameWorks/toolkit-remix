"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from functools import partial
from typing import Dict, Optional

from lightspeed.error_popup.window import ErrorPopup as _ErrorPopup
from lightspeed.trex.project_wizard.core import ProjectWizardCore as _ProjectWizardCore
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.start_page.widget import WizardStartPage as _WizardStartPage
from omni import ui, usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.wizard.widget import WizardModel as _WizardModel
from omni.flux.wizard.window import WizardWindow as _WizardWindow


class ProjectWizardWindow:
    def __init__(self, context_name: str = ""):
        self._default_attrs = {
            "_context_name": None,
            "_wizard_core": None,
            "_wizard_window": None,
            "_wizard_completed_sub": None,
            "_setup_finished_sub": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._wizard_core = _ProjectWizardCore()

        self._wizard_window = _WizardWindow(
            _WizardModel(_WizardStartPage(context_name=self._context_name)),
            title="RTX Remix Project Wizard",
            width=700,
            height=400,
            flags=ui.WINDOW_FLAGS_NO_DOCKING
            | ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
            | ui.WINDOW_FLAGS_NO_MOVE
            | ui.WINDOW_FLAGS_NO_RESIZE,
        )

        self._wizard_completed_sub = self._wizard_window.widget.subscribe_wizard_completed(self._on_wizard_completed)
        self._setup_finished_sub = None

    def _on_wizard_completed(self, payload: Dict):
        self._setup_finished_sub = self._wizard_core.subscribe_run_finished(partial(self._on_setup_completed, payload))
        self._wizard_core.setup_project(payload)

    def _on_setup_completed(self, payload: Dict, success: bool, error: Optional[str]):
        if not success:
            _ErrorPopup(
                "Project Creation Error Occurred",
                "An error occurred while creating the project.",
                details=error,
                window_size=(400, 250),
            ).show()
            return
        usd.get_context(self._context_name).open_stage(str(payload.get(_ProjectWizardKeys.PROJECT_FILE.value, "")))
        self._setup_finished_sub = None

    def show_project_wizard(self, reset_page: bool = True):
        self._wizard_window.show_wizard(reset_page=reset_page)

    def destroy(self):
        _reset_default_attrs(self)
