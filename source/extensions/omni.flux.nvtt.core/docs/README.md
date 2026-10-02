# NVTT Texture Compression [omni.flux.nvtt.core]

A ctypes binding over the NVTT 3 C wrapper that encodes images to mipmapped DDS textures in-process.
Production validator and pipeline callers use the C binding directly through `encode_dds`.

## Responsibilities

- Load the NVTT 3 shared library from the packman delivered tool directory.
- Encode a single image file to a mipmapped DDS through the NVTT high-level C API.
- Provide the C binding that production validator and pipeline conversions use directly.
- Pin GPU 0 on each encoding thread so NVTT cannot move work to another device.
- Provide one encoder context per thread, all sharing one CUDA context, to keep repeated encodes
  cheap.

## Non-Responsibilities

- Does not choose which block format to use. The caller passes a `BlockFormat` member.
- Does not create or manage worker threads. The caller runs `encode_dds` on whichever thread it
  chooses.

## Architecture

### Library resolution

The NVTT shared library lives in the packman delivered tool directory.
Nothing reads an installed copy, so the application stays self contained. The file name carries the
NVTT version (for example `nvtt30205.dll`), so the loader matches `nvtt3*.dll` instead of a fixed
name. A packman bump then needs no code change.

### Gamma handling

For gamma-encoded output, each mip converts to linear for the downsample and back to sRGB before compression.
OpenEXR, Radiance HDR, and BC6H DDS sources hold linear values. BC6H_UF16 output keeps them, and SDR sources convert
from sRGB before compression. Gamma-encoded output converts linear sources to sRGB. `FreeImage_GetFileTypeU` identifies
the format from the file header, so the file suffix has no effect. The DX10 header of a DDS file identifies a BC6H
source. NVTT has no OpenEXR reader, so the bundled `FreeImage.dll` reads OpenEXR files as exact 32 bit float values.

### GPU pinning

NVTT 2023.4.0 chooses a GPU itself and calls `cudaSetDevice`, which can move work to a device the
caller did not intend. Its own header names both `nvttIsCudaSupported` and a new context as
functions that do this. The module calls `nvttUseCurrentDevice` to stop NVTT choosing, then makes
GPU 0 current on each encoding thread through the CUDA driver library. Device selection is per
thread, so this runs once per encoding thread. `CUDA_VISIBLE_DEVICES` is not usable because it is
process wide and the renderer runs in the same process. A pinning failure logs a warning and
continues.

Order matters. A thread pins its device before the module asks whether CUDA is supported, and
before it builds a context. `is_available` only loads the library and never asks about CUDA, so
checking availability cannot move the GPU of the thread that calls it.

### Context management

One encoder context per thread, because NVTT documents a context as single threaded. All of them
share the one process CUDA context, which is what keeps a batch cheap.
Each worker-thread context is released when its worker thread exits.

The surface and the two option objects are built per encode. Retaining them per thread showed no
throughput benefit and complicates lifetime management, because their cost is negligible beside
the compression itself. The output options could not be retained anyway: they own the open DDS
file, and the C API can close it only by destroying them, so a caller that reads, hashes or moves
the file as soon as `encode_dds` returns needs that handle gone.

`use_cuda=False` exists for a machine whose driver reports no CUDA support. It is not a fallback
for a busy GPU, because the GPU path stays faster even when very little GPU memory is free.

## Usage

```python
from omni.flux.nvtt.core import BlockFormat, MipmapFilter, encode_dds, is_available

if not is_available():
    raise RuntimeError("NVTT library not found")

encode_dds(
    source=pathlib.Path("input.png"),
    destination=pathlib.Path("output.dds"),
    block_format=BlockFormat.BC7,
    gamma_encoded=True,
    mip_filter=MipmapFilter.BOX,
    use_cuda=True,
)
```

## Public API

| Symbol | Description |
|---|---|
| `BlockFormat` | `IntEnum` of supported block compression formats: `BC4` (6), `BC5` (9), `BC6H_UF16` (13, unsigned half float), `BC7` (15). The ordinals are the NVTT ABI. |
| `DxgiFormat` | `IntEnum` of the `DXGI_FORMAT` values in the DDS files this repository writes: `BC4_UNORM` (80), `BC5_UNORM` (83), `BC6H_UF16` (95), `BC6H_SF16` (96), `BC7_UNORM` (98). |
| `MipmapFilter` | `IntEnum` matching `NvttMipmapFilter`: `BOX`, `TRIANGLE`, `KAISER`, `MITCHELL`, `MIN`, `MAX`. |
| `NvttUnavailableError` | Raised when the NVTT shared library cannot be loaded. |
| `convert_to_openexr` | Read an image as float RGBA, edit the pixels in place, and write a float OpenEXR file. Memory holds one float copy. |
| `encode_dds` | Encode one image file to a mipmapped DDS. |
| `is_available` | Return whether the NVTT library can be loaded. |
| `is_dds` | Return whether the file header marks a DDS file. Does not load the NVTT library. |
| `is_linear_image` | Return whether the file header marks an OpenEXR, Radiance HDR, or BC6H DDS image. |
| `is_openexr` | Return whether the file header marks an OpenEXR image. |
| `read_dds_format` | Return the DXGI format of a DDS file with a DX10 header, or None. Does not load the NVTT library. |
| `read_linear_image` | Read an OpenEXR or Radiance HDR image as float RGBA pixels. Return None for other formats. |
| `write_openexr` | Write float RGBA pixels to an OpenEXR file with 32 bit float channels. |
