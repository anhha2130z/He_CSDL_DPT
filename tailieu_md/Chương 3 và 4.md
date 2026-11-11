# BÁO CÁO MÔN HỌC: CƠ SỞ DỮ LIỆU ĐA PHƯƠNG TIỆN
# CHƯƠNG 3 VÀ CHƯƠNG 4: TRÍCH XUẤT ĐẶC TRƯNG VÀ TÌM KIẾM ẢNH MÓN ĂN TƯƠNG ĐỒNG

---

# CHƯƠNG 3: TRIỂN KHAI TRÍCH XUẤT ĐẶC TRƯNG VÀ XÂY DỰNG CƠ SỞ DỮ LIỆU

## 3.1. Mục tiêu

Ở Chương 2, các đặc trưng thị giác dùng để mô tả ảnh món ăn đã được xác định. Chương này trình bày cách áp dụng các đặc trưng đó để biến mỗi ảnh thành dữ liệu số, đồng thời tổ chức lưu trữ dữ liệu để phục vụ tìm kiếm.

Mỗi ảnh được biểu diễn bằng một **vector đặc trưng**. Vector chứa thông tin về màu sắc, kết cấu, hình dạng và bố cục của ảnh. Khi có ảnh mới, hệ thống cũng tạo vector theo cùng quy trình để so sánh với các vector đã lưu.

Quá trình xử lý gồm hai phần:

1. **Xử lý bộ dữ liệu ban đầu:** chuẩn hóa ảnh, trích xuất đặc trưng, giảm chiều vector và xây dựng chỉ mục tìm kiếm.
2. **Xử lý khi tìm kiếm:** áp dụng cùng cách chuẩn hóa và trích xuất cho ảnh người dùng gửi lên, sau đó đưa vector vào không gian đặc trưng đã xây dựng để so sánh.

Quy trình tổng quát:

```text
Ảnh món ăn
    ↓
Chuẩn hóa kích thước, giữ nguyên tỷ lệ
    ↓
Tạo mặt nạ vùng tiền cảnh
    ↓
Trích xuất đặc trưng màu sắc, kết cấu, hình dạng và bố cục
    ↓
Ghép thành vector đặc trưng và giảm số chiều
    ↓
Lưu thông tin ảnh, vector và chỉ mục tìm kiếm
```

## 3.2. Chuẩn hóa ảnh và tạo mặt nạ

### 3.2.1. Chuẩn hóa kích thước, không làm méo ảnh

Ảnh thu thập có thể có chiều rộng và chiều cao khác nhau. Nếu kéo ảnh về hình vuông bằng cách thay đổi riêng chiều rộng hoặc chiều cao, món ăn sẽ bị méo và hình dạng của nó không còn đúng với ảnh ban đầu.

Để tránh điều này, ảnh được đặt vào giữa một khung vuông có cạnh bằng chiều dài lớn hơn của ảnh. Phần khung còn thiếu được bù thêm bằng màu lấy từ vùng viền ảnh. Nhờ vậy, nội dung ảnh giữ được tỷ lệ ban đầu và tất cả ảnh có thể được xử lý trong một khung thống nhất.

Ảnh được chuẩn hóa về kích thước 512 × 512 pixel để lưu trữ. Trước khi tính đặc trưng, ảnh được đưa về 224 × 224 pixel. Hai kích thước này phục vụ hai mục đích khác nhau: 512 × 512 dùng để lưu ảnh đã chuẩn hóa, còn 224 × 224 là kích thước xử lý đặc trưng nhằm giảm thời gian và khối lượng tính toán. Ảnh bộ dữ liệu và ảnh truy vấn đều được đưa về cùng kích thước xử lý.

### 3.2.2. Tạo mặt nạ vùng tiền cảnh

Ảnh món ăn thường có cả món ăn, đĩa hoặc bát và phần nền xung quanh. Nếu tính đặc trưng trên toàn bộ ảnh, nền có thể ảnh hưởng đến kết quả so sánh. Vì vậy, hệ thống tạo **mặt nạ** để đánh dấu vùng được xem là tiền cảnh, rồi ưu tiên sử dụng vùng đó khi tính các đặc trưng.

