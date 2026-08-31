"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

__all__ = [
    "BlockFormat",
    "MipmapFilter",
    "NvttUnavailableError",
    "encode_dds",
    "is_available",
]

import collections.abc
import contextlib
import ctypes
import enum
import os
import pathlib
import threading

import carb
import carb.tokens

# The library ships in the packman delivered tool directory, beside nvtt_export.exe, which imports
# it. Nothing here reads an installed copy, so the application stays self contained.
_NVTT_DIR_TOKEN = "${omni.flux.resources}/deps/tools/nvtt"
# The file name carries the version, such as nvtt30205.dll, so match the pattern instead. A
# packman bump then needs no change here.
_LIBRARY_GLOB = "nvtt3*.dll"


class NvttUnavailableError(RuntimeError):
    """The NVTT shared library could not be loaded."""


class MipmapFilter(enum.IntEnum):
    """Mipmap filters, matching ``NvttMipmapFilter`` in ``nvtt_wrapper.h``."""

    BOX = 0
    TRIANGLE = 1
    KAISER = 2
    MITCHELL = 3
    MIN = 4
    MAX = 5


class BlockFormat(enum.IntEnum):
    """The block formats this module supports, matching ``NvttFormat`` ordinals.

    ``NvttFormat`` aliases its DX9 and DX10 names, so the ordinals are not sequential with the
    declaration order. ``encode_dds`` asserts the written DDS header, which fails loudly if a
    caller passes a raw ordinal.
    """

    BC4 = 6
    BC5 = 9
    BC7 = 15


# nvtt_export defaults.
_QUALITY_NORMAL = 1
_CONTAINER_DDS10 = 1
_TRUE = 1
_FALSE = 0

# NVTT 2023.4.0 lets its own context choose a device and call cudaSetDevice(), which can move
# work off the intended GPU. A subprocess can pin GPU 0 with CUDA_VISIBLE_DEVICES, which is not
# usable here because that variable is process wide and this process also runs the renderer.
# nvttUseCurrentDevice stops NVTT from choosing, and then this module makes device 0 current on
# every thread that encodes.
_PINNED_DEVICE = 0
_CUDA_SUCCESS = 0

_lock = threading.Lock()
_library: ctypes.CDLL | None = None
_load_error: str | None = None
# None until a thread that has pinned its device asks. nvtt_lowlevel.h documents
# nvttIsCudaSupported as able to choose a device and call cudaSetDevice, so loading the library
# must never ask, or is_available() would move the GPU of whatever thread called it.
_cuda_supported: bool | None = None


class _ContextHolder:
    """One thread's cached NVTT contexts, freed the moment this holder is collected.

    ``threading.local`` does not call a subclass's own ``__del__`` when a worker thread exits:
    the per-thread state it manages is a plain attribute dict, not a Python object, so no
    finalizer runs for it. Storing the contexts on this separate object instead, as the value of
    a thread-local attribute, gives them a real reference count: it drops to zero, and this
    class's ``__del__`` runs, the moment that per-thread attribute dict is torn down, which
    CPython does synchronously when the owning thread exits.
    """

    def __init__(self) -> None:
        self.contexts: dict[bool, ctypes.c_void_p] = {}
        # Captured from the loaded library the first time this holder creates a context, so
        # __del__ never has to read a module global that shutdown may already have cleared. The
        # DLL itself stays loaded for the life of the process, so the captured function pointer
        # stays callable even after that.
        self.destroy_context: collections.abc.Callable[[ctypes.c_void_p], None] | None = None

    def __del__(self) -> None:
        """Destroy every context this holder cached, once each, then forget them."""
        destroy, contexts = self.destroy_context, self.contexts
        self.contexts = {}
        if destroy is None:
            return
        for context in contexts.values():
            with contextlib.suppress(Exception):
                destroy(context)


