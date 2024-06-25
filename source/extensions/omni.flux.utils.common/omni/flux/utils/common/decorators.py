"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import functools
import threading
from typing import Dict, List


def limit_recursion(num_allowed_recursive_calls: int = 0, error: bool = False):
    """
    This decorator is used to restrict the number of recursive calls a function can make.

    Any returned value from the decorated method is discarded.

    Kwargs:
        num_allowed_recursive_calls (int): The maximum allowed depth for recursion in this decorated function. The
            value does not include the initial call. Default value is zero which means any recursive calls are ignored.
        error (bool): If True and number of recursive call exceeds `num_allowed_recursive_calls` then a RecursionError
            is raised.

    Raises:
        RecursionError: If error is True and number of recursive calls exceeds `num_allowed_recursive_calls`.

    Examples:
    >>> @limit_recursion(num_allowed_recursive_calls=2)
    >>> def inc(store, i=0):
    ...     i += 1
    ...     store.append(i)
    ...     inc(store, i)
    >>> cache = []
    >>> inc(cache)
    >>> assert cache == [1, 2, 3]
    """

    def _deco(func):

        _lock = threading.RLock()

        @functools.wraps(func)
        def _wrap(*args, **kwargs):
            with _lock:
                if _wrap.call_depth > num_allowed_recursive_calls:
                    if error:
                        raise RecursionError(f"Maximum number of recursive calls reached {num_allowed_recursive_calls}")
                    return
                _wrap.call_depth += 1
                try:
                    func(*args, **kwargs)
                finally:
                    _wrap.call_depth -= 1

        # initial value
        _wrap.call_depth = 0

        return _wrap

    return _deco


def ignore_function_decorator(attrs: List[str] = None):
    """
    This decorator will break the infinite loop if a function calls itself

    Args:
        attrs:  list of attributes
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            for attr in attrs:
                if hasattr(self, attr) and getattr(self, attr):
                    return
                setattr(self, attr, True)
            func(self, *args, **kwargs)
            for attr in attrs:
                setattr(self, attr, False)

        return wrapper

    return decorator


def ignore_function_decorator_async(attrs: List[str] = None):
    """
    This decorator will break the infinite loop if a function calls itself

    Args:
        attrs:  list of attributes
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            for attr in attrs:
                if hasattr(self, attr) and getattr(self, attr):
                    return
                setattr(self, attr, True)
            await func(self, *args, **kwargs)
            for attr in attrs:
                setattr(self, attr, False)

        return wrapper

    return decorator


def ignore_function_decorator_and_reset_value(attrs: Dict[str, bool] = None):
    """
    This decorator will break the infinite loop if a function calls itself.
    If the given attribute already exist and have a True value, we can set a new value to it

    Args:
        attrs:  list of attributes
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
    """
    Set new attributes before and after that the function is executed

    Args:
        attrs: list of attributes to set
    """

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