Phương pháp phân đoạn được sử dụng là GrabCut. Kết quả phân đoạn được làm sạch bằng các phép xử lý hình thái học để giảm nhiễu nhỏ và làm liền các vùng gần nhau. Khi GrabCut không tạo được mặt nạ phù hợp, hệ thống thử một phương pháp ngưỡng dự phòng. Nếu vẫn không xác định được vùng hợp lệ, ảnh được xem là lỗi xử lý thay vì coi toàn bộ ảnh là món ăn.

Mặt nạ có tác dụng giảm ảnh hưởng của nền, nhưng không đồng nghĩa với việc món ăn luôn được tách chính xác. Nếu màu nền gần giống món ăn hoặc ảnh có nhiều vật thể, mặt nạ có thể nhận nhầm một phần nền hoặc bỏ sót một phần món ăn. Hệ thống dùng mặt nạ để chọn vùng tính toán đặc trưng, không xóa nền rồi ghép món ăn lên nền trắng.

## 3.3. Trích xuất đặc trưng

Hệ thống trích xuất bốn nhóm đặc trưng đã xác định ở Chương 2. Mỗi nhóm mô tả một khía cạnh khác nhau của ảnh.

| Nhóm đặc trưng | Số chiều | Nội dung được mô tả |
|---|---:|---|
| Màu sắc | 210 | Phân bố màu và các thống kê màu của món ăn |
| Kết cấu | 179 | Bề mặt trơn, thô, dạng sợi, dạng hạt và hướng cạnh |
| Hình dạng | 527 | Đường biên, tỷ lệ, độ đầy và hình thái vùng tiền cảnh |
| Bố cục không gian | 544 | Vị trí phân bố màu và kết cấu trong từng vùng ảnh |
| **Tổng cộng** | **1.460** | Vector mô tả tổng hợp của ảnh |

### 3.3.1. Đặc trưng màu sắc

Đặc trưng màu sắc mô tả những màu xuất hiện trong ảnh và mức độ phân bố của chúng. Hệ thống sử dụng biểu đồ màu trong hai không gian HSV và CIE-Lab, đồng thời tính thêm các thống kê như giá trị trung bình, độ phân tán và độ lệch của màu.

Nhóm đặc trưng này giúp nhận biết các ảnh có tông màu gần nhau, chẳng hạn món có sắc đỏ cam của cà chua, màu xanh của rau hoặc sắc vàng nâu của món chiên. Màu sắc hữu ích để tìm những ảnh có diện mạo gần nhau, nhưng riêng màu sắc chưa đủ để phân biệt các món có màu tương tự.

### 3.3.2. Đặc trưng kết cấu

Đặc trưng kết cấu mô tả cách các chi tiết nhỏ phân bố trên bề mặt. Hệ thống kết hợp nhiều cách đo: mẫu sáng tối cục bộ, hướng cạnh, độ tương phản và độ đồng nhất, cũng như phản hồi của các bộ lọc ở nhiều hướng và tần số.

Nhờ nhóm này, hệ thống có thêm thông tin để phân biệt các món có màu gần giống nhưng bề mặt khác nhau. Ví dụ, cơm rang có nhiều hạt và cạnh nhỏ, trong khi súp thường có bề mặt mịn hơn. Kết cấu cũng có thể hỗ trợ phân biệt các món dạng sợi với món dạng hạt hoặc dạng khối.

### 3.3.3. Đặc trưng hình dạng

Đặc trưng hình dạng được tính dựa trên mặt nạ và vùng món ăn. Các giá trị mô tả gồm đặc điểm đường biên, diện tích tương đối, mức độ tròn hoặc gọn, mật độ tiền cảnh trong các ô lưới, biên dạng theo chiều ngang và chiều dọc, khoảng cách từ tâm đến đường biên, cùng hướng cạnh bên trong vùng món ăn.

Nhóm này biểu diễn hình dạng tổng thể và cách vùng tiền cảnh chiếm chỗ trong khung hình. Tuy nhiên, do ảnh món ăn thường có đĩa, bát và cách trình bày khác nhau, đặc trưng hình dạng không phải lúc nào cũng tương ứng trực tiếp với hình dáng riêng của món ăn. Chất lượng của nó cũng phụ thuộc vào độ chính xác của mặt nạ.

