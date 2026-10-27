"""Tests for image resizing based on filesize."""

import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from beets.test import _common
from beets.test.fixtures import DummyIMBackend
from beets.test.helper import BeetsTestCase, CleanupModulesMixin
from beets.util import command_output
from beets.util.artresizer import ArtResizer, IMBackend, PILBackend


@pytest.mark.requires_import("PIL")
class TestArtworkConversion:
    @pytest.fixture
    def resizer(self, monkeypatch, tmp_path):
        from beets.util import artresizer

        monkeypatch.setattr(artresizer, "BACKEND_CLASSES", [PILBackend])
        monkeypatch.setattr(
            artresizer.util, "get_module_tempdir", lambda _: tmp_path / "output"
        )
        return ArtResizer()

    @pytest.mark.parametrize("mode", ["RGB", "RGBA", "LA", "P"])
    def test_png_to_jpeg(self, tmp_path, resizer, mode):
        from PIL import Image

        source = tmp_path / "cover.png"
        im = Image.new(mode, (16, 16))
        if mode == "P":
            im.info["transparency"] = 0
        im.save(source)
        original = source.read_bytes()
        sibling = tmp_path / "cover.jpg"
        sibling.write_bytes(b"existing artwork")

        result = resizer.reformat(os.fsencode(source), "JPEG")

        with Image.open(result) as converted:
            assert converted.format == "JPEG"
            assert converted.mode == "RGB"
            if mode != "RGB":
                assert converted.getpixel((0, 0)) == (255, 255, 255)
        assert source.read_bytes() == original
        assert sibling.read_bytes() == b"existing artwork"

    @pytest.mark.parametrize("raises", [False, True])
    def test_failed_conversion_preserves_files(
        self, tmp_path, resizer, monkeypatch, raises
    ):
        source = tmp_path / "cover.jpg"
        source.write_bytes(b"original artwork")
        targets = []

        def fail(source, target, deinterlaced):
            targets.append(Path(os.fsdecode(target)))
            targets[-1].write_bytes(b"partial conversion")
            if raises:
                raise OSError("conversion failed")
            return source

        monkeypatch.setattr(resizer.local_method, "convert_format", fail)
        if raises:
            with pytest.raises(OSError, match="conversion failed"):
                resizer.reformat(os.fsencode(source), "jpeg")
        else:
            assert resizer.reformat(os.fsencode(source), "jpeg") == os.fsencode(
                source
            )

        assert source.read_bytes() == b"original artwork"
        assert not targets[0].exists()


class TestImageMagickConversion:
    @pytest.mark.parametrize("extension", ["jpg", "JPEG", "png"])
    def test_alpha_options(self, extension):
        backend = DummyIMBackend()
        target = f"target.{extension}".encode()
        with patch("beets.util.artresizer.subprocess.check_call") as command:
            assert backend.convert_format(b"source.png", target, True) == target

        args = command.call_args.args[0]
        assert ("-alpha" in args) == (extension != "png")
        if extension != "png":
            start = args.index("-background")
            assert args[start : start + 6] == [
                "-background",
                "white",
                "-alpha",
                "remove",
                "-alpha",
                "off",
            ]

    @pytest.mark.parametrize(
        "error",
        [
            OSError("missing executable"),
            subprocess.CalledProcessError(1, "magick"),
        ],
    )
    def test_conversion_failure(self, error):
        with patch(
            "beets.util.artresizer.subprocess.check_call", side_effect=error
        ):
            assert (
                DummyIMBackend().convert_format(
                    b"source.png", b"target.jpg", True
                )
                == b"source.png"
            )


class ArtResizerFileSizeTest(CleanupModulesMixin, BeetsTestCase):
    """Unittest test case for Art Resizer to a specific filesize."""

    modules = (IMBackend.__module__,)

    IMG_225x225 = _common.RSRC / "abbey.jpg"

    def _test_img_resize(self, backend):
        """Test resizing based on file size, given a resize_func."""
        # Check quality setting unaffected by new parameter
        im_95_qual = backend.resize(
            225, self.IMG_225x225, quality=95, max_filesize=0
        )
        # check valid path returned - max_filesize hasn't broken resize command
        assert Path(os.fsdecode(im_95_qual)).exists()

        # Attempt a lower filesize with same quality
        im_a = backend.resize(
            225,
            self.IMG_225x225,
            quality=95,
            max_filesize=0.9 * os.stat(im_95_qual).st_size,
        )
        assert Path(os.fsdecode(im_a)).exists()
        # target size was achieved
        assert os.stat(im_a).st_size < os.stat(im_95_qual).st_size

        # Attempt with lower initial quality
        im_75_qual = backend.resize(
            225, self.IMG_225x225, quality=75, max_filesize=0
        )
        assert Path(os.fsdecode(im_75_qual)).exists()

        im_b = backend.resize(
            225,
            self.IMG_225x225,
            quality=95,
            max_filesize=0.9 * os.stat(im_75_qual).st_size,
        )
        assert Path(os.fsdecode(im_b)).exists()
        # Check high (initial) quality still gives a smaller filesize
        assert os.stat(im_b).st_size < os.stat(im_75_qual).st_size

    @unittest.skipUnless(PILBackend.available(), "PIL not available")
    def test_pil_file_resize(self):
        """Test PIL resize function is lowering file size."""
        self._test_img_resize(PILBackend())

    @unittest.skipUnless(IMBackend.available(), "ImageMagick not available")
    def test_im_file_resize(self):
        """Test IM resize function is lowering file size."""
        self._test_img_resize(IMBackend())

    @unittest.skipUnless(PILBackend.available(), "PIL not available")
    def test_pil_file_deinterlace(self):
        """Test PIL deinterlace function.

        Check if the `PILBackend.deinterlace()` function returns images
        that are non-progressive
        """
        path = PILBackend().deinterlace(self.IMG_225x225)
        from PIL import Image

        with Image.open(path) as img:
            assert "progression" not in img.info

    @unittest.skipUnless(IMBackend.available(), "ImageMagick not available")
    def test_im_file_deinterlace(self):
        """Test ImageMagick deinterlace function.

        Check if the `IMBackend.deinterlace()` function returns images
        that are non-progressive.
        """
        im = IMBackend()
        path = im.deinterlace(self.IMG_225x225)
        cmd = [*im.identify_cmd, "-format", "%[interlace]", os.fsdecode(path)]
        out = command_output(cmd).stdout
        assert out == b"None"

    @patch("beets.util.artresizer.util")
    def test_write_metadata_im(self, mock_util):
        """Test writing image metadata."""
        metadata = {"a": "A", "b": "B"}
        im = DummyIMBackend()
        im.write_metadata("foo", metadata)
        command = [*im.convert_cmd, *"foo -set a A -set b B foo".split()]
        mock_util.command_output.assert_called_once_with(command)
