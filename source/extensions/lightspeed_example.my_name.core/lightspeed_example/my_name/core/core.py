"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""


class _SetupCore:
    def print_hello_1(self):
        print("Hello 1")

    def print_hello_2(self):
        print("Hello 2")


def create_core():
    return _SetupCore()