### 3.3.4. Đặc trưng bố cục không gian

Một biểu đồ màu tính trên toàn ảnh chỉ cho biết ảnh có những màu nào, nhưng không cho biết chúng nằm ở đâu. Để giữ lại thông tin vị trí, ảnh được chia thành lưới 4 × 4. Trong mỗi ô, hệ thống mô tả màu sắc và kết cấu cục bộ, rồi ghép thông tin của 16 ô thành vector bố cục.

Đặc trưng này hữu ích khi cách sắp xếp thành phần có ý nghĩa. Chẳng hạn, một đĩa thức ăn có thể có phần cơm ở một phía và thức ăn ở phía còn lại. Hai ảnh có thành phần tương tự nhưng bố trí khác nhau có thể được phân biệt tốt hơn nhờ thông tin không gian.

## 3.4. Ghép vector và giảm chiều

Bốn nhóm đặc trưng được nối theo một thứ tự cố định để tạo thành vector 1.460 chiều. Trước khi lưu, hệ thống chuẩn hóa vector để giảm ảnh hưởng của độ lớn tổng thể và thay các giá trị không hợp lệ bằng giá trị an toàn.

Vector 1.460 chiều chứa nhiều thông tin, nhưng việc lưu trữ và so sánh số chiều lớn cần nhiều tài nguyên hơn. Hệ thống sử dụng **PCA** để giảm chiều, tức là chuyển vector sang một không gian nhỏ hơn nhưng cố gắng giữ lại phần biến thiên quan trọng của dữ liệu.

Trong lần xây dựng bộ dữ liệu hiện tại, vector được giảm xuống 512 chiều. PCA được xây dựng từ các ảnh trong bộ dữ liệu và được dùng lại cho mọi ảnh truy vấn. Việc dùng chung một phép biến đổi giúp vector mới có thể so sánh trực tiếp với vector cũ. Nếu huấn luyện lại PCA hoặc thay đổi cách trích đặc trưng, cần tạo lại vector và chỉ mục cho toàn bộ ảnh.

Sau khi giảm chiều, vector được chuẩn hóa độ dài trước khi đưa vào tìm kiếm. Việc chuẩn hóa này cho phép dùng tích vô hướng để tính độ tương đồng cosine giữa hai vector.

## 3.5. Tổ chức cơ sở dữ liệu và chỉ mục

Hệ thống sử dụng cách lưu trữ kết hợp, trong đó mỗi thành phần đảm nhiệm một vai trò:

| Thành phần | Thông tin lưu trữ và vai trò |
|---|---|
| Cơ sở dữ liệu quan hệ | Mã định danh và đường dẫn của từng ảnh |
| Ma trận vector thô | Vector đặc trưng 1.460 chiều trước khi giảm chiều |
| Ma trận vector sau PCA | Vector đã giảm chiều, dùng cho việc so sánh |
| Chỉ mục tìm kiếm | Hỗ trợ lấy các vector gần với vector truy vấn |
| Bảng kê và thông tin kiểm tra | Ghi nhận số lượng, thứ tự ảnh và tính toàn vẹn dữ liệu |

Thông tin ảnh và vector được lưu riêng để phù hợp với từng loại dữ liệu. Cơ sở dữ liệu quan hệ giúp quản lý ảnh và đường dẫn; ma trận số phù hợp để xử lý vector; chỉ mục hỗ trợ tìm kiếm. Các thành phần phải giữ cùng thứ tự ảnh để hệ thống luôn ghép đúng vector với ảnh tương ứng.

Chỉ mục hiện tại so sánh chính xác vector truy vấn với các vector đã lưu. Cách làm này phù hợp với quy mô bộ dữ liệu của đồ án và không bỏ qua ứng viên bằng phương pháp xấp xỉ. Khi số lượng ảnh tăng, thời gian so sánh cũng có thể tăng.

## 3.6. Bổ sung ảnh mới vào bộ dữ liệu

