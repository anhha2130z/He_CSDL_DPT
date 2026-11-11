# -*- coding: utf-8 -*-
"""
FoodLens CBIR — Flask Web Application
Hệ thống tìm kiếm ảnh món ăn dựa trên nội dung thị giác cổ điển (1.460D -> PCA 512D).
Kết hợp Cơ sở dữ liệu lai: SQLite + NumPy Matrix + FAISS IndexFlatIP.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import pickle
import shutil
import sqlite3
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import time
import tempfile
import threading
from typing import Any, Dict, List
from urllib.parse import quote
import warnings

import cv2
try:
    import faiss  # type: ignore
except ImportError:
    faiss = None
import numpy as np
from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from feature_extractors import (
    FEATURE_SCHEMA_VERSION,
    _pad_to_square,
    create_foreground_mask,
    extract_raw_features,
)

# ---------------------------------------------------------------------------
# Flask App Setup
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

# ---------------------------------------------------------------------------
# Database & Model Paths
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(BASE_DIR, "database", "database.db")
FEATURES_PATH = os.path.join(BASE_DIR, "database", "features.npy")
RAW_FEATURES_PATH = os.path.join(BASE_DIR, "database", "raw_features.npz")
PCA_PATH = os.path.join(BASE_DIR, "database", "pca_model.pkl")
FAISS_PATH = os.path.join(BASE_DIR, "database", "faiss.index")
MANIFEST_PATH = os.path.join(BASE_DIR, "database", "index_manifest.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

# ---------------------------------------------------------------------------
# Global In-Memory Resources
# ---------------------------------------------------------------------------
FEATURES_DB: np.ndarray | None = None
PCA_MODEL: Any = None
FAISS_INDEX: Any = None
IMAGE_PATHS: List[str] = []
IMAGE_RECORDS: List[Dict[str, Any]] = []
INDEX_MANIFEST: Dict[str, Any] = {}
IMAGE_CONTENT_HASHES: Dict[str, str] = {}
IMAGE_FILE_SIGNATURES: Dict[str, tuple[int, int, int]] = {}
INDEX_LOCK = threading.RLock()


class IndexRollbackError(RuntimeError):
    pass


# Vietnamese Dish Name Map
DISH_NAME_MAP: Dict[str, str] = {
    "banh_bao_kim_sa": "Bánh Bao Kim Sa",
    "banh_bot_loc": "Bánh Bột Lọc",
    "banh_can": "Bánh Căn",
    "banh_canh": "Bánh Canh",
    "banh_chung": "Bánh Chưng",
    "banh_cuon": "Bánh Cuốn",
    "banh_duc": "Bánh Đúc",
    "banh_gio": "Bánh Giò",
    "banh_khot": "Bánh Khọt",
    "banh_mi": "Bánh Mì",
    "banh_pia": "Bánh Pía",
    "banh_tet": "Bánh Tét",
    "banh_trang_nuong": "Bánh Tráng Nướng",
    "banh_trang_tron": "Bánh Tráng Trộn",
    "banh_xeo": "Bánh Xèo",
    "banh_trung_thu": "Bánh Trung Thu",
    "bap_rang_bo": "Bắp Rang Bơ",
    "bo_bit_tet": "Bò Bít Tết",
    "bo_kho": "Bò Kho",
    "bo_la_lot": "Bò Lá Lốt",
    "bo_luc_lac": "Bò Lúc Lắc",
    "bo_ne": "Bò Né",
    "bo_sot_vang": "Bò Sốt Vang",
    "bun_bo": "Bún Bò Huế",
    "bun_ca": "Bún Cá",
    "bun_cha": "Bún Chả",
    "bun_dau": "Bún Đậu Mắm Tôm",
    "bun_dau_mam_tom": "Bún Đậu Mắm Tôm",
    "bun_mam": "Bún Mắm",
    "bun_moc": "Bún Mọc",
    "bun_oc": "Bún Ốc",
    "bun_nem_nuong": "Bún Nem Nướng",
    "bun_rieu": "Bún Riêu Cua",
    "bun_thang": "Bún Thang",
    "bun_thit_nuong": "Bún Thịt Nướng",
    "ca_kho_to": "Cá Kho Tộ",
    "canh_bi_do": "Canh Bí Đỏ",
    "canh_chua": "Canh Chua Cá",
    "canh_kho_qua": "Canh Khổ Qua Nhồi Thịt",
    "canh_nga_nau_chua": "Canh Ngao Nấu Chua",
    "canh_rau_ngot": "Canh Rau Ngót Thịt Băm",
    "chao_ga": "Cháo Gà",
    "chao_long": "Cháo Lòng",
    "com_chay": "Cơm Cháy Chà Bông",
    "com_chien_duong_chau": "Cơm Chiên Dương Châu",
    "com_ga_hoi_an": "Cơm Gà Hội An",
    "com_lam": "Cơm Lam",
    "com_tam": "Cơm Tấm Sườn Bì Chả",
    "cuon_diep": "Cuốn Diếp",
    "ech_om_chuoi_dau": "Ếch Om Chuối Đậu",
    "goi_cuon": "Gỏi Cuốn Tôm Thịt",
    "goi_ngo_sen": "Gỏi Ngó Sen Tôm Thịt",
    "hu_tieu": "Hủ Tiếu Nam Vang",
    "lau_hai_san": "Lẩu Hải Sản",
    "lau_thai": "Lẩu Thái Chua Cay",
    "mi_quang": "Mì Quảng",
    "mi_van_than": "Mì Vằn Thắn",
    "muc_xao_sa_te": "Mực Xào Sa Tế",
    "nem_chua_ran": "Nem Chua Rán",
    "nem_lui": "Nem Lụi Huế",
    "nem_ran": "Nem Rán / Chả Giò",
    "nom_bo_kho": "Nộm Bò Khô",
    "nom_hoa_chuoi": "Nộm Hoa Chuối",
    "pha_lau": "Phá Lấu Bò",
    "pho_bo": "Phở Bò Hà Nội",
    "pho_cuon": "Phở Cuốn",
    "pho_ga": "Phở Gà",
    "suon_xao_chua_ngot": "Sườn Xào Chua Ngọt",
    "thit_kho_tau": "Thịt Kho Tàu",
    "tom_rang_thit": "Tôm Rang Thịt Ba Chỉ",
    "trung_cut_lon_xao_me": "Trứng Cút Lộn Xào Mê",
    "xoi_xeo": "Xôi Xéo Hà Nội",
    "uploads": "Ảnh tải lên",
}


def format_dish_name(folder_name: str) -> str:
    """Format category folder to readable Vietnamese dish name."""
    clean = folder_name.strip().lower()
    if clean in DISH_NAME_MAP:
        return DISH_NAME_MAP[clean]
    return clean.replace("_", " ").title()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_signature(path: str) -> tuple[int, int, int]:
    stat = os.stat(path)
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _fingerprint_from_hashes(content_hashes: Dict[str, str]) -> str:
    digest = hashlib.sha256()
    digest.update(f"extractor-version:{FEATURE_SCHEMA_VERSION}".encode("ascii"))
    for relative_path in sorted(content_hashes):
        relative = relative_path.encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(content_hashes[relative_path]))
    return digest.hexdigest()


def _validate_indexed_dataset(image_paths: List[str]) -> None:
    for relative_path in image_paths:
        normalized_path = relative_path.replace("\\", "/")
        absolute_path = os.path.join(BASE_DIR, *normalized_path.split("/"))
        try:
            signature = _file_signature(absolute_path)
        except OSError as exc:
            raise RuntimeError(
                "An indexed image is missing or unavailable; rebuild the offline index."
            ) from exc

        if signature != IMAGE_FILE_SIGNATURES.get(normalized_path):
            try:
                content_hash = _sha256_file(absolute_path)
                updated_signature = _file_signature(absolute_path)
            except OSError as exc:
                raise RuntimeError(
                    "An indexed image is missing or unavailable; rebuild the offline index."
                ) from exc
            if signature != updated_signature:
                raise RuntimeError("Dataset files changed; rebuild the offline index before saving uploads.")
            if content_hash != IMAGE_CONTENT_HASHES.get(normalized_path):
                raise RuntimeError("Dataset files changed; rebuild the offline index before saving uploads.")
            IMAGE_FILE_SIGNATURES[normalized_path] = signature

    fingerprint = _fingerprint_from_hashes(IMAGE_CONTENT_HASHES)
    if fingerprint != INDEX_MANIFEST.get("dataset_fingerprint"):
        raise RuntimeError("Dataset files changed; rebuild the offline index before saving uploads.")


def _dataset_fingerprint(image_paths: List[str] | None = None) -> str:
    supported_ext = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    if image_paths is None:
        image_paths = []
        for root, dirs, files in os.walk(DATA_DIR):
            dirs.sort()
            for filename in sorted(files):
                if os.path.splitext(filename)[1].lower() in supported_ext:
                    image_paths.append(os.path.join(root, filename))
        paths = [
            (path, os.path.relpath(path, BASE_DIR).replace("\\", "/"))
            for path in image_paths
        ]
    else:
        paths = [
            (
                os.path.join(BASE_DIR, *path.replace("\\", "/").split("/")),
                path.replace("\\", "/"),
            )
            for path in image_paths
        ]

    paths.sort(key=lambda item: item[1])
    content_hashes = {
        relative_path: _sha256_file(path)
        for path, relative_path in paths
    }
    return _fingerprint_from_hashes(content_hashes)


def _new_temp_path(suffix: str) -> str:
    fd, path = tempfile.mkstemp(prefix=".upload-index.", suffix=suffix, dir=os.path.dirname(DB_PATH))
    os.close(fd)
    return path


def _write_checkpoint(path: str, paths: List[str], raw_features: np.ndarray, fingerprint: str) -> None:
    with open(path, "wb") as f:
        np.savez(
            f,
            paths=np.asarray(paths),
            features=raw_features,
            fingerprint=fingerprint,
        )


def _publish_upload_artifacts(staged: Dict[str, str | None]) -> None:
    """Replace the related files as one recoverable bundle; the manifest is last."""
    targets = {
        "database.db": DB_PATH,
        "features.npy": FEATURES_PATH,
        "features.csv": os.path.join(BASE_DIR, "database", "features.csv"),
        "faiss.index": FAISS_PATH,
        "raw_features.npz": RAW_FEATURES_PATH,
        "index_manifest.json": MANIFEST_PATH,
    }
    backups: Dict[str, str] = {}
    replaced: List[str] = []
    preserve_backups = False
    try:
        for name in staged:
            target = targets[name]
            if os.path.exists(target):
                backup = _new_temp_path(".backup")
                shutil.copy2(target, backup)
                backups[name] = backup

        for name in staged:
            if name == "index_manifest.json":
                continue
            if staged[name] is None:
                if os.path.exists(targets[name]):
                    os.remove(targets[name])
            else:
                os.replace(staged[name], targets[name])
            replaced.append(name)
        manifest_path = staged["index_manifest.json"]
        if manifest_path is None:
            raise RuntimeError("The updated index manifest was not staged.")
        os.replace(manifest_path, targets["index_manifest.json"])
        replaced.append("index_manifest.json")
    except Exception as exc:
        rollback_error = None
        for name in reversed(replaced):
            try:
                backup = backups.get(name)
                if backup is not None:
                    os.replace(backup, targets[name])
                    backups.pop(name, None)
                elif os.path.exists(targets[name]):
                    os.remove(targets[name])
            except OSError as rollback_exc:
                rollback_error = rollback_exc
                break
        if rollback_error is not None:
            preserve_backups = True
            raise IndexRollbackError(
                "Upload index publication failed and rollback was incomplete; "
                "recovery backups were retained next to the index files."
            ) from exc
        raise
    finally:
        cleanup_paths = list(staged.values())
        if not preserve_backups:
            cleanup_paths.extend(backups.values())
        for path in cleanup_paths:
            if path is not None and os.path.exists(path):
                os.remove(path)


def persist_uploaded_image(image_bytes: bytes, raw_feature: np.ndarray, pca_vector: np.ndarray) -> tuple[str, bool]:
    """Persist an upload, its raw/PCA vectors, and all aligned search artifacts."""
    global FEATURES_DB, FAISS_INDEX, IMAGE_PATHS, IMAGE_RECORDS, INDEX_MANIFEST
    global IMAGE_CONTENT_HASHES, IMAGE_FILE_SIGNATURES

    image_hash = hashlib.sha256(image_bytes).hexdigest()
    relative_path = f"data/uploads/{image_hash}.jpg"
    image_path = os.path.join(BASE_DIR, *relative_path.split("/"))
    os.makedirs(os.path.dirname(image_path), exist_ok=True)

    with INDEX_LOCK:
        if INDEX_MANIFEST.get("dataset_fingerprint") is None:
            raise RuntimeError("Index manifest is not loaded; rebuild the offline index.")

        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                disk_manifest = json.load(f)
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                "Search index manifest is unavailable or invalid; rebuild the offline index."
            ) from exc
        if disk_manifest != INDEX_MANIFEST:
            raise RuntimeError("Search index changed on disk; restart the app before saving uploads.")
        _validate_indexed_dataset(IMAGE_PATHS)
        if relative_path in IMAGE_PATHS:
            return relative_path, False

        checkpoint_paths: List[str]
        try:
            with np.load(RAW_FEATURES_PATH, allow_pickle=False) as checkpoint:
                checkpoint_fingerprint = str(checkpoint["fingerprint"].item())
                checkpoint_paths = checkpoint["paths"].astype(str).tolist()
                checkpoint_features = checkpoint["features"].astype(np.float64)
        except (OSError, EOFError, KeyError, ValueError) as exc:
            raise RuntimeError("Raw feature checkpoint is unavailable; rebuild the offline index.") from exc

        if checkpoint_fingerprint != INDEX_MANIFEST.get("dataset_fingerprint"):
            raise RuntimeError("Raw feature checkpoint is stale; rebuild the offline index.")
        if (
            checkpoint_features.shape != (len(checkpoint_paths), 1460)
            or not np.isfinite(checkpoint_features).all()
            or set(path.replace("\\", "/") for path in checkpoint_paths) != set(IMAGE_PATHS)
        ):
            raise RuntimeError("Raw feature checkpoint does not match the image index; rebuild it.")
        if not np.isfinite(raw_feature).all() or raw_feature.shape != (1460,):
            raise ValueError("Invalid raw feature vector for uploaded image.")
        if pca_vector.shape != (1, FEATURES_DB.shape[1]) or not np.isfinite(pca_vector).all():
            raise ValueError("Invalid PCA feature vector for uploaded image.")

        created_image = False
        if not os.path.exists(image_path):
            fd, temp_image = tempfile.mkstemp(prefix=".upload.", suffix=".jpg", dir=os.path.dirname(image_path))
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(image_bytes)
                os.replace(temp_image, image_path)
                created_image = True
            finally:
                if os.path.exists(temp_image):
                    os.remove(temp_image)
        elif _sha256_file(image_path) != image_hash:
            raise RuntimeError("Stored upload does not match its content hash; remove it and retry.")

        staged: Dict[str, str | None] = {}
        artifacts_published = False
        try:
            new_paths = IMAGE_PATHS + [relative_path]
            next_content_hashes = dict(IMAGE_CONTENT_HASHES)
            next_content_hashes[relative_path] = image_hash
            next_fingerprint = _fingerprint_from_hashes(next_content_hashes)
            raw_matrix = np.vstack([checkpoint_features, raw_feature.reshape(1, -1)])
            pca_matrix = np.vstack([FEATURES_DB, pca_vector.astype(np.float32)])
            normalized = pca_matrix.copy()
            if faiss is not None:
                faiss.normalize_L2(normalized)
                index = faiss.IndexFlatIP(normalized.shape[1])
                index.add(normalized)

            staged["database.db"] = _new_temp_path(".db")
            connection = sqlite3.connect(staged["database.db"])
            try:
                connection.execute("""
                    CREATE TABLE Images (
                        ImageID INTEGER PRIMARY KEY AUTOINCREMENT,
                        ImagePath TEXT NOT NULL UNIQUE
                    )
                """)
                connection.executemany(
                    "INSERT INTO Images (ImagePath) VALUES (?)",
                    [(path.replace("/", os.sep),) for path in new_paths],
                )
                connection.commit()
                rows = connection.execute(
                    "SELECT ImageID, ImagePath FROM Images ORDER BY ImageID"
                ).fetchall()
            finally:
                connection.close()

            staged["features.npy"] = _new_temp_path(".npy")
            with open(staged["features.npy"], "wb") as f:
                np.save(f, pca_matrix)

            staged["features.csv"] = _new_temp_path(".csv")
            with open(staged["features.csv"], "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["ImageID", "ImagePath"]
                    + [f"Dim_{i}" for i in range(pca_matrix.shape[1])]
                )
                for row, vector in zip(rows, pca_matrix):
                    writer.writerow([row[0], row[1], *vector])

            if faiss is not None:
                staged["faiss.index"] = _new_temp_path(".index")
                faiss.write_index(index, staged["faiss.index"])
            elif "faiss.index" in INDEX_MANIFEST.get("artifacts", {}):
                staged["faiss.index"] = None

            staged["raw_features.npz"] = _new_temp_path(".npz")
            new_checkpoint_paths = checkpoint_paths + [relative_path]
            _write_checkpoint(
                staged["raw_features.npz"],
                new_checkpoint_paths,
                raw_matrix,
                next_fingerprint,
            )

            next_manifest = dict(INDEX_MANIFEST)
            next_manifest["total_images"] = len(new_paths)
            next_manifest["dataset_fingerprint"] = next_fingerprint
            artifacts = dict(next_manifest["artifacts"])
            for name, path in staged.items():
                if path is None:
                    artifacts.pop(name, None)
                elif name != "index_manifest.json":
                    artifacts[name] = _sha256_file(path)
            next_manifest["artifacts"] = artifacts
            staged["index_manifest.json"] = _new_temp_path(".json")
            with open(staged["index_manifest.json"], "w", encoding="utf-8") as f:
                json.dump(next_manifest, f, ensure_ascii=False, indent=2)
                f.write("\n")

            image_signature = _file_signature(image_path)
            _publish_upload_artifacts(staged)
            artifacts_published = True
            staged.clear()

            new_record = {
                "image_id": rows[-1][0],
                "path": relative_path,
                "category": "uploads",
                "dish_name": format_dish_name("uploads"),
                "url": "/data/uploads/" + image_hash + ".jpg",
            }
            FEATURES_DB = pca_matrix
            FAISS_INDEX = index if faiss is not None else None
            IMAGE_PATHS = new_paths
            IMAGE_RECORDS = IMAGE_RECORDS + [new_record]
            INDEX_MANIFEST = next_manifest
            IMAGE_CONTENT_HASHES = next_content_hashes
            IMAGE_FILE_SIGNATURES = {
                **IMAGE_FILE_SIGNATURES,
                relative_path: image_signature,
            }
            return relative_path, True
        except Exception as exc:
            for path in staged.values():
                if path is not None and os.path.exists(path):
                    os.remove(path)
            if (
                created_image
                and not artifacts_published
                and not isinstance(exc, IndexRollbackError)
                and os.path.exists(image_path)
            ):
                os.remove(image_path)
            raise


def load_cbir_resources():
    """Load all necessary CBIR artifacts into memory on server startup."""
    global FEATURES_DB, PCA_MODEL, FAISS_INDEX, IMAGE_PATHS, IMAGE_RECORDS, INDEX_MANIFEST
    global IMAGE_CONTENT_HASHES, IMAGE_FILE_SIGNATURES

    if not os.path.exists(MANIFEST_PATH):
        raise RuntimeError(
            "Search-index manifest is missing or outdated. Run "
            "'python 1_extract_offline.py' to rebuild aligned artifacts."
        )

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    if manifest.get("schema_version") != 2:
        raise RuntimeError("Unsupported search-index manifest; rebuild the offline index.")
    if manifest.get("extractor_version") != FEATURE_SCHEMA_VERSION:
        raise RuntimeError("Feature schema changed; rebuild the offline index.")

    artifact_paths = {
        "database.db": DB_PATH,
        "features.npy": FEATURES_PATH,
        "raw_features.npz": RAW_FEATURES_PATH,
        "pca_model.pkl": PCA_PATH,
        "features.csv": os.path.join(BASE_DIR, "database", "features.csv"),
        "faiss.index": FAISS_PATH,
    }
    recorded_artifacts = manifest.get("artifacts")
    if not isinstance(recorded_artifacts, dict):
        raise RuntimeError("Search-index manifest has no artifact checksums; rebuild the index.")
    for name in ("database.db", "features.npy", "raw_features.npz", "pca_model.pkl", "features.csv"):
        expected_hash = recorded_artifacts.get(name)
        path = artifact_paths[name]
        if not isinstance(expected_hash, str) or not os.path.isfile(path):
            raise RuntimeError(f"Search artifact {name} is missing; rebuild the offline index.")
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise RuntimeError(f"Search artifact {name} does not match the manifest; rebuild the index.")

    print(">>> Loading CBIR Resources into RAM...")
    features_db = np.load(FEATURES_PATH).astype(np.float32)

    with open(PCA_PATH, "rb") as f:
        pca_model = pickle.load(f)

    count = manifest.get("total_images")
    pca_dim = manifest.get("pca_dim")
    if (
        not isinstance(count, int)
        or not isinstance(pca_dim, int)
        or features_db.shape != (count, pca_dim)
        or not np.isfinite(features_db).all()
        or getattr(pca_model, "n_features_in_", None) != manifest.get("raw_dim")
        or getattr(pca_model, "n_components_", None) != pca_dim
    ):
        raise RuntimeError("Feature matrix and PCA model dimensions do not match the manifest.")

    faiss_hash = recorded_artifacts.get("faiss.index")
    if faiss_hash is not None:
        if not os.path.isfile(FAISS_PATH):
            raise RuntimeError("FAISS index is missing; rebuild the offline index.")
        digest = hashlib.sha256()
        with open(FAISS_PATH, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != faiss_hash:
            raise RuntimeError("FAISS index does not match the manifest; rebuild the offline index.")
        if faiss is None:
            faiss_index = None
            print("  [WARN] FAISS is unavailable; using exact SciPy cosine fallback.")
        else:
            faiss_index = faiss.read_index(FAISS_PATH)
            if faiss_index.ntotal != count or faiss_index.d != pca_dim:
                raise RuntimeError("FAISS index dimensions do not match the feature matrix.")
            print(f"  [OK] FAISS Index loaded ({faiss_index.ntotal} vectors)")
    else:
        if os.path.exists(FAISS_PATH):
            raise RuntimeError("Untracked FAISS index found; rebuild the offline index.")
        faiss_index = None
        print("  [WARN] FAISS index file not found, will use SciPy fallback.")

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT ImageID, ImagePath FROM Images ORDER BY ImageID").fetchall()
    finally:
        conn.close()
    if len(rows) != count:
        raise RuntimeError("SQLite row count does not match the feature matrix.")

    image_paths: List[str] = []
    image_records: List[Dict[str, Any]] = []
    image_content_hashes: Dict[str, str] = {}
    image_file_signatures: Dict[str, tuple[int, int, int]] = {}
    for image_id, raw_path in rows:
        normalized_path = str(raw_path).replace("\\", "/")
        parts = normalized_path.split("/")
        if len(parts) < 2 or parts[0] != "data" or any(part in ("", ".", "..") for part in parts):
            raise RuntimeError(f"Invalid dataset path in SQLite: {raw_path!r}")
        absolute_path = os.path.realpath(os.path.join(BASE_DIR, *parts))
        if os.path.commonpath([os.path.realpath(DATA_DIR), absolute_path]) != os.path.realpath(DATA_DIR):
            raise RuntimeError(f"Dataset path escapes the data directory: {raw_path!r}")
        if not os.path.isfile(absolute_path):
            raise RuntimeError(f"Dataset image is missing: {raw_path!r}")

        image_paths.append(normalized_path)
        signature_before = _file_signature(absolute_path)
        image_content_hashes[normalized_path] = _sha256_file(absolute_path)
        signature_after = _file_signature(absolute_path)
        if signature_before != signature_after:
            raise RuntimeError("Dataset files changed while the search index was loading.")
        image_file_signatures[normalized_path] = signature_after
        category_slug = parts[-2] if len(parts) >= 3 else "mon_an"
        dish_name = format_dish_name(category_slug)

        image_records.append({
            "image_id": image_id,
            "path": normalized_path,
            "category": category_slug,
            "dish_name": dish_name,
            "url": "/data/" + quote("/".join(parts[1:]), safe="/"),
        })

    FEATURES_DB = features_db
    PCA_MODEL = pca_model
    FAISS_INDEX = faiss_index
    IMAGE_PATHS = image_paths
    IMAGE_RECORDS = image_records
    INDEX_MANIFEST = manifest
    IMAGE_CONTENT_HASHES = image_content_hashes
    IMAGE_FILE_SIGNATURES = image_file_signatures
    print(f"  [OK] Database loaded {len(IMAGE_RECORDS)} food images.")
    print(f"  [OK] Memory Feature Matrix shape: {FEATURES_DB.shape}")


def get_dominant_colors(bgr: np.ndarray, mask: np.ndarray, n_colors: int = 5) -> list[dict]:
    """Extract top dominant colors in foreground with K-Means."""
    fg_pixels = bgr[mask > 0]
    if len(fg_pixels) < n_colors * 10:
        fg_pixels = bgr.reshape(-1, 3)

    fg_rgb = cv2.cvtColor(fg_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2RGB).reshape(-1, 3)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(
        fg_rgb.astype(np.float32), n_colors, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    counts = np.bincount(labels.flatten())
    total = len(labels) if len(labels) > 0 else 1

    colors = []
    for c, cnt in sorted(zip(centers, counts), key=lambda x: x[1], reverse=True):
        r, g, b = [int(np.clip(v, 0, 255)) for v in c]
        hex_code = f"#{r:02x}{g:02x}{b:02x}"
        pct = round((cnt / total) * 100, 1)
        colors.append({"hex": hex_code, "rgb": [r, g, b], "percent": pct})
    return colors


def _search_neighbors(
    query: np.ndarray,
    excluded_path: str,
    top_k: int = 5,
) -> tuple[list[int], list[float]]:
    """Return the nearest indexed images, excluding the query image itself."""
    candidate_count = min(len(IMAGE_PATHS), top_k + 1)
    if FAISS_INDEX is not None:
        scores, indices = FAISS_INDEX.search(query, candidate_count)
        neighbors = [
            (int(index), float(score))
            for index, score in zip(indices[0], scores[0])
            if 0 <= index < len(IMAGE_PATHS) and IMAGE_PATHS[index] != excluded_path
        ][:top_k]
    else:
        from scipy.spatial.distance import cdist

        distances = cdist(query, FEATURES_DB, metric="cosine").flatten()
        distances = np.nan_to_num(distances, nan=1.0, posinf=1.0, neginf=1.0)
        ranked_indices = np.argsort(distances)
        neighbors = [
            (int(index), float(1.0 - distances[index]))
            for index in ranked_indices
            if IMAGE_PATHS[index] != excluded_path
        ][:top_k]
    return [index for index, _ in neighbors], [score for _, score in neighbors]


def cosine_similarity_percent(score: float) -> float:
    """Map cosine similarity from [-1, 1] to a display scale from 0 to 100."""
    bounded_score = max(-1.0, min(float(score), 1.0))
    return round((bounded_score + 1.0) * 50.0, 1)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Render main web application interface."""
    return render_template("index.html")


