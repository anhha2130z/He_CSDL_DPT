# BÁO CÁO MÔN HỌC: CƠ SỞ DỮ LIỆU ĐA PHƯƠNG TIỆN
# CHƯƠNG 1 & CHƯƠNG 2: THU THẬP BỘ DỮ LIỆU VÀ XÂY DỰNG BỘ THUỘC TÍNH NHẬN DIỆN MÓN ĂN

---

# CHƯƠNG 1: THU THẬP VÀ MÔ TẢ ĐẶC ĐIỂM BỘ DỮ LIỆU ẢNH MÓN ĂN

## 1.1. Mục tiêu và quy cách xây dựng bộ dữ liệu ảnh

Để phục vụ bài toán **Tìm kiếm ảnh món ăn dựa trên nội dung (Content-Based Food Image Retrieval - CBIR)**, nhóm đã tiến hành khảo sát, thu thập và tiền xử lý một bộ cơ sở dữ liệu ảnh thực phẩm phong phú, đáp ứng nghiêm ngặt các quy chuẩn kỹ thuật:

1. **Quy mô bộ dữ liệu:**
   - Đã thu thập và chuẩn hóa thành công **564 tệp ảnh** chất lượng cao.
   - Bao phủ **110 danh mục món ăn khác nhau** (`110 categories`), tập trung sâu vào ẩm thực truyền thống Việt Nam (như *phở bò, bún riêu, bún chả, bún đậu mắm tôm, hủ tiếu, canh chua cá, gỏi cuốn, bánh bao...*) cùng các món ăn phổ biến của ẩm thực Á - Âu (*pizza, mì Ý, gimbap, nachos, pad Thái, gà rán...*).

2. **Quy chuẩn lưu trữ và khung hình:**
   - **Kích thước ảnh đồng nhất:** Tất cả các ảnh được chuẩn hóa về cùng độ phân giải $512 \times 512$ pixels.
   - **Tỉ lệ khung hình (Aspect Ratio):** Tỉ lệ tương đồng tuyệt đối $1:1$ (hình vuông), đảm bảo ma trận ảnh không bị méo mó hay biến dạng hình học khi đưa vào xử lý ma trận số.
   - **Định dạng ảnh:** Sinh viên lựa chọn định dạng `.jpg` (chuẩn màu RGB 24-bit, 3 kênh màu Red - Green - Blue, không gian màu tiêu chuẩn sRGB), tối ưu hóa dung lượng lưu trữ nhưng vẫn bảo toàn độ sắc nét và dải màu thực phẩm.

3. **Góc chụp và bố cục (Top-Down View & Central Alignment):**
   - **Góc chụp:** Chụp thẳng từ trên xuống (**Top-Down View / góc chụp 90°** vuông góc với mặt phẳng bàn ăn). Góc chụp này loại bỏ triệt để hiện tượng biến dạng phối cảnh (perspective distortion) và giảm thiểu bóng đổ xiên của thành đĩa/bát.
   - **Vật chứa:** Tất cả món ăn được đựng trong đĩa tròn, đĩa khay tròn hoặc bát/tô tròn có tính đối xứng tâm cao.
   - **Bố cục trọng tâm:** Món ăn và vật chứa luôn nằm căn giữa chính xác tại trọng tâm bức ảnh.
   - **Tỉ lệ bao phủ vật thể:** Món ăn và vật chứa chiếm từ $75\% \div 90\%$ diện tích khung ảnh ($[0.05, 0.95]$ theo cả hai chiều trục $X$ và $Y$), phần nền ngoài rìa (mặt bàn gỗ, khăn trải bàn) chỉ chiếm diện tích tối thiểu $< 15\%$.

```
+----------------------------------------------------+
| 512 px                                             |
|        +----------------------------------+        |
|        |           Viền đĩa tròn          |        |
|        |      +--------------------+      |        |
|        |      |                    |      |        |
|        |      |      MÓN ĂN        |      | 512 px |
|        |      |   (Căn giữa tâm)   |      |        |
|        |      |                    |      |        |
|        |      +--------------------+      |        |
|        |     (Góc chụp Top-Down 90°)      |        |
|        +----------------------------------+        |
+----------------------------------------------------+
```

---

## 1.2. Mô tả chi tiết đặc điểm Giống và Khác nhau của các món ăn trong bộ dữ liệu