class _ThreadState(threading.local):
    """The NVTT state one thread owns.

    NVTT documents a context as single threaded, so every encoding thread keeps its own.
    ``threading.local`` runs ``__init__`` once per thread that touches the instance, so every
    field below exists without a lookup by name. The context cache lives on ``holder``, a plain
    object, rather than directly on this ``threading.local`` subclass, so it is freed
    deterministically when the thread exits; see ``_ContextHolder``.
    """

    def __init__(self) -> None:
        self.device_pinned = False
        self.holder = _ContextHolder()


_thread_state = _ThreadState()


def _bind(library: ctypes.CDLL) -> None:
    """Declare the argument and return types of every function this module calls.

    Each declaration is written out, so the bound names are greppable and nothing resolves by
    string at run time.
    """
    handle = ctypes.c_void_p
    number = ctypes.c_int
    text = ctypes.c_char_p
    number_out = ctypes.POINTER(ctypes.c_int)

    library.nvttIsCudaSupported.argtypes = []
    library.nvttIsCudaSupported.restype = number
    library.nvttUseCurrentDevice.argtypes = []
    library.nvttUseCurrentDevice.restype = None

    library.nvttCreateContext.argtypes = []
    library.nvttCreateContext.restype = handle
    library.nvttDestroyContext.argtypes = [handle]
    library.nvttDestroyContext.restype = None
    library.nvttSetContextCudaAcceleration.argtypes = [handle, number]
    library.nvttSetContextCudaAcceleration.restype = None
    library.nvttContextOutputHeader.argtypes = [handle, handle, number, handle, handle]
    library.nvttContextOutputHeader.restype = number
    library.nvttContextCompress.argtypes = [handle, handle, number, number, handle, handle]
    library.nvttContextCompress.restype = number

    library.nvttCreateCompressionOptions.argtypes = []
    library.nvttCreateCompressionOptions.restype = handle
    library.nvttDestroyCompressionOptions.argtypes = [handle]
    library.nvttDestroyCompressionOptions.restype = None
    library.nvttSetCompressionOptionsFormat.argtypes = [handle, number]
    library.nvttSetCompressionOptionsFormat.restype = None
    library.nvttSetCompressionOptionsQuality.argtypes = [handle, number]
    library.nvttSetCompressionOptionsQuality.restype = None

    library.nvttCreateOutputOptions.argtypes = []
    library.nvttCreateOutputOptions.restype = handle
    library.nvttDestroyOutputOptions.argtypes = [handle]
    library.nvttDestroyOutputOptions.restype = None
    library.nvttSetOutputOptionsFileName.argtypes = [handle, text]
    library.nvttSetOutputOptionsFileName.restype = None
    library.nvttSetOutputOptionsContainer.argtypes = [handle, number]
    library.nvttSetOutputOptionsContainer.restype = None

    library.nvttCreateSurface.argtypes = []
    library.nvttCreateSurface.restype = handle
    library.nvttDestroySurface.argtypes = [handle]
    library.nvttDestroySurface.restype = None
    library.nvttSurfaceLoad.argtypes = [handle, text, number_out, number, handle]
    library.nvttSurfaceLoad.restype = number
    library.nvttSurfaceCountMipmaps.argtypes = [handle, number]
    library.nvttSurfaceCountMipmaps.restype = number
    library.nvttSurfaceBuildNextMipmapDefaults.argtypes = [handle, number, number, handle]
    library.nvttSurfaceBuildNextMipmapDefaults.restype = number
    library.nvttSurfaceToLinearFromSrgb.argtypes = [handle, handle]
    library.nvttSurfaceToLinearFromSrgb.restype = None
    library.nvttSurfaceToSrgb.argtypes = [handle, handle]
    library.nvttSurfaceToSrgb.restype = None


def _nvtt_directory() -> pathlib.Path:
    """Return the directory holding the NVTT library and its own dependencies."""
    return pathlib.Path(str(carb.tokens.get_tokens_interface().resolve(_NVTT_DIR_TOKEN)))


