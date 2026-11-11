"""
feature_extractors.py
=====================
Module trích xuất đặc trưng CBIR cổ điển cho ảnh món ăn.

Sử dụng hoàn toàn Computer Vision cổ điển (KHÔNG Deep Learning):
  - Color  : HSV / CIE-Lab histograms + Color Moments
  - Texture: LBP, EOH, GLCM (Haralick), Gabor bank, Stripe-FFT
  - Shape  : Hu Moments, scalar props, Grid Mask, Width / Contour Profile,
             Radius Signature, HOG (64x64 crop, 324-dim)
  - Spatial: 4x4 grid local HSV histogram + LBP

Tổng vector raw = 1 460 chiều  ->  L2-normalized.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import numpy as np
from scipy import stats as sp_stats
from scipy.fft import fft2, fftshift
from skimage.feature import hog, local_binary_pattern
from skimage.filters import gabor_kernel

LOGGER = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------
IMG_SIZE = 224
FEATURE_SCHEMA_VERSION = 5

# -- Color --
HIST_BINS = 32

# -- LBP --
LBP_RADIUS = 1
LBP_N_POINTS = 8
LBP_BINS = LBP_N_POINTS + 2          # uniform -> 10

# -- EOH --
EOH_BINS = 9

# -- GLCM --
GLCM_DISTANCES = [1]
GLCM_ANGLES = [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]
GLCM_LEVELS = 64

# -- Gabor --
GABOR_FREQS = [0.05, 0.1, 0.15, 0.2, 0.25]
GABOR_THETAS = [i * np.pi / 8 for i in range(8)]

# Precompute Gabor kernels once on load for 40x speedup via cv2.filter2D
PRECOMPUTED_GABOR_KERNELS: list[tuple[np.ndarray, np.ndarray]] = []
for _freq in GABOR_FREQS:
    for _theta in GABOR_THETAS:
        _gk = gabor_kernel(_freq, theta=_theta)
        PRECOMPUTED_GABOR_KERNELS.append((
            np.real(_gk).astype(np.float32),
            np.imag(_gk).astype(np.float32)
        ))

# -- FFT --
FFT_BINS = 64

# -- Shape --
GRID_SIZE = 8                         # 8x8 grid mask density
PROFILE_N = 32                        # samples for width / contour profile
RADIUS_N = 64                         # samples for radius signature
HOG_CROP = 64                         # resize crop to 64x64
HOG_CELL = (16, 16)
HOG_BLOCK = (2, 2)
HOG_ORIENT = 9
# HOG output: blocks_per_axis = (64/16 - 2 + 1) = 3 -> 3x3=9 blocks
#             features = 9 * (2*2*9) = 324

# -- Spatial --
SPATIAL_GRID = 4
SPATIAL_CELL = IMG_SIZE // SPATIAL_GRID   # 56
SPATIAL_HSV_BINS = 8


# ===================================================================== #
#  1. TIỀN XỬ LÝ & MASKING                                              #
# ===================================================================== #

def _pad_to_square(img: np.ndarray) -> np.ndarray:
    """Center an image on a square canvas without changing its aspect ratio."""
    h, w = img.shape[:2]
    side = max(h, w)
    if h == w:
        return img

    border_pixels = np.concatenate(
        (img[0], img[-1], img[1:-1, 0], img[1:-1, -1]),
        axis=0,
    )
    fill = np.median(border_pixels, axis=0).astype(img.dtype)
    square = np.empty((side, side, img.shape[2]), dtype=img.dtype)
    square[:] = fill
    top = (side - h) // 2
    left = (side - w) // 2
    square[top:top + h, left:left + w] = img
    return square


def create_foreground_mask(img: np.ndarray) -> np.ndarray:
    """Tạo binary mask phân tách foreground (món ăn) / background.

    Pipeline:
      1. GrabCut (rectangle init, margin 10 px, 5 iterations).
      2. Morphological opening + closing (elliptical kernel 5x5).
      Fallback: Otsu thresholding nếu GrabCut lỗi.

    Args:
        img: BGR uint8, shape (H, W, 3).

    Returns:
        Binary mask uint8 {0, 255}, shape (H, W).
    """
    h, w = img.shape[:2]
    mask_gc = np.zeros((h, w), dtype=np.uint8)
    used_otsu = False

    try:
        bgd = np.zeros((1, 65), dtype=np.float64)
        fgd = np.zeros((1, 65), dtype=np.float64)
        margin = 10
        rect = (margin, margin, w - 2 * margin, h - 2 * margin)
        cv2.grabCut(img, mask_gc, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
        binary = np.where(
            (mask_gc == cv2.GC_FGD) | (mask_gc == cv2.GC_PR_FGD), 255, 0
        ).astype(np.uint8)
    except cv2.error as exc:
        LOGGER.warning("GrabCut failed; falling back to Otsu thresholding: %s", exc)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        used_otsu = True

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

    if not np.any(binary):
        if not used_otsu:
            LOGGER.warning("GrabCut returned an empty mask; retrying with Otsu thresholding.")
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        if not np.any(binary):
            raise ValueError("Foreground segmentation and Otsu fallback both returned an empty mask.")
    return binary


# ===================================================================== #
#  2. COLOR FEATURES  (210 dim)                                          #
# ===================================================================== #

def _hist_channel(
    channel: np.ndarray,
    mask: np.ndarray,
    bins: int,
    vrange: Tuple[int, int],
) -> np.ndarray:
    """Histogram chuẩn hóa cho 1 kênh ảnh (dùng mask)."""
    hist = cv2.calcHist([channel], [0], mask, [bins], list(vrange))
    hist = hist.flatten().astype(np.float64)
    total = hist.sum()
    if total > 0:
        hist /= total
    return hist


def _color_moments(channel: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Mean, Std, Skewness trên vùng foreground của 1 kênh."""
    px = channel[mask > 0].astype(np.float64)
    if len(px) == 0:
        return np.zeros(3, dtype=np.float64)
    return np.array([
        np.mean(px),
        np.std(px),
        float(sp_stats.skew(px)) if len(px) > 2 and np.ptp(px) > 0 else 0.0,
    ], dtype=np.float64)


