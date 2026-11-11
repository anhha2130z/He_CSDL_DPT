import io
import unittest

import numpy as np
from PIL import Image, ImageDraw

from app import normalize_uploaded_image


class ImageNormalizationTests(unittest.TestCase):
    def test_non_square_upload_is_padded_not_stretched(self):
        source = Image.new("RGB", (400, 200), (255, 0, 0))
        ImageDraw.Draw(source).rectangle((200, 0, 399, 199), fill=(0, 0, 255))
        source_bytes = io.BytesIO()
        source.save(source_bytes, format="PNG")

        normalized = normalize_uploaded_image(source_bytes.getvalue())

        with Image.open(io.BytesIO(normalized)) as image:
            self.assertEqual(image.size, (512, 512))
            pixels = np.asarray(image.convert("RGB"))

        np.testing.assert_allclose(pixels[20, 256], (127, 0, 127), atol=8)
        np.testing.assert_allclose(pixels[256, 128], (255, 0, 0), atol=12)
        np.testing.assert_allclose(pixels[256, 384], (0, 0, 255), atol=12)


if __name__ == "__main__":
    unittest.main()
