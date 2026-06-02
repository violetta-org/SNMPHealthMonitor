# SNMP vs Modern Monitoring & Vai Trò Của SNMP Hiện Nay

Tài liệu này tổng hợp lại các so sánh giữa SNMP với các phương pháp giám sát hiện đại (Streaming Telemetry, Agent) và lý do tại sao SNMP vẫn phổ biến.

## 1. Tại Sao Chuyển Sang Streaming Telemetry & Agent?

SNMP truyền thống gặp dặc điểm là hoạt động theo cơ chế **Pull (Hỏi - Đáp)**, gây ra nhiều hạn chế trong giám sát hiện đại.

### Các Hạn Chế Của SNMP Trong Giám Sát Real-time
*   **Polling Overhead:** Server phải liên tục gửi request (`GET`) để lấy dữ liệu. Nếu tần suất lấy mẫu cao (sub-minute), việc này tạo gánh nặng lớn lên CPU thiết bị.
*   **Độ Trễ:** Do phải chờ đến lượt "hỏi", dữ liệu không thực sự là real-time.

### Giải Pháp Thay Thế: Agent & Streaming Telemetry

| Phương Pháp | Cơ Chế | Ưu Điểm Chính | Ứng Dụng |
| :--- | :--- | :--- | :--- |
| **Local Agent**<br>(Node Exporter, Telegraf) | **Local Execution**: Chạy trực tiếp trên máy, đọc file hệ thống.<br>**Push/Pull tối ưu**: Gom data thành batch lớn. | Hiệu năng cao, chi tiết sâu (OS metrics), ít tốn băng thông hỏi đáp lắt nhắt. | Server Linux/Windows, Database, Kubernetes. |
| **Streaming Telemetry**<br>(Model Driven Telemetry) | **Push (Pub/Sub)**: Server đăng ký 1 lần, thiết bị tự động đẩy luồng dữ liệu (stream) khi có cập nhật. | **Real-time** thực sự. Dữ liệu được đẩy ngay khi thay đổi. Không tốn CPU xử lý polling. | Thiết bị mạng Core (Router/Switch Cisco, Juniper), ISP. |

---

## 2. Vậy SNMP Để Làm Gì? Tại Sao Vẫn Tồn Tại?

Mặc dù thua kém về hiệu năng realtime, SNMP vẫn là tiêu chuẩn không thể thay thế nhờ **tính phổ quát**.

### 1. "Tiếng Anh" Chung Của Thế Giới Mạng
*   **Có sẵn trên mọi thứ:** Gần như mọi thiết bị mạng (Router, Switch, Wifi, Printer, Camera, UPS) khi xuất xưởng đều hỗ trợ SNMP.
*   **Đa dạng:** Một công cụ giám sát dùng SNMP có thể quản lý hàng nghìn loại thiết bị từ các hãng khác nhau mà không cần cài driver riêng hay agent riêng.

### 2. Quản Lý Tài Sản & Khám Phá (Discovery & Inventory)
SNMP rất tốt để trả lời câu hỏi "Anh là ai?":
*   Lấy tên thiết bị, Serial Number, Firmware version.
*   Liệt kê danh sách cổng mạng (Interface list).

### 3. Cảnh Báo Sự Cố (SNMP TRAP)
*   Cơ chế **Trap** cho phép thiết bị chủ động báo về Server ngay khi có lỗi nghiêm trọng (đứt cáp, quá nhiệt) mà không cần chờ Server hỏi.

### 4. Dùng Cho Nhu Cầu Cơ Bản (Vừa & Nhỏ)
*   Với đa số doanh nghiệp, giám sát tần suất **5 phút/lần** là đủ.
*   SNMP rẻ (miễn phí), dễ triển khai, không cần cài Agent phức tạp.

---
*Tóm lại: Dùng **Agent/Streaming** cho dữ liệu sâu, realtime, vẽ biểu đồ mượt. Dùng **SNMP** để quản lý hạ tầng mạng chung, thiết bị đóng (thường) và nhận cảnh báo lỗi.*

---

## 3. Parallel SNMP Polling (Polling Song Song) trong Thực Tế

Trong thực tế, việc Polling song song là tiêu chuẩn để quản lý mạng quy mô lớn một cách hiệu quả.

### Cách Hoạt Động Của Parallel Polling
1.  **Xử lý đồng thời tại NMS:** Các hệ thống quản lý mạng (NMS) hiện đại sử dụng đa luồng (multi-threading) hoặc I/O bất đồng bộ để gửi hàng ngàn yêu cầu SNMP tới nhiều thiết bị cùng lúc. Điều này ngăn việc một thiết bị chậm làm tắc nghẽn cả chu trình polling.
2.  **Gom nhóm yêu cầu (Request Aggregation/PDU Bundling):** Trong một gói tin (PDU), manager có thể yêu cầu nhiều OID cùng lúc. Ví dụ: Lệnh "GetBulk" trong SNMPv2c/v3 có thể kéo cả một bảng dữ liệu interface trong một lần thay vì phải hỏi từng dòng.
3.  **Mở rộng theo chiều ngang (Horizontal Scaling):** Các môi trường lớn thường dùng nhiều máy poller phân tán (proxy agents), chia tải để mỗi server phụ trách polling một nhóm thiết bị cụ thể.

