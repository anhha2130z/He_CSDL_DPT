# TỔNG QUAN HỆ THỐNG TÌM KIẾM ẢNH MÓN ĂN (FOOD CBIR SYSTEM)

## 1. Mục tiêu hệ thống
Hệ thống CBIR (Content-Based Image Retrieval) được xây dựng để tìm kiếm các hình ảnh món ăn tương tự dựa trên nội dung thị giác (Visual Content), hoàn toàn không phụ thuộc vào nhãn text thủ công hay học sâu (No Deep Learning).

Người dùng tải lên 1 ảnh món ăn truy vấn, hệ thống sẽ:
- Tiền xử lý & tách vùng đối tượng (GrabCut / Saliency Masking + Morphology Opening/Closing).
- Trích xuất vector đặc trưng thị giác cổ điển 1.460 chiều:
  - **Color (Màu sắc):** 210 chiều (HSV / CIE-Lab histograms + Color Moments: Mean, Std, Skewness).
  - **Texture (Kết cấu vân bề mặt):** 179 chiều (LBP, EOH, GLCM/Haralick, Gabor filter bank 40 bộ lọc, Stripe-FFT 2D).
  - **Shape (Hình dáng đối tượng):** 527 chiều (Hu Moments, scalars, Grid Mask Density 8x8, Width/Contour Profile, Radius Signature, HOG ROI 64x64).
  - **Spatial (Bố cục không gian):** 544 chiều (Lưới 4x4 x (24 HSV + 10 LBP)).
- Chuẩn hóa L2-Normalization.
- Giảm chiều bằng PCA (1.460 chiều &rarr; tối đa 512 chiều, tùy số mẫu); tỷ lệ phương sai được báo theo mô hình thực tế.
- Xếp hạng theo Cosine score/distance qua FAISS IndexFlatIP (hoặc SciPy vectorized cosine).
- Trả về Top-K ảnh kèm phần trăm quy đổi từ điểm cosine; đây không phải xác suất hay phần trăm độ chính xác.

---

## 2. Công nghệ và thư viện sử dụng
- **Python 3.10+ / 3.11+ / 3.12+**: Ngôn ngữ cốt lõi.
- **OpenCV (`opencv-python`)**: Đọc/ghi ảnh, resize, tách nền GrabCut, toán tử hình thái học, tính Sobel gradient, Contour, Moments.
- **NumPy**: Xử lý đại số tuyến tính, ma trận vector hóa, lưu định dạng nhị phân `features.npy`.
- **SciPy**: Biến đổi Fourier 2D (`scipy.fft`), thống kê độ lệch Skewness (`scipy.stats`), tính khoảng cách Cosine (`scipy.spatial.distance.cdist`).
- **scikit-image**: Local Binary Pattern (LBP), GLCM / Haralick texture, Gabor filter bank, Histogram of Oriented Gradients (HOG).
- **scikit-learn**: Principal Component Analysis (PCA) giảm chiều đặc trưng.
- **FAISS (`faiss-cpu`)**: Chỉ mục tìm kiếm chính xác theo tích vô hướng (`IndexFlatIP`).
- **SQLite 3**: Quản lý siêu dữ liệu quan hệ nhẹ (`database.db`).
- **Flask**: Web Application Full-Stack `app.py` phục vụ giao diện web trực quan tìm kiếm Top 5 món ăn giống nhất.
- **Pickle**: Tuần tự hóa mô hình PCA (`pca_model.pkl`).

---

## 3. Kiến trúc luồng trích xuất đặc trưng (1460D &rarr; tối đa 512D)

### 3.1. Tiền xử lý & Mặt nạ vùng chọn (Foreground Segmentation)
- Thuật toán phân đoạn GrabCut kết hợp Morphology Opening/Closing (kernel elip $5 \times 5$) để loại bỏ nhiễu và làm liền mạch vùng món ăn.
- Ảnh không vuông được căn giữa trên canvas vuông; phần đệm dùng màu trung vị viền ảnh để giữ tỷ lệ trước khi resize.
- Fallback Otsu nếu GrabCut phát sinh lỗi; mặt nạ rỗng cuối cùng được báo lỗi thay vì đổi âm thầm thành toàn ảnh.

### 3.2. Bốn nhóm đặc trưng thị giác cổ điển
1. **Color (210 chiều):**
   - Global HSV Histogram: 96 chiều.
   - Global CIE-Lab Histogram: 96 chiều.
   - Color Moments (Mean, Std, Skewness trên 6 kênh): 18 chiều.
2. **Texture (179 chiều):**
   - Uniform LBP: 10 chiều.
   - Edge Orientation Histogram (EOH): 9 chiều.
   - GLCM / Haralick: 16 chiều (Contrast, Dissimilarity, Homogeneity, Energy, Correlation, ASM).
   - Gabor filter bank: 80 chiều (5 tần số $\times$ 8 hướng, gồm mean và std).
   - Stripe FFT 2D: 64 chiều.
3. **Shape (527 chiều):**
   - Hu Moments (7 bất biến) + Scalars (Area, Perimeter, Compactness, Circularity): 11 chiều.
   - Grid Mask Density (Lưới 8x8): 64 chiều.
   - Width / Contour Profile: 64 chiều.
   - Radius Signature (tâm tới biên theo góc): 64 chiều.
   - HOG trên vùng ROI món ăn (64x64): 324 chiều.
4. **Spatial Layout (544 chiều):**
   - Chia lưới 4x4 = 16 ô cục bộ.
   - Mỗi ô: 24 chiều HSV + 10 chiều LBP = 34 chiều $\times 16 = 544$ chiều.

### 3.3. L2-Normalization và PCA Compression
$$\mathbf{v}_{\text{raw}} = [\mathbf{f}_{\text{color}} \parallel \mathbf{f}_{\text{texture}} \parallel \mathbf{f}_{\text{shape}} \parallel \mathbf{f}_{\text{spatial}}] \in \mathbb{R}^{1460}$$
$$\mathbf{v}_{\text{norm}} = \frac{\mathbf{v}_{\text{raw}}}{\|\mathbf{v}_{\text{raw}}\|_2}$$
$$\mathbf{x} = \text{PCA.transform}(\mathbf{v}_{\text{norm}}) \in \mathbb{R}^{k},\quad k \le 512$$

---

## 4. Kiến trúc lưu trữ lai (Hybrid Database)
- **SQLite (`database/database.db`)**:
  - Bảng `Images(ImageID INTEGER PRIMARY KEY AUTOINCREMENT, ImagePath TEXT NOT NULL UNIQUE)`.
  - Quản lý siêu dữ liệu, ngăn ngừa trùng lặp bản ghi bằng ràng buộc `UNIQUE`.
- **NumPy Matrix (`database/features.npy`)**:
  - Ma trận $(N, k)$ kiểu `float32`, với $k \leq 512$, nạp trực tiếp vào RAM để tính toán.
- **Chỉ mục FAISS (`database/faiss.index`)**:
  - Cấu trúc `IndexFlatIP` tìm kiếm chính xác trên vector đã chuẩn hóa; thời gian phụ thuộc kích thước chỉ mục và phần cứng.
- **Pickle Model (`database/pca_model.pkl`)**:
  - Lưu trữ trạng thái mô hình PCA đã huấn luyện offline.
- **Bảng đối chiếu CSV (`database/features.csv`)**:
  - Bảng $N$ hàng và $2+k$ cột (`ImageID`, `ImagePath`, `Dim_0` ... `Dim_{k-1}`) để gỡ lỗi và kiểm tra trực quan.
