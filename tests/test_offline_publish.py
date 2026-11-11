import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


offline = importlib.import_module("1_extract_offline")


class OfflinePublishTests(unittest.TestCase):
    def test_failed_publish_restores_previous_artifacts_and_manifest(self):
        names = (
            "OUTPUT_DIR",
            "DB_PATH",
            "FEATURES_PATH",
            "RAW_FEATURES_PATH",
            "PCA_PATH",
            "FAISS_PATH",
            "CSV_PATH",
            "MANIFEST_PATH",
        )
        previous = {name: getattr(offline, name) for name in names}

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = os.path.join(temp_dir, "database")
                os.makedirs(output_dir)
                targets = {
                    "database.db": os.path.join(output_dir, "database.db"),
                    "features.npy": os.path.join(output_dir, "features.npy"),
                    "raw_features.npz": os.path.join(output_dir, "raw_features.npz"),
                    "pca_model.pkl": os.path.join(output_dir, "pca_model.pkl"),
                    "features.csv": os.path.join(output_dir, "features.csv"),
                    "faiss.index": os.path.join(output_dir, "faiss.index"),
                    "index_manifest.json": os.path.join(output_dir, "index_manifest.json"),
                }
                for name, path in targets.items():
                    with open(path, "wb") as file:
                        file.write(f"old-{name}".encode())
                original_contents = {}
                for name, path in targets.items():
                    with open(path, "rb") as file:
                        original_contents[name] = file.read()

                offline.OUTPUT_DIR = output_dir
                offline.DB_PATH = targets["database.db"]
                offline.FEATURES_PATH = targets["features.npy"]
                offline.RAW_FEATURES_PATH = targets["raw_features.npz"]
                offline.PCA_PATH = targets["pca_model.pkl"]
                offline.FAISS_PATH = targets["faiss.index"]
                offline.CSV_PATH = targets["features.csv"]
                offline.MANIFEST_PATH = targets["index_manifest.json"]

                staged = {}
                for name in targets:
                    if name == "index_manifest.json":
                        continue
                    path = os.path.join(temp_dir, f"staged-{name}")
                    with open(path, "wb") as file:
                        file.write(f"new-{name}".encode())
                    staged[name] = path

                real_replace = os.replace
                failed = False

                def fail_once(source, destination):
                    nonlocal failed
                    if destination == targets["features.npy"] and not failed:
                        failed = True
                        raise OSError("simulated publish failure")
                    return real_replace(source, destination)

                with patch.object(offline.os, "replace", side_effect=fail_once):
                    with self.assertRaisesRegex(OSError, "simulated publish failure"):
                        offline.publish_artifacts(staged, 1, 1, "fingerprint")

                for name, path in targets.items():
                    with open(path, "rb") as file:
                        self.assertEqual(file.read(), original_contents[name])
        finally:
            for name, value in previous.items():
                setattr(offline, name, value)


if __name__ == "__main__":
    unittest.main()