### Hạn Chế Trong Thực Tế
Dù Manager có thể poll song song, thiết bị Agent (như Router đơn lẻ) lại có giới hạn:
*   **Agent đơn luồng:** Nhiều thiết bị cũ hoặc cấu hình thấp xử lý request tuần tự. Gửi quá nhiều request cùng lúc có thể làm tăng độ trễ hoặc treo process quản lý của thiết bị.
*   **Đặc thù phiên bản:** Parallel polling với SNMPv1 rất rủi ro; nếu 1 request trong lô bị lỗi, cả lô thường bị coi là hỏng. SNMPv2c và v3 xử lý việc này tốt hơn (trả về kết quả một phần).
*   **Tràn bộ đệm UDP:** Polling tốc độ quá cao có thể làm tràn bộ đệm UDP của hệ điều hành, dẫn đến mất gói tin.

### Giải Pháp Thực Tiễn
*   **PRTG Network Monitor:** Dùng các sensor tích hợp để tự động hóa parallel polling và xử lý dữ liệu từ nhiều phiên bản SNMP.
*   **Telegraf:** Có thể cấu hình chạy nhiều instance song song để tăng tốc độ MIB walk trên hàng ngàn thiết bị.
*   **UVexplorer:** Sử dụng "Multi-SNMP polling" để thử nhiều thông tin đăng nhập song song trong một phiên khám phá mạng.

---

## 4. Insight từ Kentik: SNMP vs Streaming Telemetry

Theo phân tích từ bài viết [The Benefits and Drawbacks of SNMP and Streaming Telemetry](https://www.kentik.com/blog/the-benefits-and-drawbacks-of-snmp-and-streaming-telemetry/) của Kentik, việc lựa chọn giữa SNMP và Streaming Telemetry không đơn giản là loại bỏ cái cũ để thay bằng cái mới, mà là sự bổ trợ lẫn nhau.

### Điểm Mạnh và Yếu Của SNMP (The Veteran)
*   **Điểm Mạnh:**
    *   **Tương thích tuyệt đối:** Hỗ trợ từ switch Data Center đắt tiền đến router cũ 20 năm tuổi.
    *   **Chi phí thấp & Đơn giản:** Dễ triển khai, không cần kỹ năng chuyên sâu, nhiều công cụ miễn phí.
    *   **Tin cậy:** Đã được kiểm chứng qua hàng thập kỷ.
*   **Điểm Yếu:**
    *   **Dữ liệu có thể gây hiểu lầm:** Vì SNMP không có Timestamp tại nguồn (source timestamp), biểu đồ hiển thị dựa trên thời gian Server nhận được gói tin. Điều này có thể tạo ra các "gai" (spikes) giả hoặc làm phẳng các biến động thực tế.
    *   **Không hiệu quả ở quy mô lớn:** Cơ chế "Hỏi - Trả lời" lặp đi lặp lại tiêu tốn tài nguyên CPU của thiết bị mạng khi số lượng interface và metric tăng lên.

### Streaming Telemetry: Hướng Tiếp Cận Hiện Đại
*   **Lợi ích:**
    *   **Độ phân giải cao (High Resolution):** Cung cấp dữ liệu "Near Real-time", phù hợp cho các yêu cầu giám sát dưới 1 phút (sub-minute).
    *   **Hiệu quả phần cứng:** Việc xử lý đẩy dữ liệu thường được thực hiện bởi chip chuyên dụng (ASIC) thay vì CPU chính, nên ít ảnh hưởng hiệu năng thiết bị.
    *   **Dữ liệu chính xác:** Có Timestamp ngay tại nguồn, giúp vẽ biểu đồ chính xác tuyệt đối.
*   **Hạn chế:**
    *   **Chưa đồng bộ:** Nhiều thiết bị chưa hỗ trợ, hoặc mỗi hãng làm một kiểu (proprietary).
    *   **Phức tạp:** Đòi hỏi kỹ sư mạng phải học thêm về API, Data Models (YANG), và cấu hình phức tạp hơn SNMP nhiều.

### Kết Luận
Không nên loại bỏ hoàn toàn SNMP. Một chiến lược giám sát toàn diện (Network Visibility Strategy) nên bao gồm cả hai: **SNMP** cho tính tương thích rộng và cảnh báo cơ bản, kết hợp **Streaming Telemetry** cho các phần mạng cốt lõi cần độ chi tiết cao và real-time.