@app.route("/data/<path:filename>")
def serve_data_image(filename):
    """Serve dataset images directly to the browser."""
    return send_from_directory(DATA_DIR, filename)


def normalize_uploaded_image(image_bytes: bytes) -> bytes:
    """Pad an uploaded image to square, then resize it to a 512x512 JPEG."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Ảnh vượt quá giới hạn kích thước xử lý.")
            image = ImageOps.exif_transpose(image).convert("RGB")
            rgb = np.asarray(image)
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            square = _pad_to_square(bgr)
            interpolation = cv2.INTER_AREA if square.shape[0] > 512 else cv2.INTER_CUBIC
            resized = cv2.resize(square, (512, 512), interpolation=interpolation)
            image = Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


@app.errorhandler(RequestEntityTooLarge)
def handle_upload_too_large(_error):
    return jsonify({"success": False, "error": "Ảnh tải lên vượt quá giới hạn 10 MB."}), 413


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Get system database statistics."""
    total = len(IMAGE_RECORDS)
    categories = len({rec["category"] for rec in IMAGE_RECORDS})
    return jsonify({
        "success": True,
        "total_images": total,
        "total_categories": categories,
        "raw_dim": 1460,
        "pca_dim": int(FEATURES_DB.shape[1]) if FEATURES_DB is not None else 0,
        "faiss_ready": FAISS_INDEX is not None,
    })