def get_color_features(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Trích xuất đặc trưng màu sắc.

    Thành phần:
      - HSV Global Histogram  (32 bin x 3 kênh = 96)
      - Lab Global Histogram  (32 bin x 3 kênh = 96)
      - HSV Color Moments     (3 kênh x 3 = 9)
      - Lab Color Moments     (3 kênh x 3 = 9)
    Tổng: **210 dim**.

    Args:
        img:  BGR uint8 (H, W, 3).
        mask: Binary uint8 {0, 255} (H, W).
    """
    m8 = (mask > 0).astype(np.uint8) * 255
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2Lab)

    parts: list[np.ndarray] = []

    # HSV histogram (H: 0-180, S/V: 0-256)
    parts.append(_hist_channel(hsv[:, :, 0], m8, HIST_BINS, (0, 180)))
    parts.append(_hist_channel(hsv[:, :, 1], m8, HIST_BINS, (0, 256)))
    parts.append(_hist_channel(hsv[:, :, 2], m8, HIST_BINS, (0, 256)))

    # Lab histogram (L: 0-256, a/b: 0-256)
    for c in range(3):
        parts.append(_hist_channel(lab[:, :, c], m8, HIST_BINS, (0, 256)))

    # Color moments
    for c in range(3):
        parts.append(_color_moments(hsv[:, :, c], m8))
    for c in range(3):
        parts.append(_color_moments(lab[:, :, c], m8))

    return np.concatenate(parts)  # 96 + 96 + 9 + 9 = 210


# ===================================================================== #
#  3. TEXTURE FEATURES  (179 dim)                                        #
# ===================================================================== #

def _lbp_histogram(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """LBP uniform histogram (radius=1, P=8 -> 10 bins)."""
    lbp = local_binary_pattern(gray, LBP_N_POINTS, LBP_RADIUS, method="uniform")
    px = lbp[mask > 0]
    if len(px) == 0:
        return np.zeros(LBP_BINS, dtype=np.float64)
    hist, _ = np.histogram(px, bins=LBP_BINS, range=(0, LBP_BINS))
    hist = hist.astype(np.float64)
    s = hist.sum()
    if s > 0:
        hist /= s
    return hist


def _eoh(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Edge Orientation Histogram (Sobel, 9 bins, 0-180 deg)."""
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    angle = np.degrees(np.arctan2(gy, gx)) % 180

    mb = mask > 0
    m_masked = mag[mb]
    a_masked = angle[mb]
    if len(m_masked) == 0:
        return np.zeros(EOH_BINS, dtype=np.float64)

    hist, _ = np.histogram(a_masked, bins=EOH_BINS, range=(0, 180), weights=m_masked)
    hist = hist.astype(np.float64)
    s = hist.sum()
    if s > 0:
        hist /= s
    return hist


def _glcm_features(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """GLCM Haralick: Energy, Contrast, Homogeneity, Correlation.
    distances=[1], 4 angles -> 4 props x 4 angles = 16 dim."""
    quantized = np.minimum(gray.astype(np.uint16) * GLCM_LEVELS // 256, GLCM_LEVELS - 1)
    foreground = mask > 0
    levels = np.arange(GLCM_LEVELS, dtype=np.float64)
    delta = levels[:, None] - levels[None, :]
    outputs = [[], [], [], []]

    for dy, dx in ((0, 1), (-1, 1), (-1, 0), (-1, -1)):
        y0, y1 = max(0, -dy), min(gray.shape[0], gray.shape[0] - dy)
        x0, x1 = max(0, -dx), min(gray.shape[1], gray.shape[1] - dx)
        first = quantized[y0:y1, x0:x1]
        second = quantized[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
        valid = foreground[y0:y1, x0:x1] & foreground[y0 + dy:y1 + dy, x0 + dx:x1 + dx]

        if not np.any(valid):
            values = (0.0, 0.0, 0.0, 0.0)
        else:
            indices = (
                first[valid].astype(np.int64) * GLCM_LEVELS
                + second[valid].astype(np.int64)
            )
            counts = np.bincount(indices, minlength=GLCM_LEVELS ** 2).reshape(
                GLCM_LEVELS, GLCM_LEVELS
            ).astype(np.float64)
            counts += counts.T
            probability = counts / counts.sum()
            px = probability.sum(axis=1)
            py = probability.sum(axis=0)
            mean_x = float(np.dot(levels, px))
            mean_y = float(np.dot(levels, py))
            std_x = float(np.sqrt(np.dot((levels - mean_x) ** 2, px)))
            std_y = float(np.sqrt(np.dot((levels - mean_y) ** 2, py)))
            correlation = (
                float(np.sum((levels[:, None] - mean_x) * (levels[None, :] - mean_y) * probability))
                / (std_x * std_y)
                if std_x > 0 and std_y > 0
                else 1.0
            )
            values = (
                float(np.sqrt(np.sum(probability ** 2))),
                float(np.sum((delta ** 2) * probability)),
                float(np.sum(probability / (1.0 + delta ** 2))),
                correlation,
            )
        for output, value in zip(outputs, values):
            output.append(value)

    return np.concatenate([np.asarray(values, dtype=np.float64) for values in outputs])


def _gabor_features(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Gabor filter bank: 5 freq x 8 theta -> mean & std = 80 dim.
    Dùng các kernel tiền tính toán và cv2.filter2D."""
    gf = (gray.astype(np.float32) / 255.0)
    mb = mask > 0
    feats: list[float] = []

    for kr, ki in PRECOMPUTED_GABOR_KERNELS:
        rr = cv2.filter2D(gf, cv2.CV_32F, kr, borderType=cv2.BORDER_REFLECT)
        ii = cv2.filter2D(gf, cv2.CV_32F, ki, borderType=cv2.BORDER_REFLECT)
        mag = np.sqrt(rr ** 2 + ii ** 2)
        px = mag[mb]
        if len(px) > 0:
            feats.extend([float(np.mean(px)), float(np.std(px))])
        else:
            feats.extend([0.0, 0.0])

    return np.array(feats, dtype=np.float64)


def _fft_radial(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Stripe FFT: 2D FFT magnitude -> radial profile (64 dim).
    Bắt đặc trưng chu kỳ vân lông."""
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return np.zeros(FFT_BINS, dtype=np.float64)
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    crop = gray[y0:y1, x0:x1].astype(np.float64)
    crop_mask = mask[y0:y1, x0:x1] > 0
    mean = float(np.mean(crop[crop_mask]))
    fg = crop - mean
    fg[~crop_mask] = 0.0

    spectrum = fftshift(fft2(fg))
    mag = np.log1p(np.abs(spectrum))

    h, w = mag.shape
    cy, cx = h // 2, w // 2
    max_r = min(cy, cx)

    Y, X = np.ogrid[:h, :w]
    r_map = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).astype(int)

    radial = np.zeros(max_r + 1, dtype=np.float64)
    for i in range(max_r + 1):
        ring = mag[r_map == i]
        if len(ring) > 0:
            radial[i] = np.mean(ring)

    if max_r > 0:
        idx = np.linspace(0, max_r, FFT_BINS).astype(int)
        profile = radial[idx]
    else:
        profile = np.zeros(FFT_BINS, dtype=np.float64)

    mx = np.max(np.abs(profile))
    if mx > 0:
        profile /= mx
    return profile


def get_texture_features(gray_img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Trích xuất đặc trưng kết cấu.

    Thành phần:
      - LBP  : 10 dim
      - EOH  :  9 dim
      - GLCM : 16 dim
      - Gabor: 80 dim
      - FFT  : 64 dim
    Tổng: **179 dim**.

    Args:
        gray_img: Grayscale uint8 (H, W).
        mask:     Binary uint8 {0, 255} (H, W).
    """
    foreground = mask > 0
    texture_gray = gray_img.copy()
    texture_gray[~foreground] = np.mean(gray_img[foreground]).astype(gray_img.dtype)
    return np.concatenate([
        _lbp_histogram(texture_gray, mask),
        _eoh(texture_gray, mask),
        _glcm_features(texture_gray, mask),
        _gabor_features(texture_gray, mask),
        _fft_radial(texture_gray, mask),
    ])


# ===================================================================== #
#  4. SHAPE FEATURES  (527 dim)                                          #
# ===================================================================== #

def _hu_and_scalars(mask: np.ndarray) -> np.ndarray:
    """Hu Moments (7) + Area ratio, Perimeter norm, Compactness,
    Circularity (4) = 11 dim."""
    mom = cv2.moments(mask)
    hu = cv2.HuMoments(mom).flatten()
    hu = -np.sign(hu) * np.log10(np.abs(hu) + 1e-12)

    h, w = mask.shape
    area = float(np.sum(mask > 0))
    area_ratio = area / (h * w)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        cnt = max(contours, key=cv2.contourArea)
        perim = cv2.arcLength(cnt, True)
        cnt_area = cv2.contourArea(cnt)
        perim_norm = perim / (2 * (h + w)) if (h + w) > 0 else 0.0
        compactness = (perim ** 2) / (4 * np.pi * cnt_area) if cnt_area > 0 else 0.0
        circularity = (4 * np.pi * cnt_area) / (perim ** 2) if perim > 0 else 0.0
    else:
        perim_norm, compactness, circularity = 0.0, 0.0, 0.0

    scalars = np.array([area_ratio, perim_norm, compactness, circularity])
    return np.concatenate([hu, scalars])


def _grid_mask_density(mask: np.ndarray) -> np.ndarray:
    """Lưới 8x8 trên mask -> mật độ foreground mỗi ô (64 dim)."""
    h, w = mask.shape
    ch, cw = h // GRID_SIZE, w // GRID_SIZE
    grid = np.zeros(GRID_SIZE * GRID_SIZE, dtype=np.float64)
    k = 0
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            cell = mask[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
            grid[k] = np.mean(cell > 0)
            k += 1
    return grid


def _width_profile(mask: np.ndarray) -> np.ndarray:
    """Width Profile: chiều rộng foreground theo từng hàng (32 dim)."""
    h = mask.shape[0]
    prof = np.zeros(h, dtype=np.float64)
    for r in range(h):
        cols = np.where(mask[r] > 0)[0]
        if len(cols) > 0:
            prof[r] = cols[-1] - cols[0] + 1
    mx = prof.max()
    if mx > 0:
        prof /= mx
    idx = np.linspace(0, h - 1, PROFILE_N).astype(int)
    return prof[idx]


def _contour_profile(mask: np.ndarray) -> np.ndarray:
    """Contour Profile: chiều cao foreground theo từng cột (32 dim)."""
    w = mask.shape[1]
    prof = np.zeros(w, dtype=np.float64)
    for c in range(w):
        rows = np.where(mask[:, c] > 0)[0]
        if len(rows) > 0:
            prof[c] = rows[-1] - rows[0] + 1
    mx = prof.max()
    if mx > 0:
        prof /= mx
    idx = np.linspace(0, w - 1, PROFILE_N).astype(int)
    return prof[idx]


def _radius_signature(mask: np.ndarray) -> np.ndarray:
    """Radius Signature: khoảng cách trọng tâm -> viền (64 dim)."""
    mom = cv2.moments(mask)
    if mom["m00"] == 0:
        return np.zeros(RADIUS_N, dtype=np.float64)

    cx = mom["m10"] / mom["m00"]
    cy = mom["m01"] / mom["m00"]

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return np.zeros(RADIUS_N, dtype=np.float64)

    cnt = max(contours, key=cv2.contourArea)
    pts = cnt.squeeze()
    if pts.ndim < 2 or len(pts) < 3:
        return np.zeros(RADIUS_N, dtype=np.float64)

    dx = pts[:, 0].astype(np.float64) - cx
    dy = pts[:, 1].astype(np.float64) - cy
    angles = np.arctan2(dy, dx)
    dists = np.sqrt(dx ** 2 + dy ** 2)

    order = np.argsort(angles)
    target = np.linspace(-np.pi, np.pi, RADIUS_N, endpoint=False)
    sig = np.interp(target, angles[order], dists[order], period=2 * np.pi)

    mx = sig.max()
    if mx > 0:
        sig /= mx
    return sig


def _hog_features(mask: np.ndarray, gray: np.ndarray) -> np.ndarray:
    """HOG chuyên biệt: crop bbox -> 64x64, cell 16x16, block 2x2,
    9 bins, L2-Hys -> **324 dim**."""
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return np.zeros(324, dtype=np.float64)

    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    if y1 <= y0 or x1 <= x0:
        return np.zeros(324, dtype=np.float64)

    crop = gray[y0:y1 + 1, x0:x1 + 1].copy()
    crop_mask = mask[y0:y1 + 1, x0:x1 + 1] > 0
    crop[crop_mask == 0] = np.mean(crop[crop_mask]).astype(crop.dtype)
    crop = cv2.resize(crop, (HOG_CROP, HOG_CROP), interpolation=cv2.INTER_LINEAR)

    return hog(
        crop,
        orientations=HOG_ORIENT,
        pixels_per_cell=HOG_CELL,
        cells_per_block=HOG_BLOCK,
        block_norm="L2-Hys",
        feature_vector=True,
    ).astype(np.float64)


def get_shape_features(mask: np.ndarray, gray: Optional[np.ndarray] = None) -> np.ndarray:
    """Trích xuất đặc trưng hình dáng từ mask.

    Thành phần:
      - Hu Moments + scalars :  11 dim
      - Grid Mask (8x8)      :  64 dim
      - Width Profile         :  32 dim
      - Contour Profile       :  32 dim
      - Radius Signature      :  64 dim
      - HOG (64x64)           : 324 dim
    Tổng: **527 dim**.

    Args:
        mask: Binary uint8 {0, 255} (H, W).
        gray: Grayscale uint8 (H, W) — cần cho HOG.
    """
    hog_feat = _hog_features(mask, gray) if gray is not None else np.zeros(324)

    return np.concatenate([
        _hu_and_scalars(mask),
        _grid_mask_density(mask),
        _width_profile(mask),
        _contour_profile(mask),
        _radius_signature(mask),
        hog_feat,
    ])


# ===================================================================== #
#  5. SPATIAL FEATURES  4x4 grid  (544 dim)                              #
# ===================================================================== #

def get_spatial_features(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Đặc trưng không gian: chia 224x224 thành 16 ô (4x4).

    Mỗi ô chứa foreground:
      - HSV Histogram  (8 bin x 3 kênh = 24)
      - LBP Histogram  (10)
    -> 34 dim / ô.   Tổng: **544 dim**.

    Ô không chứa foreground (< 10 px) -> vector 0.

    Args:
        img:  BGR uint8 (224, 224, 3).
        mask: Binary uint8 {0, 255} (224, 224).
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    foreground = mask > 0
    if np.any(foreground):
        gray[~foreground] = np.mean(gray[foreground]).astype(gray.dtype)

    per_cell = SPATIAL_HSV_BINS * 3 + LBP_BINS  # 34
    out = np.zeros(SPATIAL_GRID ** 2 * per_cell, dtype=np.float64)

    k = 0
    for r in range(SPATIAL_GRID):
        for c in range(SPATIAL_GRID):
            y0, y1 = r * SPATIAL_CELL, (r + 1) * SPATIAL_CELL
            x0, x1 = c * SPATIAL_CELL, (c + 1) * SPATIAL_CELL
            cm = mask[y0:y1, x0:x1]

            if np.sum(cm > 0) < 10:
                k += per_cell
                continue

            cm8 = (cm > 0).astype(np.uint8) * 255
            ch = hsv[y0:y1, x0:x1]
            cg = gray[y0:y1, x0:x1]

            cell_feat = np.concatenate([
                _hist_channel(ch[:, :, 0], cm8, SPATIAL_HSV_BINS, (0, 180)),
                _hist_channel(ch[:, :, 1], cm8, SPATIAL_HSV_BINS, (0, 256)),
                _hist_channel(ch[:, :, 2], cm8, SPATIAL_HSV_BINS, (0, 256)),
                _lbp_histogram(cg, cm8),
            ])
            out[k:k + per_cell] = cell_feat
            k += per_cell

    return out


# ===================================================================== #
#  6. FUSION — Hàm tổ hợp chính                                         #
# ===================================================================== #

def extract_raw_features(
    image_input: str | np.ndarray,
    precomputed_mask: Optional[np.ndarray] = None,
) -> Optional[np.ndarray]:
    """Hàm chính: đọc ảnh/mảng BGR -> masking -> trích tất cả đặc trưng ->
    concatenate -> L2-normalize.

    Args:
        image_input: Đường dẫn tệp ảnh hoặc mảng BGR numpy array.
        precomputed_mask: Mặt nạ nhị phân tiền cảnh đã tính trước (nếu có).

    Returns:
        Vector float64 shape (1460,) đã L2-normalize, hoặc None nếu lỗi.
    """
    if isinstance(image_input, str):
        img = cv2.imread(image_input)
    else:
        img = image_input

    if img is None:
        return None

    img = _pad_to_square(img)
    img = cv2.resize(img, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_LINEAR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if precomputed_mask is not None:
        if precomputed_mask.shape[:2] != (IMG_SIZE, IMG_SIZE):
            mask = cv2.resize(precomputed_mask, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_NEAREST)
        else:
            mask = precomputed_mask
    else:
        mask = create_foreground_mask(img)
    if mask.ndim != 2 or not np.any(mask > 0):
        raise ValueError("A non-empty, two-dimensional foreground mask is required.")

    raw = np.concatenate([
        get_color_features(img, mask),       # 210
        get_texture_features(gray, mask),    # 179
        get_shape_features(mask, gray),      # 527
        get_spatial_features(img, mask),     # 544
    ])

    # Guard against numerical issues (e.g., skew/glcm correlation producing NaN).
    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)

    norm = np.linalg.norm(raw)
    if norm > 0:
        raw /= norm

    # Final safety pass after normalization.
    return np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