Dựa trên 564 hình ảnh thu thập được, nhóm đã phân tích sâu các thuộc tính thị giác và chia thành 6 nhóm đặc trưng chính để mô tả sự tương đồng và khác biệt:

### Bảng tổng quát đối chiếu đặc điểm giống và khác nhau

| Nhóm đặc trưng | Đặc điểm GIỐNG NHAU giữa các ảnh | Đặc điểm KHÁC NHAU giữa các món ăn | Ý nghĩa đối với tìm kiếm |
|:---|:---|:---|:---:|
| **1. Bố cục & Góc nhìn (Layout & Viewpoint)** | - Đều chụp từ trên xuống (Top-down 90°).<br>- Vật thể nằm ở vị trí trung tâm ảnh.<br>- Khoảng cách chụp tương đồng, vật thể chiếm đa phần diện tích khung hình ($75\% - 90\%$). | - Cách thức trình bày nguyên liệu trên đĩa: có món bày phân vùng rõ rệt (bún đậu mắm tôm), có món trộn đều ngẫu nhiên (cơm rang, nộm), có món ngập trong nước dùng lỏng (phở, bún riêu). | **Rất cao** (Định vị vùng không gian) |
| **2. Hình học & Vật chứa (Shape & Container)** | - Đều có đường bao tổng thể bên ngoài theo hình tròn/bầu dục của đĩa hoặc bát tròn.<br>- Tính đối xứng tâm quanh trục bức ảnh. | - Chi tiết đường biên của từng thành phần bên trong: dạng sợi uốn lượn (bún, miến), dạng khối lập phương (đậu phụ chiên, thịt kho), dạng lát cắt bầu dục (trứng luộc, chả cá), hoặc dạng hạt li ti (cơm, mè rang). | **Cao** (Phân biệt vi hình thái) |
| **3. Màu sắc (Color Distribution)** | - Đều cấu thành từ các gam màu tự nhiên của thực phẩm tươi sống hoặc đã chín (đỏ, vàng, xanh lục, nâu, trắng ngà).<br>- Phản xạ ánh sáng tự nhiên, ít độ chói nhân tạo. | - Gam màu chủ đạo khác biệt theo trường phái món ăn:<br>+ Món canh rau: dải xanh lục ($H \approx 35^\circ - 75^\circ$).<br>+ Món súp bí đỏ, bún riêu, canh kim chi: dải cam đỏ ($H \approx 0^\circ - 25^\circ$).<br>+ Món chiên rán: dải vàng rơm, nâu cánh gián.<br>+ Món cơm, cháo: gam màu trắng ngà. | **Rất cao** (Trụ cột phân lớp) |
| **4. Kết cấu bề mặt (Texture)** | - Đều là bề mặt vật liệu hữu cơ không đồng nhất (không phẳng nhẵn bóng tuyệt đối như kim loại/gốm sứ công nghiệp). | - Độ thô ráp và cấu trúc vân bề mặt chênh lệch rõ rệt:<br>+ Bề mặt trơn mịn: nước dùng trong, súp đặc, cháo, bánh flan.<br>+ Bề mặt thô ráp, gồ ghề, nhăn nheo: da gà rán xù, nem rán giòn, khoai tây chiên.<br>+ Bề mặt dạng sợi đan xen phức tạp: bún bò, hủ tiếu, mì ramen.<br>+ Bề mặt dạng hạt rời rạc: cơm rang, hạt điều, hạt hạnh nhân. | **Rất cao** (Trụ cột phân biệt món cùng màu) |
| **5. Thành phần cấu tạo (Constituents)** | - Đều là sự kết hợp đa thành phần giữa tinh bột (gạo, mì, bột lọc), đạm (thịt, hải sản), chất xơ (rau sống, củ quả) và chất lỏng/xốt. | - Số lượng và sự phối trộn nguyên liệu:<br>+ Món đơn thành phần: cơm trắng, canh suông, bát hạt rang.<br>+ Món đa thành phần hỗn hợp: lẩu thập cẩm, bún thang, salad nga với nhiều lớp nguyên liệu đan xen. | **Cao** (Phân tích mức độ phức tạp) |
| **6. Trạng thái vật lý (Physical State)** | - Đều được đặt cố định trên mặt phẳng ngang trong thời gian chụp ảnh. | - Món dạng lỏng hoàn toàn (canh, súp, cháo) có bề mặt căng phẳng, có váng dầu mỡ hoặc hành hoa nổi.<br>- Món dạng rắn/khô (bánh mì, pizza, nem chua rán) có độ cao nổi khối rõ nét. | **Trung bình** |

