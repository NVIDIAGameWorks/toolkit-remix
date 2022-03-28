"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui
from lightspeed_example.my_name.widget import create_widget


class _SetupWindow:

    WINDOW_NAME = "Window example"

    def __init__(self):
        """Window"""
        self.__default_attr = {"_window": None, "_widget": None}
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self.__create_ui()

    @property
    def widget(self):
        return self._widget

    @property
    def window(self):
        return self._window

    def __create_ui(self):
        """Create the main UI"""
        self._window = ui.Window(self.WINDOW_NAME, name=self.WINDOW_NAME, width=400, height=300)
        with self._window.frame:
            self._widget = create_widget()

    def destroy(self):
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)


def create_window():
    return _SetupWindow()
