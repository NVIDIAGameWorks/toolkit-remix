import omni.kit.test
from omni.flux.asset_importer.core import (
    determine_ideal_types,
    get_texture_sets,
    get_texture_type_from_filename,
    parse_texture_paths,
)
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes


class TestAssetUtils(omni.kit.test.AsyncTestCase):
    def test_parse_texture_paths(self):
        # Dictionary with filepath/filename and expected number of parts. It should split at any _-. character
        # or at capital letters EX: TestString_01.a.rtex.dds = ["Test", "String", "01", "a", "rtex"]
        paths_to_parse = {
            "/path/to/file/T_TestingTexture_albedo.dds": 4,
            "other.dds": 1,
            "C:/path/to/file/ProcessedTexture.a.rtex.dds": 4,
        }

        parsed_paths = parse_texture_paths(list(paths_to_parse.keys()))
        for name, parts in parsed_paths.items():
            self.assertEqual(paths_to_parse[name], len(parts))

    def test_get_texture_type_from_filename(self):
        # Each tag resolves to its own type. Multi-letter tags must not match a shorter tag such as `r`, `n` or `s`.
        test_paths = {
            "/path/to/file/ProcessedTexture.a.rtex.dds": _TextureTypes.DIFFUSE,
            "/path/to/file/ProcessedTexture_metallic.m.rtex.dds": _TextureTypes.METALLIC,
            "/path/to/file/ProcessedTexture_roughness.r.rtex.dds": _TextureTypes.ROUGHNESS,
            "ProcessedTexture.n.rtex.dds": _TextureTypes.NORMAL_OGL,
            "ProcessedTexture.e.rtex.dds": _TextureTypes.EMISSIVE,
            "ProcessedTexture.h.rtex.dds": _TextureTypes.HEIGHT,
            "ProcessedTexture.tr.rtex.dds": _TextureTypes.TRANSMITTANCE,
            "ProcessedTexture.an.rtex.dds": _TextureTypes.ANISOTROPY,
            "ProcessedTexture.md.rtex.dds": _TextureTypes.MEASUREMENT_DISTANCE,
            "ProcessedTexture.ss.rtex.dds": _TextureTypes.SINGLE_SCATTERING,
            "ProcessedTexture.s.rtex.dds": _TextureTypes.SKYBOX,
            "ProcessedTexture.rtex.dds": None,
            "other.dds": None,
        }

        for test_path, expected_type in test_paths.items():
            with self.subTest(test_path=test_path):
                # Arrange
                # Act
                found_type = get_texture_type_from_filename(test_path)

                # Assert
                self.assertEqual(expected_type, found_type)

    def test_get_texture_sets(self):
        # Arrange
        paths = [
            "C:/test_01/T_Test_Diffuse.png",
            "C:/test_01/T_Test_Emissive.png",
            "D:/test_01/T_Test_Diffuse.dds",
            "D:/test_01/T_Test_Emissive.dds",
            "C:/test_02/Texture_OTH_Normal.jpg",
            "C:/test_02/Texture_Metallic.jpg",
            "C:/test_03/subdir/Test.gif",
            "C:/test_04/subdir/metal_01.lxr",
            "C:/test_04/subdir/metal_02.lxr",
            "C:/test_05/T_Metal_DX_Normal.psd",
            "C:/test_05/T_Metal_OGL.psd",
        ]
        expected_groups = {
            "C:/test_01/T_Test_": [
                ("Diffuse", "C:/test_01/T_Test_Diffuse.png"),
                ("Emissive", "C:/test_01/T_Test_Emissive.png"),
            ],
            "D:/test_01/T_Test_": [
                ("Diffuse", "D:/test_01/T_Test_Diffuse.dds"),
                ("Emissive", "D:/test_01/T_Test_Emissive.dds"),
            ],
            "C:/test_02/Texture_": [
                ("OTH", "C:/test_02/Texture_OTH_Normal.jpg"),
                ("Metallic", "C:/test_02/Texture_Metallic.jpg"),
            ],
            "C:/test_03/subdir/Test.gif": [
                ("Other", "C:/test_03/subdir/Test.gif"),
            ],
            "C:/test_04/subdir/": [
                ("metal", "C:/test_04/subdir/metal_01.lxr"),
                ("metal", "C:/test_04/subdir/metal_02.lxr"),
            ],
            "C:/test_05/T_Metal_": [
                ("DX", "C:/test_05/T_Metal_DX_Normal.psd"),
                ("OGL", "C:/test_05/T_Metal_OGL.psd"),
            ],
        }

        # Act
        texture_sets = get_texture_sets(paths)

        # Assert
        self.assertDictEqual(texture_sets, expected_groups)

    def test_determine_ideal_types(self):
        # Dictionary with a filepath with the associated TextureType
        test_paths = {
            "/path/to/file/T_TestingTexture_albedo.png": _TextureTypes.DIFFUSE,
            "/path/to/file/T_TestingTexture_metallic.png": _TextureTypes.METALLIC,
            "/path/to/path/T_TestingTexture_roughness.png": _TextureTypes.ROUGHNESS,
        }

        ideal_types = determine_ideal_types(list(test_paths.keys()))
        for path, texture_type in ideal_types.items():
            self.assertEqual(test_paths[path], texture_type)