def _load() -> ctypes.CDLL:
    """Load the NVTT shared library once per process.

    Returns:
        The loaded library.

    Raises:
        NvttUnavailableError: If the library is missing or cannot be loaded.
    """
    global _library, _load_error
    with _lock:
        if _library is not None:
            return _library
        if _load_error is not None:
            raise NvttUnavailableError(_load_error)
        directory = _nvtt_directory()
        candidates = sorted(directory.glob(_LIBRARY_GLOB))
        if not candidates:
            _load_error = f"no {_LIBRARY_GLOB} in {directory}"
            raise NvttUnavailableError(_load_error)
        # Highest version last, so prefer it if a package ever carries two.
        path = candidates[-1]
        try:
            # The library resolves FreeImage.dll and the CUDA runtime from its own directory.
            os.add_dll_directory(str(directory))
            library = ctypes.CDLL(str(path))
            _bind(library)
        except (OSError, AttributeError) as error:
            _load_error = f"cannot load {path}: {error}"
            raise NvttUnavailableError(_load_error) from error
        _library = library
        return library


def is_available() -> bool:
    """Return whether in-process encoding can run."""
    try:
        _load()
    except NvttUnavailableError:
        return False
    return True


def _pin_device(library: ctypes.CDLL) -> None:
    """Make the pinned GPU current on this thread, so NVTT cannot move work to another one.

    ``cudaSetDevice`` is per thread, and NVTT reads the current device once this module has called
    ``nvttUseCurrentDevice``. Retaining the primary context of device 0 and making it current is
    what the CUDA runtime does for ``cudaSetDevice(0)``, and it needs only the driver library that
    ships with every NVIDIA driver.

    A failure here is not fatal: NVTT then picks a device itself, which is the behaviour before
    this pinning existed.
    """
    if _thread_state.device_pinned:
        return
    _thread_state.device_pinned = True
    try:
        driver = ctypes.CDLL("nvcuda.dll")
    except OSError as error:
        carb.log_warn(f"[NvttLibrary] Cannot load the CUDA driver to pin a GPU: {error}")
        return

    device = ctypes.c_int()
    context = ctypes.c_void_p()
    steps = (
        ("cuInit", driver.cuInit, (0,)),
        ("cuDeviceGet", driver.cuDeviceGet, (ctypes.byref(device), _PINNED_DEVICE)),
        ("cuDevicePrimaryCtxRetain", driver.cuDevicePrimaryCtxRetain, (ctypes.byref(context), device)),
        ("cuCtxSetCurrent", driver.cuCtxSetCurrent, (context,)),
    )
    for name, function, arguments in steps:
        result = function(*arguments)
        if result != _CUDA_SUCCESS:
            carb.log_warn(f"[NvttLibrary] {name} returned {result}; NVTT will choose its own GPU")
            return
    library.nvttUseCurrentDevice()


def _cuda_is_supported(library: ctypes.CDLL) -> bool:
    """Return whether NVTT reports CUDA support, asking the library at most once per process.

    Only call this from a thread that has already pinned its device. ``nvtt_lowlevel.h`` documents
    ``nvttIsCudaSupported`` as one of the functions that can choose a device and call
    ``cudaSetDevice``, and this process also runs the renderer.
    """
    global _cuda_supported
    if _cuda_supported is None:
        with _lock:
            if _cuda_supported is None:
                _cuda_supported = bool(library.nvttIsCudaSupported())
    return _cuda_supported


def _context(library: ctypes.CDLL, use_cuda: bool) -> ctypes.c_void_p:
    """Return this thread's encoder context for one acceleration mode, creating it on first use.

    NVTT documents a context as single threaded, so each encoding thread owns its own. Contexts in
    the same process share one CUDA context, which is what makes repeated GPU encodes cheap.
    """
    if use_cuda:
        # Pin first. NVTT can call cudaSetDevice from both the CUDA probe below and a new
        # context, and pinning stops it, so the order here is what keeps work on GPU 0.
        _pin_device(library)
    cuda = use_cuda and _cuda_is_supported(library)
    holder = _thread_state.holder
    context = holder.contexts.get(cuda)
    if context is None:
        context = library.nvttCreateContext()
        library.nvttSetContextCudaAcceleration(context, _TRUE if cuda else _FALSE)
        holder.contexts[cuda] = context
        holder.destroy_context = library.nvttDestroyContext
    return context


