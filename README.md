# Hệ thống Tìm kiếm Ảnh Món Ăn dựa trên Nội dung (Food Image CBIR System)

Hệ thống **CBIR (Content-Based Image Retrieval)** tìm kiếm và truy hồi ảnh món ăn tương đồng dựa trên nội dung thị giác thực tế, sử dụng hoàn toàn **Thị giác máy tính cổ điển (Classical Computer Vision - No Deep Learning)** theo kiến trúc chuẩn hóa tham khảo từ [bird-search-system](https://github.com/b22dccn256/bird-search-system).

Hệ thống trích xuất vector đặc trưng 1.460 chiều (Màu sắc, Kết cấu, Hình dạng, Bố cục không gian), chuẩn hóa $L_2$, giảm chiều bằng PCA và tìm Top 5 ảnh gần nhất bằng Cosine Similarity. CSDL lai gồm SQLite, NumPy và FAISS; ứng dụng Flask xác thực tính nhất quán các artifact khi khởi động.

---

## 📁 Cấu trúc Dự án Chuẩn hóa

```
CSDLDPT/
│
├── data/                               # Tập ảnh cục bộ; không được phân phối kèm repository
├── database/                           # Artifact chỉ mục được tạo cục bộ
│
├── tailieu_md/                         # Tài liệu thuyết minh chi tiết
│   ├── SYSTEM_OVERVIEW.md              # Tổng quan kiến trúc hệ thống
│   └── Chương 3 và 4.md                # Trích xuất đặc trưng và tìm kiếm ảnh
│
├── templates/                          # Giao diện HTML Web Flask
│   └── index.html                      # Template giao diện tìm kiếm Top 5
├── static/                             # Tệp tĩnh Web
│   ├── css/style.css                   # Định kiểu Glassmorphism hiện đại
│   └── js/app.js                       # Logic tương tác AJAX xử lý tìm kiếm
├── tests/
│   ├── test_feature_extractors.py      # Kiểm tra hành vi vùng mask và mask rỗng
│   ├── test_image_normalization.py     # Kiểm tra padding giữ tỷ lệ ảnh
│   ├── test_offline_publish.py         # Kiểm tra rollback khi build chỉ mục lỗi
│   └── test_upload_persistence.py      # Kiểm tra lưu ảnh, vector và loại tự khớp
├── app.py                              # Ứng dụng Web Flask tìm kiếm Top 5 ảnh món ăn (Port 5000)
├── 1_extract_offline.py                # Pipeline trích xuất đặc trưng ngoại tuyến & nén PCA
├── feature_extractors.py               # Module trích xuất 4 bộ thuộc tính cổ điển (1.460D)
├── BAO_CAO_CSDLDPT.md                  # Báo cáo học thuật toàn diện 5 phần theo đề cương
└── README.md                           # Hướng dẫn tổng quan và vận hành dự án
```

---

## 🧠 Chi tiết 4 Bộ Thuộc Tính Nhận Diện (1.460 Chiều &rarr; PCA tối đa 512 Chiều)

```
                 KIẾN TRÚC BỘ ĐẶC TRƯNG THỊ GIÁC CỔ ĐIỂN (1.460 CHIỀU)
  ┌───────────────────┬───────────────────┬───────────────────┬───────────────────┐
  │   1. COLOR (210)  │  2. TEXTURE (179) │   3. SHAPE (527)  │  4. SPATIAL (544) │
  ├───────────────────┼───────────────────┼───────────────────┼───────────────────┤
  │ - HSV Hist: 96    │ - Unif LBP: 10    │ - Hu+Scalars: 11  │ - 4x4 Grid Cells  │
  │ - Lab Hist: 96    │ - EOH: 9          │ - Grid Mask: 64   │   x (24 HSV +     │
  │ - Moments: 18     │ - GLCM: 16        │ - Contour Prof: 64│      10 LBP)      │
  │   (Mean/Std/Skew) │ - Gabor Bank: 80  │ - Radius Sign: 64 │   = 16 x 34       │
  │                   │ - Stripe-FFT: 64  │ - HOG ROI: 324    │   = 544           │
  └───────────────────┴───────────────────┴───────────────────┴───────────────────┘
                                          │
                               [L2-NORMALIZATION]
                                          │
                             [PCA DIMENSION REDUCTION]
                           1.460 Chiều ────► 512 Chiều
```

| STT | Nhóm đặc trưng | Thuật toán trích rút | Số chiều thô | Giá trị kỹ thuật trong bài toán tìm kiếm ảnh |
|:---:|:---|:---|:---:|:---|
| **1** | **Màu sắc (Color)** | HSV Histogram (96d) + CIE-Lab Histogram (96d) + Color Moments $\mu, \sigma, s$ (18d) | **210** | Tách rời độ sáng khỏi sắc thái màu, bất biến với cường độ chiếu sáng; nắm bắt gam màu chủ đạo đặc trưng của từng món. |
| **2** | **Kết cấu (Texture)** | Uniform LBP (10d) + EOH (9d) + GLCM Haralick (16d) + Gabor Bank 40 bộ lọc (80d) + Stripe-FFT 2D (64d) | **179** | Bắt trọn tính chất bề mặt vi mô (hạt cơm, sợi bún, nước súp lỏng, gà rán gồ ghề) và họa tiết tuần hoàn. |
| **3** | **Hình dạng (Shape)** | 7 Hu Moments + 4 Scalars (11d) + Grid Mask (64d) + Contour Profile (64d) + Radius Signature (64d) + HOG ROI (324d) | **527** | Mô tả hình học đối tượng món ăn sau khi tách nền GrabCut, nhận diện đường biên và viền ngoài thức ăn. |
| **4** | **Bố cục (Spatial)** | Lưới không gian $4 \times 4$ ô khối $\times$ (24 HSV + 10 LBP) | **544** | Bảo toàn vị trí nguyên liệu trên lòng đĩa (trung tâm đĩa chứa gì, vành đai ngoài chứa gì). |
| *--* | **Nén PCA** | **Principal Component Analysis** | **tối đa 512** | **Tỷ lệ phương sai được tính từ dữ liệu huấn luyện và hiển thị sau khi build.** |

---

## 🗄️ Kiến trúc Cơ sở dữ liệu lai (Hybrid Database)

- **SQLite (`database/database.db`):** Quản lý bảng `Images(ImageID, ImagePath)`. Ràng buộc `UNIQUE` ngăn ngừa trùng lặp và hỗ trợ cơ chế nạp bù (Resume-safe).
- **NumPy Matrix (`database/features.npy`):** Ma trận $(N, k)$ kiểu `float32`, trong đó $k \leq 512$ phụ thuộc số ảnh dùng huấn luyện PCA.
- **Chỉ mục FAISS (`database/faiss.index`):** Cấu trúc `IndexFlatIP` tìm kiếm chính xác theo tích vô hướng trên vector đã chuẩn hóa; thời gian thực tế phụ thuộc quy mô dữ liệu và phần cứng.
- **Pickle Model (`database/pca_model.pkl`):** Lưu trữ trạng thái mô hình PCA đã huấn luyện ngoại tuyến.
- **Bảng đối chiếu CSV (`database/features.csv`):** Bảng $N$ hàng với 2 cột định danh và $k$ cột vector (`Dim_0` ... `Dim_{k-1}`), trong đó $k$ là số thành phần PCA thực tế.
- **Manifest (`database/index_manifest.json`):** Ghi số lượng/chiều dữ liệu và SHA-256 của từng artifact; ứng dụng từ chối khởi động nếu các tệp không đồng bộ.
- **Vector thô đã publish (`database/raw_features.npz`):** Gắn từng vector với đường dẫn và dấu vân tay của tập dữ liệu để ứng dụng kiểm tra đồng bộ.
- **Checkpoint build (`database/.raw_features.checkpoint.npz`):** Tệp tạm dùng để tiếp tục trích xuất nếu build bị gián đoạn; được xóa sau khi publish thành công. Nếu build lỗi giữa lúc publish, bộ artifact cũ được khôi phục khi rollback thành công.

---

## 🛠️ Hướng dẫn Cài đặt và Vận hành

> **Dữ liệu ảnh và chỉ mục không được đưa vào repository.** Bộ ảnh được tổng hợp từ Internet và chưa có quyền phân phối lại; các thư mục `data/` và `database/` vì vậy bị loại khỏi Git. Để chạy hệ thống, hãy tự chuẩn bị bộ ảnh mà bạn có quyền sử dụng trong `data/`, sau đó tạo lại chỉ mục theo hướng dẫn bên dưới.

### 1. Cài đặt môi trường
Khuyến nghị sử dụng Python 3.10 hoặc 3.11:
```bash
pip install opencv-python numpy scipy scikit-image scikit-learn faiss-cpu flask pillow
```

### 2. Trích xuất đặc trưng ngoại tuyến (Offline Extraction)
Lệnh này quét ảnh trong `data/`, tạo mặt nạ GrabCut, trích xuất 1.460D, giảm chiều PCA và tạo lại SQLite, NumPy, CSV, FAISS cùng manifest theo một thứ tự ảnh xác định:
```bash
python 1_extract_offline.py
```
*(Checkpoint build lưu vector cùng đường dẫn mỗi 25 ảnh. Nếu tập ảnh thay đổi, checkpoint cũ tự bị vô hiệu hóa. Dataset tùy chọn phải nằm bên trong `data/`. Ảnh không vuông được căn giữa trên canvas vuông, phần đệm lấy màu trung vị viền ảnh, rồi resize về 224×224 để trích đặc trưng.)*

Chạy kiểm thử đơn vị:
```bash
python -m unittest discover -s tests -v
```

### 3. Khởi chạy Ứng dụng Web Flask (Tìm kiếm Top 5)

Khởi động web server Flask:
```bash
python app.py
```
Trình duyệt sẽ tự mở tại **`http://127.0.0.1:5000`** khi server khởi động.

- **Chức năng:** Tải ảnh món ăn (tối đa 10 MB, hỗ trợ kéo thả / click); máy chủ giữ nguyên tỷ lệ ảnh bằng cách căn giữa ảnh trên canvas vuông, bù phần thiếu bằng màu trung vị viền ảnh, rồi resize thành JPEG 512×512 trong `data/uploads/`. Ảnh không bị kéo méo hoặc ghép lên nền trắng. Hệ thống tạo mặt nạ GrabCut và lưu vector thô/PCA vào các artifact tương ứng; upload trùng không tạo bản sao. Ảnh truy vấn được lưu trong chỉ mục nhưng bị loại khỏi kết quả của chính truy vấn đó. Nếu dữ liệu nguồn thay đổi, cần rebuild chỉ mục trước khi lưu upload mới.
- Ảnh upload được lưu cục bộ trong `data/uploads/`; thư mục này không được đưa lên GitHub.
- Ảnh upload được giữ lại, không tự động xóa; dung lượng lưu trữ tăng theo số ảnh duy nhất. Nếu cần dọn dữ liệu, hãy dừng ứng dụng, sao lưu trước, xóa có chủ đích rồi rebuild toàn bộ chỉ mục.
- **Lưu ý:** Thời gian phản hồi và chất lượng truy hồi phụ thuộc thiết bị, dữ liệu và cách chụp. Đánh giá chất lượng bằng Precision@K/Recall@K trên tập truy vấn có nhãn; không suy ra độ chính xác từ điểm cosine.
- Giao diện hiển thị độ tương đồng theo thang phần trăm quy đổi từ điểm cosine; đây không phải xác suất hai ảnh cùng món.

Ứng dụng mặc định chỉ lắng nghe `127.0.0.1`; nếu muốn truy cập từ máy khác, cần chủ động cấu hình triển khai có kiểm soát thay vì mở server phát triển trực tiếp ra mạng.

---

## 📑 Báo cáo Học thuật
Xem báo cáo tại tệp:
👉 [BAO_CAO_CSDLDPT.md](./BAO_CAO_CSDLDPT.md)
# He_CSDL_DPT
