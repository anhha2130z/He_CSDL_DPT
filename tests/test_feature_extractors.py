import unittest

import numpy as np

from feature_extractors import _pad_to_square, create_foreground_mask, extract_raw_features


class FeatureExtractorTests(unittest.TestCase):
    def test_padding_preserves_image_aspect_ratio_and_centers_content(self):
        image = np.zeros((20, 40, 3), dtype=np.uint8)
        image[:, :20] = (0, 0, 255)
        image[:, 20:] = (255, 0, 0)

        padded = _pad_to_square(image)

        self.assertEqual(padded.shape, (40, 40, 3))
        np.testing.assert_array_equal(padded[0, 20], (127, 0, 127))
        np.testing.assert_array_equal(padded[10, 5], (0, 0, 255))
        np.testing.assert_array_equal(padded[10, 35], (255, 0, 0))

    def test_features_ignore_pixels_outside_precomputed_mask(self):
        rng = np.random.default_rng(42)
        first = rng.integers(0, 256, size=(224, 224, 3), dtype=np.uint8)
        second = rng.integers(0, 256, size=(224, 224, 3), dtype=np.uint8)
        mask = np.zeros((224, 224), dtype=np.uint8)
        mask[48:176, 48:176] = 255
        second[mask > 0] = first[mask > 0]

        first_features = extract_raw_features(first, precomputed_mask=mask)
        second_features = extract_raw_features(second, precomputed_mask=mask)

        self.assertIsNotNone(first_features)
        self.assertIsNotNone(second_features)
        np.testing.assert_allclose(first_features, second_features, rtol=0, atol=1e-12)

    def test_empty_fallback_mask_is_reported(self):
        blank = np.zeros((224, 224, 3), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "empty mask"):
            create_foreground_mask(blank)


if __name__ == "__main__":
    unittest.main()