Ảnh do người dùng tải lên được chuẩn hóa và lưu lại. Hệ thống dùng nội dung ảnh đã chuẩn hóa để nhận biết ảnh trùng; nếu ảnh đã có trong dữ liệu thì không tạo thêm một bản ghi mới.

Với ảnh mới, hệ thống thực hiện các bước sau:

1. Tạo mặt nạ và trích xuất vector thô theo cùng quy trình với ảnh trong bộ dữ liệu.
2. Dùng PCA hiện có để chuyển vector về đúng số chiều và không gian đang sử dụng.
3. Bổ sung thông tin ảnh và vector vào các thành phần lưu trữ tương ứng.
4. Cập nhật chỉ mục để ảnh mới có thể tham gia những lần tìm kiếm tiếp theo.

Việc cập nhật được thực hiện đồng bộ để hạn chế tình trạng ảnh đã được ghi nhận nhưng vector chưa được lưu, hoặc vector không còn liên kết đúng với ảnh. Nếu cần thay đổi bộ trích xuất hoặc mô hình PCA, cần xây dựng lại toàn bộ chỉ mục thay vì kết hợp dữ liệu được tạo theo các cấu hình khác nhau.

## 3.7. Kết luận chương

Chương này đã trình bày cách giữ nguyên tỷ lệ ảnh khi chuẩn hóa, tạo mặt nạ tiền cảnh, trích xuất bốn nhóm đặc trưng và tổ chức lưu trữ vector. Mỗi ảnh được chuyển thành một biểu diễn số thống nhất, có thể so sánh với ảnh khác. Đây là cơ sở để triển khai tìm kiếm ảnh tương đồng trong Chương 4.

---

# CHƯƠNG 4: TRIỂN KHAI VÀ ĐÁNH GIÁ HỆ THỐNG TÌM KIẾM ẢNH TƯƠNG ĐỒNG

## 4.1. Mục tiêu và đầu vào, đầu ra

Chức năng tìm kiếm nhận đầu vào là một ảnh món ăn mới và trả về tối đa 5 ảnh gần nhất trong bộ dữ liệu, được sắp xếp từ tương đồng cao đến thấp. Hệ thống tìm ảnh dựa trên nội dung thị giác; nó không phải là mô hình phân loại có nhiệm vụ khẳng định tên món ăn.

Thông tin kết quả gồm ảnh được tìm thấy, thứ hạng và điểm tương đồng. Người dùng có thể dựa vào các ảnh này để tham khảo những món có diện mạo gần với ảnh truy vấn.

## 4.2. Quy trình xử lý một truy vấn

### Bước 1: Nhận ảnh

Người dùng chọn ảnh món ăn cần tìm. Hệ thống kiểm tra ảnh có thể đọc được và có kích thước phù hợp trước khi xử lý. Những tệp không hợp lệ được báo lỗi thay vì tiếp tục tạo kết quả không đáng tin cậy.

### Bước 2: Chuẩn hóa ảnh và tạo mặt nạ

Ảnh được xoay theo thông tin hướng lưu trong ảnh nếu có, chuyển về dạng màu phù hợp và thêm phần đệm để tạo khung vuông. Hệ thống không kéo giãn nội dung ảnh. Ảnh sau chuẩn hóa được lưu ở kích thước 512 × 512; sau đó được đưa về 224 × 224 để tạo mặt nạ và tính đặc trưng.

### Bước 3: Trích xuất vector truy vấn

Hệ thống tạo mặt nạ tiền cảnh và tính các nhóm đặc trưng màu sắc, kết cấu, hình dạng và bố cục. Các nhóm được ghép thành vector 1.460 chiều, chuẩn hóa và chuyển qua mô hình PCA đã xây dựng trước đó.

Vector sau PCA được chuẩn hóa theo cùng cách với các vector trong bộ dữ liệu. Bước này bảo đảm hai bên có cùng số chiều và có thể so sánh trực tiếp.

### Bước 4: Lưu ảnh mới