def encode_dds(
    source: pathlib.Path,
    destination: pathlib.Path,
    *,
    block_format: BlockFormat,
    gamma_encoded: bool,
    mip_filter: MipmapFilter = MipmapFilter.BOX,
    use_cuda: bool = True,
) -> None:
    """Encode one image file to a mipmapped DDS without leaving this process.

    Reproduces the nvtt_export defaults: a full mipmap chain and ``normal`` quality. A gamma
    encoded surface is converted to linear only for the downsample and converted back before
    each level is written, which is what ``--mip-gamma-correct`` does. The stored values
    themselves stay gamma encoded.

    Args:
        source: Image file to read. NVTT reads it through FreeImage.
        destination: DDS file to write.
        block_format: The block compression format.
        gamma_encoded: Whether the source holds gamma encoded values.
        mip_filter: Filter used to build each mipmap.
        use_cuda: Whether to use the GPU. Pass False to encode on the CPU when GPU memory is
            scarce, for example while another process holds most of it. Ignored when the
            installed driver reports no CUDA support.

    Raises:
        NvttUnavailableError: If the NVTT library cannot be loaded.
        RuntimeError: If NVTT fails to read the source or write the destination.
    """
    library = _load()
    context = _context(library, use_cuda)
    # Built per call. A create and destroy pair costs well under a microsecond against roughly
    # 130 ms for a 1k BC7 encode, so keeping them per thread measured no faster and only made the
    # lifetime harder to follow. The output options have to be per call in any case: they own the
    # open DDS file, and the C API can close it only by destroying them, so a caller that reads or
    # moves the file as soon as this returns needs that handle gone.
    surface = library.nvttCreateSurface()
    compression = library.nvttCreateCompressionOptions()
    output = library.nvttCreateOutputOptions()
    try:
        has_alpha = ctypes.c_int(0)
        if not library.nvttSurfaceLoad(surface, str(source).encode(), ctypes.byref(has_alpha), _FALSE, None):
            raise RuntimeError(f"NVTT cannot read {source}")

        library.nvttSetCompressionOptionsFormat(compression, int(block_format))
        library.nvttSetCompressionOptionsQuality(compression, _QUALITY_NORMAL)
        library.nvttSetOutputOptionsFileName(output, str(destination).encode())
        library.nvttSetOutputOptionsContainer(output, _CONTAINER_DDS10)
        # nvtt_export lets the exporter choose the transfer function, which selects the plain
        # UNORM format rather than its _SRGB variant. Setting the flag here would not match.

        mipmap_count = library.nvttSurfaceCountMipmaps(surface, 1)
        if not library.nvttContextOutputHeader(context, surface, mipmap_count, compression, output):
            raise RuntimeError(f"NVTT cannot write the DDS header for {destination}")

        # Level 0 is written from the values as loaded. Every later level is downsampled in
        # linear space when the surface is gamma encoded, then converted back before writing.
        for level in range(mipmap_count):
            if level > 0:
                if gamma_encoded:
                    library.nvttSurfaceToLinearFromSrgb(surface, None)
                if not library.nvttSurfaceBuildNextMipmapDefaults(surface, int(mip_filter), 1, None):
                    raise RuntimeError(f"NVTT cannot build mipmap {level} for {source}")
                if gamma_encoded:
                    library.nvttSurfaceToSrgb(surface, None)
            if not library.nvttContextCompress(context, surface, 0, level, compression, output):
                raise RuntimeError(f"NVTT cannot compress mip level {level} of {source}")
    finally:
        library.nvttDestroyOutputOptions(output)
        library.nvttDestroyCompressionOptions(compression)
        library.nvttDestroySurface(surface)
