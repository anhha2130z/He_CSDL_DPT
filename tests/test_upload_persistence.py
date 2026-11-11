import csv
import json
import os
import pickle
import sqlite3
import tempfile
import unittest

import numpy as np
from sklearn.decomposition import PCA

import app as app_module


class UploadPersistenceTests(unittest.TestCase):
    def test_cosine_similarity_percent_uses_full_cosine_range(self):
        self.assertEqual(app_module.cosine_similarity_percent(-1), 0)
        self.assertEqual(app_module.cosine_similarity_percent(0), 50)
        self.assertEqual(app_module.cosine_similarity_percent(1), 100)
        self.assertEqual(app_module.cosine_similarity_percent(0.6), 80)
        self.assertEqual(app_module.cosine_similarity_percent(2), 100)
        self.assertEqual(app_module.cosine_similarity_percent(-2), 0)

    def test_search_excludes_query_image_for_faiss_and_fallback(self):
        names = ("FAISS_INDEX", "FEATURES_DB", "IMAGE_PATHS")
        previous = {name: getattr(app_module, name) for name in names}

        class FakeIndex:
            def __init__(self, vectors):
                self.vectors = vectors

            def search(self, query, count):
                scores = query @ self.vectors.T
                indices = np.argsort(-scores[0])[:count]
                return scores[:, indices], indices.reshape(1, -1)

        try:
            vectors = np.asarray([
                [1.0, 0.0],
                [0.8, 0.6],
                [0.6, 0.8],
                [0.0, 1.0],
            ], dtype=np.float32)
            app_module.FEATURES_DB = vectors
            app_module.IMAGE_PATHS = [
                "data/uploads/query.jpg",
                "data/example/first.jpg",
                "data/example/second.jpg",
                "data/example/third.jpg",
            ]
            query = np.asarray([[1.0, 0.0]], dtype=np.float32)

            app_module.FAISS_INDEX = FakeIndex(vectors)
            faiss_indices, _ = app_module._search_neighbors(
                query, "data/uploads/query.jpg", top_k=3
            )
            self.assertEqual(faiss_indices, [1, 2, 3])

            app_module.FAISS_INDEX = None
            fallback_indices, _ = app_module._search_neighbors(
                query, "data/uploads/query.jpg", top_k=3
            )
            self.assertEqual(fallback_indices, [1, 2, 3])
        finally:
            for name, value in previous.items():
                setattr(app_module, name, value)

    def test_upload_updates_image_store_features_and_search_index(self):
        if app_module.faiss is None:
            self.skipTest("FAISS is required for this persistence integration test.")

        global_names = (
            "BASE_DIR",
            "DATA_DIR",
            "DB_PATH",
            "FEATURES_PATH",
            "RAW_FEATURES_PATH",
            "PCA_PATH",
            "FAISS_PATH",
            "MANIFEST_PATH",
            "FEATURES_DB",
            "PCA_MODEL",
            "FAISS_INDEX",
            "IMAGE_PATHS",
            "IMAGE_RECORDS",
            "INDEX_MANIFEST",
            "IMAGE_CONTENT_HASHES",
            "IMAGE_FILE_SIGNATURES",
        )
        previous = {name: getattr(app_module, name) for name in global_names}

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                data_dir = os.path.join(temp_dir, "data")
                category_dir = os.path.join(data_dir, "example")
                database_dir = os.path.join(temp_dir, "database")
                os.makedirs(category_dir)
                os.makedirs(database_dir)

                seed_relative = "data/example/seed.jpg"
                with open(os.path.join(category_dir, "seed.jpg"), "wb") as f:
                    f.write(b"seed-image")

                app_module.BASE_DIR = temp_dir
                app_module.DATA_DIR = data_dir
                app_module.DB_PATH = os.path.join(database_dir, "database.db")
                app_module.FEATURES_PATH = os.path.join(database_dir, "features.npy")
                app_module.RAW_FEATURES_PATH = os.path.join(database_dir, "raw_features.npz")
                app_module.PCA_PATH = os.path.join(database_dir, "pca_model.pkl")
                app_module.FAISS_PATH = os.path.join(database_dir, "faiss.index")
                app_module.MANIFEST_PATH = os.path.join(database_dir, "index_manifest.json")

                raw_matrix = np.zeros((1, 1460), dtype=np.float64)
                raw_matrix[0, 0] = 1.0
                pca_matrix = np.asarray([[1.0, 0.0]], dtype=np.float32)
                with open(app_module.FEATURES_PATH, "wb") as f:
                    np.save(f, pca_matrix)
                with open(app_module.PCA_PATH, "wb") as f:
                    pca_model = PCA(n_components=2).fit(
                        np.random.default_rng(42).normal(size=(3, 1460))
                    )
                    pickle.dump(pca_model, f)

                connection = sqlite3.connect(app_module.DB_PATH)
                connection.execute(
                    "CREATE TABLE Images (ImageID INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "ImagePath TEXT NOT NULL UNIQUE)"
                )
                connection.execute("INSERT INTO Images (ImagePath) VALUES (?)", (seed_relative,))
                connection.commit()
                connection.close()

                with open(os.path.join(database_dir, "features.csv"), "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["ImageID", "ImagePath", "Dim_0", "Dim_1"])
                    writer.writerow([1, seed_relative, 1.0, 0.0])

                fingerprint = app_module._dataset_fingerprint()
                with open(app_module.RAW_FEATURES_PATH, "wb") as f:
                    np.savez(
                        f,
                        paths=np.asarray([seed_relative]),
                        features=raw_matrix,
                        fingerprint=fingerprint,
                    )

                index = app_module.faiss.IndexFlatIP(2)
                index.add(pca_matrix.copy())
                app_module.faiss.write_index(index, app_module.FAISS_PATH)

                artifact_paths = {
                    "database.db": app_module.DB_PATH,
                    "features.npy": app_module.FEATURES_PATH,
                    "raw_features.npz": app_module.RAW_FEATURES_PATH,
                    "pca_model.pkl": app_module.PCA_PATH,
                    "features.csv": os.path.join(database_dir, "features.csv"),
                    "faiss.index": app_module.FAISS_PATH,
                }
                manifest = {
                    "schema_version": 2,
                    "extractor_version": app_module.FEATURE_SCHEMA_VERSION,
                    "total_images": 1,
                    "raw_dim": 1460,
                    "pca_dim": 2,
                    "dataset_fingerprint": fingerprint,
                    "artifacts": {
                        name: app_module._sha256_file(path)
                        for name, path in artifact_paths.items()
                    },
                }
                with open(app_module.MANIFEST_PATH, "w", encoding="utf-8") as f:
                    json.dump(manifest, f)

                app_module.load_cbir_resources()
                self.assertEqual(app_module.INDEX_MANIFEST, manifest)

                upload_bytes = b"normalized-upload-image"
                raw_feature = np.zeros(1460, dtype=np.float64)
                raw_feature[1] = 1.0
                pca_vector = np.asarray([[0.0, 1.0]], dtype=np.float32)

                relative_path, added = app_module.persist_uploaded_image(
                    upload_bytes,
                    raw_feature,
                    pca_vector,
                )

                self.assertTrue(added)
                self.assertTrue(os.path.isfile(os.path.join(temp_dir, *relative_path.split("/"))))
                self.assertEqual(len(app_module.IMAGE_RECORDS), 2)
                self.assertEqual(app_module.FEATURES_DB.shape, (2, 2))
                self.assertEqual(app_module.FAISS_INDEX.ntotal, 2)
                self.assertEqual(app_module.INDEX_MANIFEST["total_images"], 2)
                for name, expected_hash in app_module.INDEX_MANIFEST["artifacts"].items():
                    artifact_path = artifact_paths.get(name)
                    if name == "features.csv":
                        artifact_path = os.path.join(database_dir, "features.csv")
                    self.assertIsNotNone(artifact_path)
                    self.assertEqual(app_module._sha256_file(artifact_path), expected_hash)

                with np.load(app_module.RAW_FEATURES_PATH, allow_pickle=False) as checkpoint:
                    self.assertEqual(checkpoint["features"].shape, (2, 1460))
                    self.assertEqual(checkpoint["paths"][-1], relative_path)
                    self.assertEqual(
                        str(checkpoint["fingerprint"].item()),
                        app_module.INDEX_MANIFEST["dataset_fingerprint"],
                    )

                connection = sqlite3.connect(app_module.DB_PATH)
                rows = connection.execute(
                    "SELECT ImageID, ImagePath FROM Images ORDER BY ImageID"
                ).fetchall()
                connection.close()
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[-1][1].replace("\\", "/"), relative_path)

                duplicate_path, duplicate_added = app_module.persist_uploaded_image(
                    upload_bytes,
                    raw_feature,
                    pca_vector,
                )
                self.assertEqual(duplicate_path, relative_path)
                self.assertFalse(duplicate_added)
                self.assertEqual(len(app_module.IMAGE_RECORDS), 2)

                with open(os.path.join(category_dir, "seed.jpg"), "wb") as f:
                    f.write(b"changed-after-index-build")
                with self.assertRaisesRegex(RuntimeError, "Dataset files changed"):
                    app_module.persist_uploaded_image(
                        b"another-upload",
                        raw_feature,
                        pca_vector,
                    )
        finally:
            for name, value in previous.items():
                setattr(app_module, name, value)


if __name__ == "__main__":
    unittest.main()