Ảnh truy vấn được lưu để có thể sử dụng về sau. Nếu ảnh chưa có trong chỉ mục, hệ thống bổ sung ảnh và vector của nó vào dữ liệu tìm kiếm. Nếu ảnh đã tồn tại, hệ thống không thêm một bản ghi trùng.

### Bước 5: Tìm và xếp hạng kết quả

Vector truy vấn được so sánh với vector của các ảnh trong chỉ mục. Những ảnh có điểm tương đồng cao hơn được xếp trước. Hệ thống lấy tối đa 5 kết quả hợp lệ để trả về.

Nếu ảnh truy vấn vừa được thêm vào chỉ mục, chính ảnh đó sẽ bị loại khỏi danh sách kết quả của lần tìm kiếm hiện tại. Điều này tránh việc kết quả đầu tiên chỉ là bản thân ảnh vừa gửi lên.

### Bước 6: Hiển thị kết quả

Giao diện hiển thị danh sách ảnh theo thứ tự giảm dần của điểm tương đồng. Để biểu diễn trực quan, điểm cosine được quy đổi tuyến tính từ khoảng $[-1,1]$ sang thang $[0,100]\%$:

$$
\text{Phần trăm hiển thị}
= \frac{\text{điểm cosine}+1}{2}\times 100\%.
$$

Đây là thang điểm quy đổi để so sánh và xếp hạng, không phải xác suất, độ chính xác hay tỷ lệ phần trăm hai ảnh chắc chắn cùng món.

## 4.3. Độ tương đồng cosine

Để so sánh ảnh truy vấn với một ảnh trong bộ dữ liệu, hệ thống sử dụng độ tương đồng cosine giữa hai vector đặc trưng:

$$
\operatorname{sim}(\mathbf{q},\mathbf{x})
=
\frac{\mathbf{q}\cdot\mathbf{x}}
{\|\mathbf{q}\|_2\,\|\mathbf{x}\|_2},
$$

trong đó:

- $\mathbf{q}$ là vector đặc trưng của ảnh truy vấn;
- $\mathbf{x}$ là vector đặc trưng của một ảnh trong bộ dữ liệu;
- $\mathbf{q}\cdot\mathbf{x}$ là tích vô hướng của hai vector;
- $\|\mathbf{q}\|_2$ và $\|\mathbf{x}\|_2$ là độ dài của từng vector.

Điểm càng cao thì hướng của hai vector càng gần nhau, nghĩa là các đặc trưng mà hệ thống đo được có mức tương đồng cao hơn. Các kết quả được sắp xếp theo điểm giảm dần.

Trong hệ thống, vector được chuẩn hóa trước khi so sánh. Khi hai vector có độ dài bằng 1, phép tính cosine tương đương với tích vô hướng. Hệ thống có thể biểu diễn khoảng cách cosine bằng:

$$
\operatorname{distance}=1-\operatorname{sim}.
$$

Điểm cosine chỉ phản ánh độ gần nhau theo bộ đặc trưng đã thiết kế. Điểm này không phải xác suất, không phải phần trăm ảnh đúng và không bảo đảm hai ảnh có cùng tên món ăn.

## 4.4. Quy mô dữ liệu và kết quả triển khai

Ở lần xây dựng bộ dữ liệu được ghi nhận, hệ thống có **564 ảnh thuộc 110 danh mục**. Mỗi ảnh được mô tả bằng vector thô 1.460 chiều và vector sau PCA 512 chiều. Đây là số liệu của lần xây dựng hiện tại; số lượng ảnh có thể thay đổi khi bộ dữ liệu được bổ sung.

Quy trình đã triển khai được từ ảnh truy vấn đến danh sách tối đa 5 ảnh gần nhất. Ảnh mới có thể được lưu và thêm vào dữ liệu tìm kiếm; ảnh trùng được hạn chế tạo bản ghi lặp; ảnh truy vấn không được trả lại như một kết quả của chính nó.

Các kiểm thử chức năng được thực hiện nhằm xác nhận những luồng chính như giữ tỷ lệ ảnh, lưu ảnh mới, cập nhật vector, phát hiện ảnh trùng, loại ảnh tự khớp và bảo vệ tính nhất quán khi cập nhật dữ liệu gặp lỗi. Những kiểm thử này xác nhận hệ thống hoạt động theo thiết kế, nhưng không phải phép đo độ chính xác tìm kiếm.