---

## 1.3. Phân tích giá trị thông tin đối với bài toán tìm kiếm tương đồng (CBIR)

1. **Tính tương đồng nội lớp (Intra-Class Similarity):**
   - Các hình ảnh thuộc cùng một danh mục món ăn (ví dụ: các đĩa *Gỏi cuốn* khác nhau hoặc các bát *Bún riêu* khác nhau) chia sẻ sự đồng nhất rất cao về:
     - Gam màu chủ đạo và phân bố histogram màu sắc (màu đỏ gạch riêu cua, màu xanh hành hoa, màu vàng đậu rán).
     - Kết cấu vi mô (độ nhấp nhô của sợi bún và nước dùng).
     - Bố cục sắp xếp không gian (mặt nước dùng chiếm trọn lòng tô, hành lá rải đều bề mặt).
   - **Ý nghĩa:** Cho phép hệ thống gộp nhóm chính xác các biến thể của cùng một món ăn dù góc xoay đĩa hay ánh sáng chụp có sai khác nhẹ.

2. **Tính phân biệt liên lớp (Inter-Class Dissimilarity):**
   - Sự khác biệt về kết cấu (Texture) và hình dáng vi mô (Micro-shape) là yếu tố quyết định để phân biệt các món ăn có gam màu tương đồng:
     - *Ví dụ 1:* Cơm chiên trứng và Canh súp bí đỏ đều có màu vàng cam chủ đạo. Tuy nhiên, cơm chiên có kết cấu hạt rời rạc (chỉ số độ tương phản GLCM cao, phản ứng tần số cao ở Stripe-FFT và mật độ vi biên LBP dày đặc), trong khi súp bí đỏ có bề mặt trơn phẳng (năng lượng GLCM cao, độ đồng nhất cao, phổ FFT tập trung ở vùng tần số thấp).
     - *Ví dụ 2:* Bún bò Huế và Phở bò đều là món nước có thịt bò, nhưng hình thái sợi bún (tiết diện tròn, uốn lượn mềm) khác biệt rõ rệt với sợi phở (tiết diện dẹp hình chữ nhật, xếp lớp phẳng).
   - **Ý nghĩa:** Tránh hiện tượng nhầm lẫn đặc trưng, giúp bộ mô tả đạt độ nhạy phân lớp (Discriminative Power) vượt trội.

---

# CHƯƠNG 2: XÂY DỰNG CÁC BỘ THUỘC TÍNH NHẬN DIỆN MÓN ĂN

## 2.1. Kiến trúc tổng thể hệ thuộc tính nhận diện món ăn (1.460 Chiều)

Để giải quyết bài toán nhận diện và tìm kiếm ảnh món ăn dựa trên nội dung (Content-Based Food Image Retrieval - CBIR), hệ thống trích xuất **4 bộ thuộc tính thị giác toàn diện** với tổng cộng **1.460 chiều đặc trưng**:

```
                  KIẾN TRÚC BỘ THUỘC TÍNH NHẬN DIỆN MÓN ĂN (1.460 CHIỀU)
   ┌───────────────────┬───────────────────┬───────────────────┬───────────────────┐
   │ 1. MÀU SẮC (210D) │ 2. KẾT CẤU (179D) │3. HÌNH DÁNG (527D)│4. BỐ CỤC KG(544D) │
   ├───────────────────┼───────────────────┼───────────────────┼───────────────────┤
   │ - HSV Hist: 96D   │ - Unif LBP: 10D   │ - Hu + Scalars:11D│ - Lưới 4x4 ô      │
   │ - Lab Hist: 96D   │ - EOH Sobel: 9D   │ - Grid Mask: 64D  │   x (24 HSV +     │
   │ - Moments: 18D    │ - GLCM: 16D       │ - Width Prof: 32D │      10 LBP)      │
   │   (Mean/Std/Skew) │ - Gabor Bank: 80D │ - Contour Prof:32D│   = 16 x 34       │
   │                   │ - Stripe-FFT: 64D │ - Radius Sign: 64D│   = 544 Chiều     │
   │                   │                   │ - HOG ROI: 324D   │                   │
   └───────────────────┴───────────────────┴───────────────────┴───────────────────┘
                                           │
                         VECTOR ĐẶC TRƯNG HỢP NHẤT: 1.460 CHIỀU
```

