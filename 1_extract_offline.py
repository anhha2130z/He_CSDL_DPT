"""
Offline feature extraction and index generation for the FoodLens CBIR app.

The raw-feature checkpoint stores each vector with its relative image path and
a content fingerprint, so interrupted runs can safely resume without confusing
feature order with SQLite row order.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pickle
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile
from multiprocessing import Pool
from typing import Optional, Tuple

import numpy as np
from sklearn.decomposition import PCA

try:
    import faiss  # type: ignore
except ImportError:
    faiss = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_DATA_DIR = DATA_DIR
OUTPUT_DIR = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(OUTPUT_DIR, "database.db")
FEATURES_PATH = os.path.join(OUTPUT_DIR, "features.npy")
RAW_FEATURES_PATH = os.path.join(OUTPUT_DIR, "raw_features.npz")
CHECKPOINT_PATH = os.path.join(OUTPUT_DIR, ".raw_features.checkpoint.npz")
PCA_PATH = os.path.join(OUTPUT_DIR, "pca_model.pkl")
FAISS_PATH = os.path.join(OUTPUT_DIR, "faiss.index")
CSV_PATH = os.path.join(OUTPUT_DIR, "features.csv")
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "index_manifest.json")
PCA_COMPONENTS = 512
CHECKPOINT_EVERY = 25
RAW_DIM = 1460
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

BASE_DIR = os.path.abspath(BASE_DIR)
DATA_DIR = os.path.abspath(DATA_DIR)

sys.path.insert(0, BASE_DIR)
from feature_extractors import FEATURE_SCHEMA_VERSION, extract_raw_features
EXTRACTOR_VERSION = FEATURE_SCHEMA_VERSION


def _relative_path(path: str) -> str:
    return os.path.relpath(path, BASE_DIR)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_dataset_fingerprint(paths: list[str]) -> str:
    """Hash file contents and paths so a checkpoint cannot outlive its inputs."""
    digest = hashlib.sha256()
    digest.update(f"extractor-version:{EXTRACTOR_VERSION}".encode("ascii"))
    for path in sorted(paths, key=_relative_path):
        relative = _relative_path(path).replace("\\", "/").encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest()


def _extract_worker(path: str) -> Tuple[str, Optional[np.ndarray], Optional[str]]:
    try:
        feat = extract_raw_features(path)
        if feat is None:
            return path, None, "image could not be decoded"
        feat = np.nan_to_num(feat, nan=0.0, posinf=0.0, neginf=0.0)
        if feat.shape != (RAW_DIM,):
            return path, None, f"unexpected feature shape {feat.shape}"
        return path, feat, None
    except Exception as exc:
        return path, None, f"{type(exc).__name__}: {exc}"


def collect_images(folder: str) -> list[str]:
    """Collect supported image paths in a stable order."""
    paths: list[str] = []
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for filename in sorted(files):
            if os.path.splitext(filename)[1].lower() in SUPPORTED_EXT:
                paths.append(os.path.join(root, filename))
    return paths


def load_checkpoint(fingerprint: str) -> dict[str, np.ndarray]:
    checkpoint_path = CHECKPOINT_PATH if os.path.exists(CHECKPOINT_PATH) else RAW_FEATURES_PATH
    if not os.path.exists(checkpoint_path):
        return {}
    try:
        with np.load(checkpoint_path, allow_pickle=False) as checkpoint:
            saved_fingerprint = str(checkpoint["fingerprint"].item())
            paths = checkpoint["paths"].astype(str)
            features = checkpoint["features"]
        if saved_fingerprint != fingerprint:
            print("[INFO] Dataset changed; discarding stale feature checkpoint.")
            return {}
        if features.shape != (len(paths), RAW_DIM) or len(set(paths.tolist())) != len(paths):
            raise ValueError("checkpoint paths and feature matrix are inconsistent")
        if not np.isfinite(features).all():
            raise ValueError("checkpoint contains non-finite feature values")
        return {path: features[i].copy() for i, path in enumerate(paths)}
    except (OSError, EOFError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[WARN] Invalid raw-feature checkpoint; recomputing it: {exc}")
        return {}


def save_checkpoint(features_by_path: dict[str, np.ndarray], fingerprint: str) -> None:
    fd, temp_path = tempfile.mkstemp(prefix=".raw_features.", suffix=".npz", dir=OUTPUT_DIR)
    try:
        with os.fdopen(fd, "wb") as f:
            paths = list(features_by_path)
            matrix = (
                np.stack([features_by_path[path] for path in paths])
                if paths
                else np.empty((0, RAW_DIM), dtype=np.float64)
            )
            np.savez(f, paths=np.asarray(paths), features=matrix, fingerprint=fingerprint)
        os.replace(temp_path, CHECKPOINT_PATH)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _create_temp_path(suffix: str) -> str:
    fd, path = tempfile.mkstemp(prefix=".cbir-build.", suffix=suffix, dir=OUTPUT_DIR)
    os.close(fd)
    return path


def stage_artifacts(
    image_paths: list[str],
    raw_features: np.ndarray,
    features_pca: np.ndarray,
    pca: PCA,
    dataset_fingerprint: str,
) -> dict[str, str]:
    staged = {
        "database.db": _create_temp_path(".db"),
        "features.npy": _create_temp_path(".npy"),
        "raw_features.npz": _create_temp_path(".npz"),
        "pca_model.pkl": _create_temp_path(".pkl"),
        "features.csv": _create_temp_path(".csv"),
    }

    conn = sqlite3.connect(staged["database.db"])
    try:
        conn.execute("""
            CREATE TABLE Images (
                ImageID INTEGER PRIMARY KEY AUTOINCREMENT,
                ImagePath TEXT NOT NULL UNIQUE
            )
        """)
        rel_paths = [_relative_path(path) for path in image_paths]
        conn.executemany(
            "INSERT INTO Images (ImagePath) VALUES (?)",
            [(path,) for path in rel_paths],
        )
        conn.commit()
        rows = conn.execute("SELECT ImageID, ImagePath FROM Images ORDER BY ImageID").fetchall()
    finally:
        conn.close()

    with open(staged["features.npy"], "wb") as f:
        np.save(f, features_pca.astype(np.float32))
    with open(staged["raw_features.npz"], "wb") as f:
        np.savez(
            f,
            paths=np.asarray([_relative_path(path) for path in image_paths]),
            features=raw_features,
            fingerprint=dataset_fingerprint,
        )
    with open(staged["pca_model.pkl"], "wb") as f:
        pickle.dump(pca, f)
    with open(staged["features.csv"], "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ImageID", "ImagePath"] + [f"Dim_{i}" for i in range(features_pca.shape[1])])
        for row, vector in zip(rows, features_pca):
            writer.writerow([row[0], row[1], *vector])

    if faiss is not None:
        staged["faiss.index"] = _create_temp_path(".index")
        index_vectors = features_pca.astype(np.float32).copy()
        faiss.normalize_L2(index_vectors)
        index = faiss.IndexFlatIP(index_vectors.shape[1])
        index.add(index_vectors)
        faiss.write_index(index, staged["faiss.index"])

    return staged


def publish_artifacts(
    staged: dict[str, str],
    count: int,
    pca_dim: int,
    dataset_fingerprint: str,
) -> None:
    final_paths = {
        "database.db": DB_PATH,
        "features.npy": FEATURES_PATH,
        "raw_features.npz": RAW_FEATURES_PATH,
        "pca_model.pkl": PCA_PATH,
        "features.csv": CSV_PATH,
        "faiss.index": FAISS_PATH,
    }
    manifest = {
        "schema_version": 2,
        "extractor_version": EXTRACTOR_VERSION,
        "total_images": count,
        "raw_dim": RAW_DIM,
        "pca_dim": pca_dim,
        "dataset_fingerprint": dataset_fingerprint,
        "artifacts": {
            name: _sha256_file(staged[name])
            for name in staged
        },
    }
    fd, temp_manifest = tempfile.mkstemp(prefix=".index_manifest.", suffix=".json", dir=OUTPUT_DIR)
    backups: dict[str, str] = {}
    replaced: list[str] = []
    preserve_backups = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")

        targets = {**final_paths, "index_manifest.json": MANIFEST_PATH}
        changed_names = list(staged)
        if "faiss.index" not in staged and os.path.exists(FAISS_PATH):
            changed_names.append("faiss.index")
        changed_names.append("index_manifest.json")

        for name in changed_names:
            target = targets[name]
            if os.path.exists(target):
                backup_fd, backup_path = tempfile.mkstemp(
                    prefix=".cbir-backup.", suffix=".bak", dir=OUTPUT_DIR
                )
                os.close(backup_fd)
                shutil.copy2(target, backup_path)
                backups[name] = backup_path

        for name, temp_path in staged.items():
            os.replace(temp_path, final_paths[name])
            replaced.append(name)
        if "faiss.index" not in staged and os.path.exists(FAISS_PATH):
            os.remove(FAISS_PATH)
            replaced.append("faiss.index")

        os.replace(temp_manifest, MANIFEST_PATH)
        replaced.append("index_manifest.json")
    except Exception as exc:
        rollback_error = None
        targets = {**final_paths, "index_manifest.json": MANIFEST_PATH}
        for name in reversed(replaced):
            try:
                if name in backups:
                    os.replace(backups.pop(name), targets[name])
                elif os.path.exists(targets[name]):
                    os.remove(targets[name])
            except OSError as rollback_exc:
                rollback_error = rollback_exc
                break
        if rollback_error is not None:
            preserve_backups = True
            raise RuntimeError(
                "Index publication failed and rollback was incomplete; recovery backups "
                f"were retained in {OUTPUT_DIR}: {rollback_error}"
            ) from exc
        raise
    finally:
        if os.path.exists(temp_manifest):
            os.remove(temp_manifest)
        if not preserve_backups:
            for backup_path in backups.values():
                if os.path.exists(backup_path):
                    os.remove(backup_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="CBIR Offline Extraction & PCA")
    parser.add_argument("--dataset", default=DEFAULT_DATA_DIR, help="Dataset folder inside data/")
    parser.add_argument("--workers", type=int, default=2, help="Parallel feature extraction workers")
    parser.add_argument("--checkpoint", type=int, default=CHECKPOINT_EVERY, help="Checkpoint interval")
    args = parser.parse_args()

    dataset_dir = os.path.abspath(args.dataset)
    if not os.path.isdir(dataset_dir):
        parser.error(f"Dataset folder not found: {dataset_dir}")
    if os.path.commonpath([DATA_DIR, dataset_dir]) != DATA_DIR:
        parser.error(f"Dataset must be inside {DATA_DIR} so the web app can serve its images.")
    if args.workers < 1 or args.checkpoint < 1:
        parser.error("--workers and --checkpoint must be at least 1")

    image_paths = collect_images(dataset_dir)
    if not image_paths:
        parser.error(f"No supported images found in {dataset_dir}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"[INFO] Found {len(image_paths)} images in {dataset_dir}")
    print("[INFO] Fingerprinting dataset for a safe, resumable checkpoint...")
    fingerprint = compute_dataset_fingerprint(image_paths)
    features_by_path = load_checkpoint(fingerprint)
    todo_paths = [path for path in image_paths if _relative_path(path) not in features_by_path]
    print(f"[INFO] Reusing {len(features_by_path)} vectors; extracting {len(todo_paths)} images.")

    staged: dict[str, str] = {}
    try:
        if todo_paths:
            start = time.time()
            if args.workers > 1:
                with Pool(processes=args.workers) as pool:
                    iterator = pool.imap(_extract_worker, todo_paths)
                    for index, (path, vector, error) in enumerate(iterator, 1):
                        if vector is not None:
                            features_by_path[_relative_path(path)] = vector
                        else:
                            print(f"[WARN] Skipping {_relative_path(path)}: {error}")
                        if index % args.checkpoint == 0 or index == len(todo_paths):
                            save_checkpoint(features_by_path, fingerprint)
                            print(f"[INFO] Extraction {index}/{len(todo_paths)}")
            else:
                for index, path in enumerate(todo_paths, 1):
                    _, vector, error = _extract_worker(path)
                    if vector is not None:
                        features_by_path[_relative_path(path)] = vector
                    else:
                        print(f"[WARN] Skipping {_relative_path(path)}: {error}")
                    if index % args.checkpoint == 0 or index == len(todo_paths):
                        save_checkpoint(features_by_path, fingerprint)
                        print(f"[INFO] Extraction {index}/{len(todo_paths)}")
            print(f"[INFO] Feature extraction took {time.time() - start:.1f}s")

        ordered_paths = [path for path in image_paths if _relative_path(path) in features_by_path]
        if len(ordered_paths) < 2:
            raise RuntimeError(f"At least 2 valid images are required; found {len(ordered_paths)}.")

        matrix = np.stack([features_by_path[_relative_path(path)] for path in ordered_paths])
        if not np.isfinite(matrix).all():
            raise RuntimeError("Raw feature matrix contains non-finite values.")

        components = min(PCA_COMPONENTS, matrix.shape[0], matrix.shape[1])
        pca = PCA(n_components=components, random_state=42)
        features_pca = pca.fit_transform(matrix)
        variance_pct = float(np.nan_to_num(pca.explained_variance_ratio_, nan=0.0).sum() * 100)
        print(
            f"[INFO] PCA: {matrix.shape[1]} -> {components} dimensions; "
            f"variance retained {variance_pct:.2f}%"
        )

        staged = stage_artifacts(ordered_paths, matrix, features_pca, pca, fingerprint)
        publish_artifacts(staged, len(ordered_paths), components, fingerprint)
        staged.clear()
        if os.path.exists(CHECKPOINT_PATH):
            os.remove(CHECKPOINT_PATH)
        print(f"[OK] Published aligned database and search index for {len(ordered_paths)} images.")
        if faiss is None:
            print("[WARN] FAISS is unavailable; the app will use its exact cosine fallback.")
    finally:
        for temp_path in staged.values():
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    main()