## 4.5. Đánh giá chất lượng tìm kiếm

Để biết kết quả Top 5 có thực sự phù hợp hay không, cần có một tập ảnh truy vấn và nhãn xác định trước những ảnh nào được xem là liên quan. Khi đó có thể đếm số ảnh liên quan xuất hiện trong 5 kết quả đầu tiên.

Một chỉ số đơn giản là **Precision@5**:

$$
\operatorname{Precision@5}
=
\frac{\text{số ảnh liên quan trong 5 kết quả đầu}}
{5}.
$$

Ví dụ, nếu có 3 ảnh liên quan trong 5 kết quả thì Precision@5 bằng $3/5=0{,}6$. Cần sử dụng cùng một quy tắc xác định ảnh liên quan cho tất cả truy vấn để kết quả đánh giá có ý nghĩa.

Hiện chưa có bộ truy vấn độc lập kèm nhãn liên quan được xác nhận để tính Precision@5 hoặc các chỉ số tương tự. Vì vậy, chưa thể đưa ra một con số độ chính xác tổng quát cho hệ thống. Các ảnh kết quả có thể được xem trực quan để minh họa, nhưng không thay thế đánh giá định lượng trên tập có nhãn.

Khi tiến hành đánh giá, nên chọn truy vấn không dùng để xây dựng hoặc điều chỉnh các tham số của hệ thống. Đồng thời, cần loại chính ảnh truy vấn khỏi danh sách kết quả để tránh làm tăng giả tạo số ảnh được xem là đúng.

## 4.6. Các yếu tố ảnh hưởng đến kết quả

Một số yếu tố có thể làm thay đổi thứ tự ảnh được tìm thấy:

- **Độ chính xác của mặt nạ:** Nếu mặt nạ lấy nhầm nền hoặc bỏ sót món ăn, các đặc trưng tính ra sẽ không phản ánh đúng nội dung cần tìm.
- **Điều kiện chụp ảnh:** Ánh sáng, màu nền, góc chụp, cách trình bày và kích thước món ăn có thể khác nhau giữa ảnh truy vấn và ảnh trong bộ dữ liệu.
- **Sự giống nhau giữa các món:** Hai món khác tên vẫn có thể có màu sắc hoặc kết cấu tương tự; ngược lại, cùng một món có thể được trình bày rất khác nhau.
- **Cách kết hợp đặc trưng:** Vector tổng hợp nhiều nhóm đặc trưng. Mỗi nhóm có thể đóng góp khác nhau vào kết quả; cần có đánh giá trên dữ liệu có nhãn nếu muốn điều chỉnh mức ảnh hưởng.
- **Quy mô bộ dữ liệu:** Kết quả chỉ có thể chọn trong những ảnh đã được đưa vào chỉ mục. Nếu món cần tìm chưa có ảnh đại diện phù hợp, hệ thống không thể bảo đảm trả về ảnh đúng món.

Ngoài chất lượng tìm kiếm, thời gian phản hồi cũng phụ thuộc vào kích thước ảnh, quá trình tạo mặt nạ và số lượng vector cần so sánh. Chưa có phép đo hiệu năng lặp lại trên nhiều cấu hình phần cứng, vì vậy không đưa ra cam kết cụ thể về thời gian xử lý.

## 4.7. Kết luận chương

Chương này đã trình bày quy trình tìm kiếm từ lúc nhận ảnh mới, chuẩn hóa và trích xuất vector đến khi so sánh, xếp hạng và trả về tối đa 5 ảnh. Phép so sánh cosine được dùng để sắp xếp các ảnh theo mức gần nhau của vector đặc trưng.

Hệ thống đã triển khai được các chức năng chính của một hệ tìm kiếm ảnh dựa trên nội dung. Tuy nhiên, điểm tương đồng không đồng nghĩa với độ chính xác phân loại. Muốn kết luận khách quan về chất lượng Top 5, cần xây dựng tập truy vấn có nhãn và thực hiện đánh giá định lượng.
