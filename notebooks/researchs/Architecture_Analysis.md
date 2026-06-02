# Phân Tích Kiến Trúc Hiện Tại & So Sánh Mô Hình StatCan

Tài liệu này tổng hợp các phân tích về sự "lẫn lộn" trong kiến trúc hiện tại của dự án và làm rõ sự khác biệt với các mô hình chuẩn (như ví dụ từ StatCan).

## 1. Phân Tích Kiến Trúc Hiện Tại: Sự "Lẫn Lộn" & Thiếu Decoupling

Sau khi xem xét mã nguồn (`rasberrypi/manager.py`, `collectors/snmp.py`), chúng ta nhận thấy các vấn đề chính sau:

### A. Sự Kết Hợp Giữa Cũ & Mới (Hybrid/Mixed Logic)
*   **Thành phần Cũ (Polling):** Hệ thống đóng vai trò là một **SNMP Manager truyền thống**. Nó sử dụng thư viện `pysnmp` để gửi lệnh `GET/WALK` (Hỏi - Đáp) tới thiết bị. Đây là cơ chế chậm chạp, thụ động.
*   **Thành phần Mới (Pushing):** Ngay sau khi Poll xong, nó lại đóng gói dữ liệu và bắn **UDP** sang `query-service` để giả lập quá trình Streaming/Pushing.
*   **Nhận xét:** Đây là mô hình "Bình mới rượu cũ". Thay vì thiết bị tự đẩy data (Telemetry chuẩn), ta dựng một trạm trung gian để Poll rồi tự Push đi.

### B. Vấn đề Tight Coupling (Dính chặt, Thiếu tách biệt)
Thành phần `Collector` (`manager.py`) đang "biết quá nhiều" và làm quá nhiều việc:
1.  **Thu thập:** Poll SNMP.
2.  **Lưu trữ (Vấn đề lớn):** Kết nối trực tiếp vào Database (`db_service.db_writer`) để ghi dữ liệu. Đây là **sai nguyên tắc** Decoupling. Collector không nên quan tâm DB là gì.
3.  **Truyền tin:** Gửi UDP cho `query-service` hiển thị Real-time.

=> **Hậu quả:** Khó mở rộng, khó thay đổi DB, khó tái sử dụng code cho thiết bị khác.

### C. Hạn Chế Đơn Lẻ (Single Device)
*   Code được viết hard-code để chạy vòng lặp vô tận cho **1 thiết bị** (`snmp_agent` là chuỗi đơn).
*   Không có cơ chế duyệt danh sách thiết bị hay đa luồng (multi-thread) để quản lý quy mô lớn.

### D. Xác nhận về `psutil`
*   Hệ thống dùng thuần túy giao thức mạng SNMP (UDP 161) qua `pysnmp`, không sử dụng `psutil` để đọc thông số hệ thống local.

---

## 2. So Sánh Với Mô Hình StatCan (Metric Collector -> Kafka -> DB)

Có sự thắc mắc rằng mô hình của StatCan cũng là Collector gom data rồi đẩy đi, vậy tại sao mô hình hiện tại lại bị coi là "sai" hay "lẫn lộn"?

### Sự Khác Biệt Cốt Lõi: Trách Nhiệm (Responsibility)

| Đặc Điểm | Mô Hình StatCan / Chuẩn Hiện Đại | Mô Hình Hiện Tại (Project) |
| :--- | :--- | :--- |
| **Luồng Dữ Liệu** | Collector -> **Kafka** -> Consumer -> **DB** | Collector -> **DB** (Trực tiếp) <br> *Đồng thời* <br> Collector -> **UDP** -> Query Service |
| **Trách nhiệm của Collector** | Chỉ làm 1 việc: Gom dữ liệu và ném vào ống dẫn (Kafka/Queue). **Không biết DB là gì.** | Làm 3 việc: Gom, **Ghi DB**, Bắn UDP. |
| **Tính Decoupling** | **Cao.** Muốn đổi DB từ InfluxDB sang Prometheus? Chỉ cần sửa Consumer/DB Adapter. Collector giữ nguyên. | **Thấp.** Muốn đổi DB? Phải sửa code trong Collector (`manager.py`). |
| **Cơ chế Thu thập** | Thường là Agent cài trên máy (Node Exporter) đọc file OS cực nhanh. | Dùng máy này Poll máy kia qua mạng (SNMP) rồi mới đẩy đi. |

### Kết Luận
Vấn đề không nằm ở hành động "Push UDP" (đó là điểm tốt), mà nằm ở việc Collector đang **ôm đồm trách nhiệm ghi DB**.

**Để chuẩn hóa (Decoupling):**
1.  Collector (`manager.py`) chỉ nên: Poll SNMP -> Bắn UDP (JSON). **Cắt bỏ hoàn toàn code DB.**
2.  Query Service (Consumer) sẽ: Nhận UDP -> (1) Đẩy WebSocket Realtime + (2) Ghi xuống DB.