---

## 2.2. Trình bày chi tiết các bộ đặc trưng, các chiều và ý nghĩa nhận diện

### 1. Bộ đặc trưng Màu sắc (Color Features - 210 chiều)

Màu sắc là tín hiệu thị giác trực quan nhất và phản ánh sắc thái nguyên liệu cấu thành món ăn.

#### a. Các chiều của bộ đặc trưng
* **Global HSV Histogram (96 chiều):**
  * **32 chiều Kênh Sắc thái màu ($H$ - Hue):** Đại diện cho 32 khoảng phổ màu tự nhiên từ đỏ, cam, vàng, lục, lam đến tím.
  * **32 chiều Kênh Độ bão hòa màu ($S$ - Saturation):** Đại diện cho 32 mức độ đậm đặc, thuần khiết của màu (từ màu nhạt/pha xám đến màu tươi rực rỡ).
  * **32 chiều Kênh Cường độ sáng ($V$ - Value):** Đại diện cho 32 mức độ sáng - tối của điểm ảnh.
* **Global CIE-Lab Histogram (96 chiều):**
  * **32 chiều Kênh Độ sáng tri giác ($L^*$):** Biểu diễn 32 mức độ sáng - tối theo cảm nhận thị giác của mắt người.
  * **32 chiều Trục màu $a^*$ (Xanh lục $\leftrightarrow$ Đỏ):** Thể hiện mức độ nghiêng về sắc xanh lá hay sắc đỏ.
  * **32 chiều Trục màu $b^*$ (Xanh lam $\leftrightarrow$ Vàng):** Thể hiện mức độ nghiêng về sắc xanh lam hay sắc vàng.
* **Color Moments – Mô-men thống kê phân bố màu (18 chiều):** Tính trên 6 kênh màu ($H, S, V$ và $L^*, a^*, b^*$):
  * **6 chiều Giá trị trung bình (Mean):** Thể hiện tông màu và độ sáng bình quân của món ăn trên từng kênh.
  * **6 chiều Độ lệch chuẩn (Standard Deviation):** Đo lường mức độ biến động, phân tán và độ tương phản màu sắc giữa các thành phần thực phẩm.
  * **6 chiều Độ bất đối xứng/độ xiên (Skewness):** Phản ánh xu hướng phân bố màu lệch về gam màu tối hay gam màu sáng.

#### b. Ý nghĩa của các chiều
* Nắm bắt phân bố phổ màu tổng quát mà không phụ thuộc vào điều kiện chiếu sáng khi chụp ảnh.
* Mô phỏng cảm nhận thị giác người, nhận biết chính xác sắc độ ấm/lạnh của nước dùng, độ tươi ngon của rau sống và độ chín của thịt.
* Tóm tắt cực kỳ cô đọng tông màu chủ đạo toàn cục của đĩa thức ăn, bất biến với phép quay và tịnh tiến.

#### c. Tác dụng trong xác định điểm giống và khác nhau
* **Xác định điểm GIỐNG NHAU:** Nhận diện các ảnh thuộc cùng một món ăn nhờ sự thống nhất về gam màu chủ đạo (ví dụ: các bát *Bún riêu* luôn mang sắc đỏ cam đặc trưng của cà chua và riêu cua; các bát *Canh rau cải* luôn mang sắc xanh lục).
* **Xác định điểm KHÁC NHAU:** Đóng vai trò là "tầng lọc đầu tiên" giúp phân loại và tách biệt nhanh chóng các món ăn thuộc các trường phái màu sắc khác nhau (món canh rau xanh lục $\leftrightarrow$ món súp bí đỏ màu cam $\leftrightarrow$ món cơm trắng ngà $\leftrightarrow$ món kho màu nâu sẫm).

---

### 2. Bộ đặc trưng Kết cấu bề mặt (Texture Features - 179 chiều)

Đặc trưng kết cấu giúp phân biệt các món ăn có gam màu tương đồng nhưng cấu tạo bề mặt vật lý khác nhau.