@app.route("/api/search", methods=["POST"])
def search_image():
    """CBIR Search Endpoint: Query image -> Top-5 Similar Dishes (Optimized ultra-fast)."""
    t0 = time.perf_counter()

    if "query_image" not in request.files:
        return jsonify({"success": False, "error": "Chưa tải lên tệp ảnh món ăn."}), 400

    file = request.files["query_image"]
    if file.filename == "":
        return jsonify({"success": False, "error": "Tên tệp không hợp lệ."}), 400

    # Luôn cố định Top 5 ảnh theo yêu cầu
    if FEATURES_DB is None or PCA_MODEL is None or not IMAGE_RECORDS:
        return jsonify({
            "success": False,
            "error": "Cơ sở dữ liệu tìm kiếm chưa sẵn sàng. Hãy rebuild và nạp lại index.",
        }), 503
    try:
        # Normalize every accepted upload before processing it.
        try:
            img_bytes = normalize_uploaded_image(file.read())
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            return jsonify({
                "success": False,
                "error": "Không thể đọc ảnh tải lên. Vui lòng chọn tệp ảnh hợp lệ.",
            }), 400

        nparr = np.frombuffer(img_bytes, np.uint8)
        bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if bgr is None:
            return jsonify({"success": False, "error": "Không thể giải mã ảnh đã chuẩn hóa."}), 400

        preview_bgr = bgr

        # Resize directly to 224x224 for standard feature extraction
        img_224 = cv2.resize(bgr, (224, 224), interpolation=cv2.INTER_LINEAR)

        # 1. Compute one foreground mask at the feature-extraction resolution.
        try:
            mask_224 = create_foreground_mask(img_224)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 422

        # Encode binary mask as Base64 for intermediate inspection
        _, mask_png = cv2.imencode(".png", mask_224)
        mask_base64 = "data:image/png;base64," + base64.b64encode(mask_png.tobytes()).decode("utf-8")

        # Encode query preview as Base64
        _, bgr_png = cv2.imencode(".jpg", preview_bgr)
        query_base64 = "data:image/jpeg;base64," + base64.b64encode(bgr_png.tobytes()).decode("utf-8")

        # Extract dominant colors from the selected foreground.
        dominant_colors = get_dominant_colors(img_224, mask_224, n_colors=5)

        # 2. Extract 1460D raw features directly in RAM passing precomputed mask
        raw_feat = extract_raw_features(img_224, precomputed_mask=mask_224)
        if raw_feat is None:
            return jsonify({"success": False, "error": "Không thể trích xuất đặc trưng từ ảnh này."}), 500

        raw_feat = np.nan_to_num(raw_feat, nan=0.0, posinf=0.0, neginf=0.0)

        # 3. L2-Normalize -> PCA -> L2-Normalize
        norm_val = np.linalg.norm(raw_feat)
        if norm_val > 0:
            v_norm = raw_feat / norm_val
        else:
            v_norm = raw_feat

        pca_vector = PCA_MODEL.transform(v_norm.reshape(1, -1)).astype(np.float32)
        try:
            saved_path, image_added = persist_uploaded_image(
                img_bytes,
                raw_feat,
                pca_vector,
            )
        except RuntimeError as exc:
            return jsonify({
                "success": False,
                "error": f"Không thể lưu ảnh vào chỉ mục: {exc}",
            }), 503
        q_pca = pca_vector.copy()
        if faiss is not None:
            faiss.normalize_L2(q_pca)
        else:
            query_norm = np.linalg.norm(q_pca)
            if query_norm > 0:
                q_pca /= query_norm

        # 4. Search in FAISS IndexFlatIP (or Cosine)
        with INDEX_LOCK:
            indices, scores = _search_neighbors(q_pca, saved_path)
            records_snapshot = IMAGE_RECORDS

        # 5. Format Top-5 Results
        results = []
        for rank, (idx, score) in enumerate(zip(indices, scores), 1):
            if idx < 0 or idx >= len(records_snapshot):
                continue

            rec = records_snapshot[idx]
            bounded_score = max(-1.0, min(float(score), 1.0))
            cosine_score = round(bounded_score, 4)
            cosine_dist = round(max(0.0, 1.0 - bounded_score), 4)

            results.append({
                "rank": rank,
                "dish_name": rec["dish_name"],
                "category": rec["category"],
                "image_url": rec["url"],
                "relative_path": rec["path"],
                "cosine_score": cosine_score,
                "cosine_dist": cosine_dist,
                "similarity_pct": cosine_similarity_percent(bounded_score),
            })

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        # Vector metrics for intermediate illustration
        feature_breakdown = {
            "color_dim": 210,
            "texture_dim": 179,
            "shape_dim": 527,
            "spatial_dim": 544,
            "total_raw_dim": 1460,
            "pca_dim": int(PCA_MODEL.n_components_),
            "pca_variance_pct": round(
                float(np.nan_to_num(PCA_MODEL.explained_variance_ratio_, nan=0.0).sum() * 100),
                2,
            ),
            "mean": round(float(np.mean(q_pca)), 5),
            "std": round(float(np.std(q_pca)), 5),
            "max": round(float(np.max(q_pca)), 5),
            "min": round(float(np.min(q_pca)), 5),
            "sample_vector": [round(float(x), 4) for x in q_pca[0][:16]],
        }

        return jsonify({
            "success": True,
            "elapsed_ms": elapsed_ms,
            "query_image_base64": query_base64,
            "query_mask_base64": mask_base64,
            "saved_image_path": saved_path,
            "image_added_to_index": image_added,
            "total_images": len(IMAGE_RECORDS),
            "dominant_colors": dominant_colors,
            "feature_breakdown": feature_breakdown,
            "results": results,
        })

    except Exception:
        app.logger.exception("Unhandled image-search error")
        return jsonify({
            "success": False,
            "error": "Đã xảy ra lỗi khi xử lý ảnh. Vui lòng thử lại.",
        }), 500


# ---------------------------------------------------------------------------
# Server Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        load_cbir_resources()
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as exc:
        print(f"[ERROR] Unable to load the CBIR index: {exc}")
        raise SystemExit(1) from exc
    print("=" * 60)
    print("   FoodLens CBIR -- Flask Web Server Ready!")
    print("   Truy cap Web Demo tai: http://localhost:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False)
