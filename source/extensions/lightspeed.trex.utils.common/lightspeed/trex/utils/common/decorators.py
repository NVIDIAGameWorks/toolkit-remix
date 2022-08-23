"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import functools
from typing import Dict, List


def ignore_function_decorator(attrs: List[str] = None):
    """
    This decorator will break the infinite loop if a function calls itself

    Args:
        attrs:  list of attributes

    Returns:

    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            for attr in attrs:
                if getattr(self, attr):
                    return
                setattr(self, attr, True)
            func(self, *args, **kwargs)
            for attr in attrs:
                setattr(self, attr, False)

        return wrapper

    return decorator


def ignore_function_decorator_and_reset_value(attrs: Dict[str, bool] = None):
    """
    This decorator will break the infinite loop if a function calls itself

    Args:
        attrs:  list of attributes

    Returns:

    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            for attr, value in attrs.items():
                if getattr(self, attr):
                    setattr(self, attr, value)
                    return
                setattr(self, attr, True)
            func(self, *args, **kwargs)
            for attr in attrs:
                setattr(self, attr, False)

        return wrapper

    return decorator


def sandwich_attrs_function_decorator(attrs: List[str] = None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            for attr in attrs:
                setattr(self, attr, True)
            func(self, *args, **kwargs)
            for attr in attrs:
                setattr(self, attr, False)

        return wrapper

    return decorator