#### a. Các chiều của bộ đặc trưng
* **Uniform Local Binary Pattern - LBP (10 chiều):**
  * **8 chiều Mẫu đồng nhất (Uniform Patterns):** Đại diện cho các mẫu vi cấu trúc cơ bản gồm điểm phẳng, cạnh vi mô, góc nhọn và đốm sáng/tối cục bộ.
  * **2 chiều Mẫu không đồng nhất:** Đại diện cho toàn bộ các dạng chuyển tiếp mức xám phức tạp, hỗn loạn còn lại.
* **Edge Orientation Histogram - EOH (9 chiều):**
  * **9 chiều tương ứng với 9 bin góc hướng cạnh:** Mỗi chiều đại diện cho một dải góc $20^\circ$ (trải đều từ $0^\circ \div 180^\circ$).
* **GLCM Haralick - Ma trận đồng xuất hiện mức xám (16 chiều):** Đo lường 4 chỉ số thống kê trên 4 hướng không gian ($0^\circ, 45^\circ, 90^\circ, 135^\circ$):
  * **4 chiều Năng lượng (Energy):** Đo lường độ đồng nhất và tính lặp lại của kết cấu bề mặt.
  * **4 chiều Độ tương phản (Contrast):** Đo lường sự biến thiên mức xám cục bộ (độ sâu của các rãnh, nếp nhăn giữa các nguyên liệu).
  * **4 chiều Độ thuần nhất (Homogeneity):** Thể hiện độ trơn phẳng, liền mạch của bề mặt thực phẩm.
  * **4 chiều Hệ số tương quan (Correlation):** Đo lường tính liên kết tuyến tính và hướng kéo dài của các vân mức xám.
* **Gabor Filter Bank (80 chiều):** Kết hợp 5 dải tần số với 8 góc xoay hướng:
  * **40 chiều Giá trị trung bình ($\mu$):** Thể hiện năng lượng phản hồi trung bình của các đường vân theo từng kích cỡ và phương hướng.
  * **40 chiều Độ lệch chuẩn ($\sigma$):** Thể hiện mức độ biến động và độ dày đặc của các vân cấu trúc tương ứng.
* **2D Stripe-FFT (64 chiều):**
  * **64 chiều Vòng tròn năng lượng đồng tâm (Radial Rings):** Quét từ vùng tần số thấp (vùng trung tâm) lan dần ra tần số cao (vùng ngoại vi).

#### b. Ý nghĩa của các chiều
* Mã hóa các chi tiết vi cấu trúc bề mặt điểm ảnh, bất biến với sự thay đổi độ sáng đơn điệu.
* Thể hiện mật độ và phương hướng chủ đạo của các đường viền và nếp gấp vi mô.
* Định lượng độ thô ráp tổng thể, phân biệt món ăn có cấu trúc phức tạp nhiều tầng với món có bề mặt đồng nhất.
* Bắt trọn hoa văn bề mặt ở nhiều tỉ lệ và hướng khác nhau, nắm bắt tính chất chu kỳ của các thớ thịt hay hạt rải trên đĩa ăn.

#### c. Tác dụng trong xác định điểm giống và khác nhau
* **Xác định điểm GIỐNG NHAU:** Nhận diện độ thô ráp đồng chất giữa các đĩa cùng một món (ví dụ: cùng độ sánh mịn của cháo, cùng độ xốp giòn của bánh mì, cùng độ gồ ghề của da gà rán).
* **Xác định điểm KHÁC NHAU:** Là **chìa khóa quyết định** để phân biệt các món ăn trùng màu sắc nhưng khác trạng thái bề mặt vật lý (ví dụ: *Cơm chiên* có kết cấu hạt thô rời rạc $\leftrightarrow$ *Súp bí đỏ* dạng lỏng trơn nhẵn; *Phở bò* sợi dẹp $\leftrightarrow$ *Bún bò* sợi tròn).

---

### 3. Bộ đặc trưng Hình dạng & Đường biên (Shape Features - 527 chiều)

Trích xuất trên vùng tiền cảnh món ăn nhằm ghi nhận cấu trúc hình học, tỷ lệ lấp đầy lòng đĩa và các đường viền bao ngoài.

#### a. Các chiều của bộ đặc trưng
* **Hu Moments & Đại lượng vô hướng hình học (11 chiều):**
  * **7 chiều Mô-men bất biến Hu:** Đại diện cho hình thái bao quát của khối thức ăn, bất biến với phép tịnh tiến, co giãn và quay hình học.
  * **1 chiều Tỷ lệ diện tích (Area Ratio):** Tỷ lệ diện tích phần thức ăn so với toàn bộ diện tích khung hình.
  * **1 chiều Chu vi chuẩn hóa (Perimeter Norm):** Chiều dài đường bao quanh phần thức ăn.
  * **1 chiều Độ nén (Compactness):** Mức độ co cụm, đặc khít về tâm của khối thức ăn.
  * **1 chiều Độ tròn (Circularity):** Mức độ tiệm cận hình tròn hoàn hảo của vùng thức ăn.
* **Grid Mask Density (64 chiều):**
  * **64 chiều Mật độ ô lưới:** Vùng tiền cảnh món ăn được chia thành lưới $8 \times 8 = 64$ ô vuông nhỏ; mỗi chiều ghi nhận tỷ lệ phần trăm diện tích món ăn chiếm trong từng ô.
* **Width Profile & Contour Profile (64 chiều):**
  * **32 chiều Width Profile:** Đo bề rộng ngang của món ăn tại 32 lát cắt dọc phân bố đều từ đỉnh xuống đáy.
  * **32 chiều Contour Profile:** Đo chiều cao dọc của món ăn tại 32 lát cắt ngang phân bố đều từ trái sang phải.
* **Radius Signature (64 chiều):**
  * **64 chiều Bán kính biên:** Ghi nhận khoảng cách từ trọng tâm hình học đến các điểm trên đường viền ngoài tại 64 góc quét đều nhau.
* **HOG trên vùng món ăn - ROI (324 chiều):**
  * Vùng món ăn chuẩn hóa được chia thành 9 khối ($3 \times 3$ blocks), mỗi khối gồm 4 ô ($2 \times 2$ cells), mỗi ô thu thập 9 hướng gradient ($9 \text{ khối} \times 4 \text{ ô} \times 9 \text{ hướng} = \mathbf{324}$ chiều).

#### b. Ý nghĩa của các chiều
* Xác định độ đầy đặn trong lòng đĩa và tính chất đối xứng tròn của món ăn bên trong đĩa/bát.
* Thể hiện sự phân bố khối lượng món ăn trong không gian đĩa; phát hiện món trải phẳng hay vun cao ở tâm đĩa.
* Ghi lại biên dạng bao ngoài theo cả hai chiều ngang và dọc, phản ánh tính đối xứng, độ bè ra hoặc độ thon gọn của món ăn.
* Bắt cấu trúc hình học và biên dạng vi mô nội tại bên trong khối thức ăn.

#### c. Tác dụng trong xác định điểm giống và khác nhau
* **Xác định điểm GIỐNG NHAU:** Nhận diện tính chất đối xứng tâm tròn của đĩa thức ăn và tỷ lệ lấp đầy lòng đĩa đặc trưng của cùng một món.
* **Xác định điểm KHÁC NHAU:** Nhận diện sự khác biệt về hình thái sắp xếp thành phần bên trong (món dạng khối to bản vs món dạng sợi mảnh, món vụn hạt) và đường viền bao ngoài (viền lá rau lượn sóng vs đường cong tròn trơn nhẵn của bánh flan, súp).

---

### 4. Bộ đặc trưng Bố cục không gian (Spatial Layout Features - 544 chiều)

Khắc phục hoàn toàn nhược điểm **mất thông tin vị trí không gian** của các bộ trích xuất toàn cục.

#### a. Các chiều của bộ đặc trưng
* Ảnh được phân chia đều thành lưới không gian $4 \times 4 = 16$ ô khối cục bộ (mỗi ô có kích thước $56 \times 56$ px).
* Tại mỗi ô trong 16 ô, trích xuất đồng thời 34 chiều:
  * **24 chiều HSV cục bộ:** 8 chiều cho kênh $H$, 8 chiều cho kênh $S$, 8 chiều cho kênh $V$ (ghi nhận màu sắc riêng biệt của từng ô).
  * **10 chiều Uniform LBP cục bộ:** 10 mẫu kết cấu vi mô bên trong ô đó.
* Nối tuần tự 16 ô: $16 \text{ ô} \times 34 \text{ chiều/ô} = \mathbf{544}$ **chiều**.

#### b. Ý nghĩa của các chiều
* Cung cấp thông tin chính xác về vị trí của từng thành phần nguyên liệu trên đĩa ăn.
* Gắn kết mối quan hệ tương hỗ giữa màu sắc và kết cấu vi mô tại từng khu vực tọa độ cụ thể.

#### c. Tác dụng trong xác định điểm giống và khác nhau
* **Xác định điểm GIỐNG NHAU:** Ghi nhận tính ổn định trong bố cục trình bày truyền thống của món ăn giữa các đĩa khác nhau (ví dụ: món *Cơm tấm* luôn có nửa trên là sườn nướng, nửa dưới là cơm trắng).
* **Xác định điểm KHÁC NHAU:** Phân biệt cực kỳ hiệu quả các món ăn **có cùng tập nguyên liệu nhưng khác nhau về cách bài trí** (ví dụ: món *Bún đậu mắm tôm* bày theo từng góc riêng biệt: bún lá trắng góc trái, đậu chiên vàng góc phải, mắm tôm ở giữa $\leftrightarrow$ khác biệt hoàn toàn với món bún riêu trộn lẫn mọi thành phần; hoặc *Gỏi cuốn* xếp cuốn riêng $\leftrightarrow$ *Gỏi nộm* trộn đều hỗn hợp).

---

## 2.3. Bảng tổng hợp đối sánh Giá trị thông tin của các đặc trưng

Bảng dưới đây tổng hợp vai trò của từng bộ đặc trưng đối với hai mục tiêu cốt lõi: **Xác định điểm giống nhau** (Intra-class similarity) và **Xác định điểm khác nhau** (Inter-class dissimilarity):

| Bộ đặc trưng | Số chiều | Tác dụng xác định ĐIỂM GIỐNG NHAU (Similarity) | Tác dụng xác định ĐIỂM KHÁC NHAU (Dissimilarity) | Giá trị thông tin tổng quát |
|:---|:---:|:---|:---|:---:|
| **Color (HSV + Lab + Moments)** | 210 | Nhận diện các ảnh có chung gam màu món ăn (ví dụ: cùng sắc đỏ cà chua, cùng màu xanh canh rau). | Phân biệt rõ các món ăn thuộc các trường phái màu sắc khác nhau (canh rau $\leftrightarrow$ súp bí đỏ). | **Rất cao** *(Tầng lọc đầu tiên)* |
| **Texture (LBP + GLCM + Gabor + FFT)** | 179 | Nhận diện độ thô ráp đồng chất giữa các đĩa cùng một món (độ nhuyễn của cháo, độ mịn của súp). | **Chìa khóa phân biệt** các món ăn trùng màu sắc nhưng khác trạng thái bề mặt (cơm chiên vàng vs súp bí đỏ vàng). | **Xuất sắc** *(Tránh nhầm lẫn màu)* |
| **Shape (Hu + Mask + Profile + HOG)** | 527 | Nhận diện tính chất đối xứng tâm tròn của đĩa thức ăn và tỷ lệ lấp đầy lòng đĩa. | Phân biệt hình thái sắp đặt nguyên liệu bên trong (món dạng khối to bản vs món dạng sợi mảnh, món vụn). | **Rất cao** *(Xác định cấu trúc)* |
| **Spatial Layout (Grid 4x4)** | 544 | Ghi nhận tính ổn định trong bố cục trình bày của món ăn (cơm luôn ở góc này, thức ăn ở góc kia). | Tách biệt các món có cùng nguyên liệu nhưng cách bài trí khác nhau (bún đậu phân vùng vs bún riêu trộn lẫn). | **Rất cao** *(Khắc phục mất vị trí)* |
| **TỔNG CỘNG** | **1.460** | **Bắt trọn sự đồng nhất về màu sắc, bề mặt, cấu trúc và vị trí bài trí.** | **Nhạy bén phát hiện sai khác vi mô, trạng thái vật lý và bố cục sắp đặt.** | **Bộ thuộc tính toàn diện** |

---

> **Kết luận:** Hệ thuộc tính 1.460 chiều đã tạo nên một bộ mô tả thị giác toàn diện, đáp ứng hoàn hảo hai tiêu chí: **bắt trọn sự tương đồng** giữa các ảnh cùng một món ăn và **nhạy bén phát hiện sự khác biệt** giữa các món ăn khác nhau, làm tiền đề vững chắc cho cơ sở dữ liệu đa phương tiện CBIR hoạt động chính xác và hiệu quả.