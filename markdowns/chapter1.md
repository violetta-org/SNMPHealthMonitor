# CHƯƠNG 1. CƠ SỞ LÝ THUYẾT

## 1.1 Giới thiệu đề tài

### 1.1.1 Tổng quan đề tài

**Đề tài tập trung nghiên cứu và phát triển cái gì?**  
Đề tài tập trung nghiên cứu và phát triển một hệ thống Web Application tích hợp nhằm giám sát tài nguyên và điều khiển từ xa các thiết bị máy tính nhúng, cụ thể là Raspberry Pi. Hệ thống giải quyết vấn đề quản trị hệ thống Linux từ xa bằng giao diện đồ họa (GUI) trực quan thay vì chỉ phụ thuộc vào giao diện dòng lệnh (CLI).

**Kiến trúc hệ thống bao gồm các thành phần?**  
Kiến trúc hệ thống bao gồm hai thành phần logic chính hoạt động trên cùng một thiết bị hoặc mô hình Client-Server:
1.  **Server/Backend:** Được xây dựng trên ngôn ngữ Python với Framework Flask và thư viện Socket.IO, chịu trách nhiệm tương tác với Hệ điều hành để thu thập dữ liệu (CPU, RAM, Disk) và thực thi lệnh hệ thống.
2.  **Client/Frontend:** Giao diện Dashboard chạy trên trình duyệt Web, hiển thị dữ liệu thời gian thực và cung cấp các công cụ tương tác (Terminal, File Manager) cho người dùng.

**Hệ thống được triển khai như thế nào?**  
Hệ thống được triển khai trọn gói (standalone) ngay trên thiết bị Raspberry Pi. Thiết bị đóng vai trò vừa là máy chủ Web phục vụ ứng dụng, vừa là đối tượng giám sát. Người dùng chỉ cần truy cập vào địa chỉ IP của Raspberry Pi thông qua trình duyệt Web trên cùng mạng cục bộ (LAN) hoặc qua Internet (nếu cấu hình Port Forwarding) để sử dụng toàn bộ tính năng.

### 1.1.2 Mục tiêu thực hiện

#### 1.1.2.1 Mục tiêu tổng quát
Vận dụng các kiến thức nền tảng của hai môn học "Hệ điều hành" và "Mạng máy tính" để xây dựng một sản phẩm công nghệ hoàn chỉnh, có tính ứng dụng thực tiễn cao, phục vụ cho việc quản trị hệ thống.

#### 1.1.2.2 Mục tiêu cụ thể
*   Xây dựng được cơ chế thu thập thông tin hoạt động của hệ điều hành Linux (Process, Memory, I/O) theo thời gian thực.
*   Thiết lập được kênh truyền thông tin cậy và tốc độ cao giữa Server và Client sử dụng giao thức WebSocket.
*   Triển khai thành công các tính năng quản trị cốt lõi: Dashboard giám sát, Web Terminal, và trình quản lý File.

## 1.2 Cơ sở lý thuyết

### 1.2.1 Hệ điều hành Linux

#### 1.2.1.1 Giới thiệu
Linux là một hệ điều hành mã nguồn mở (Open Source), giống Unix, được phát triển dựa trên hạt nhân Linux (Linux Kernel). Nó đóng vai trò là phần mềm trung gian giao tiếp giữa phần cứng máy tính và các ứng dụng phần mềm.

#### 1.2.1.2 Ưu điểm của hệ điều hành Linux
*   **Tính linh hoạt và tùy biến cao:** Linux cho phép cài đặt và cấu hình linh hoạt các dịch vụ như Flask (Web Server), SQLite (Database), Socket.IO (Real-time Communication) – là các thành phần quan trọng trong hệ thống giám sát và điều khiển từ xa.
    
*   **Hiệu năng ổn định:** Linux tối ưu việc quản lý tài nguyên hệ thống và hỗ trợ chạy đa tiến trình, giúp xử lý log, phân tích gói tin và phát hiện tấn công trong thời gian thực hiệu quả hơn. Đây là yếu tố quan trọng cho các máy chủ hoạt động liên tục 24/7 như Raspberry Pi trong đề tài.
    
*   **Bảo mật cao:** Linux có cơ chế phân quyền chặt chẽ (user/group permission, SELinux, AppArmor) giúp hạn chế truy cập trái phép và bảo vệ các dịch vụ mạng như Terminal SSH và File Manager khỏi các cuộc tấn công.
    
*   **Mã nguồn mở:** Cho phép nhà phát triển tùy chỉnh nhân (kernel) hoặc điều chỉnh module để tối ưu hiệu năng giám sát, phát hiện xâm nhập.
    
*   **Cộng đồng hỗ trợ mạnh mẽ:** Linux có cộng đồng lớn cung cấp tài liệu, công cụ mã nguồn mở và hỗ trợ triển khai các framework như Flask và các thư viện Python (psutil, Paramiko) phục vụ cho việc xây dựng ứng dụng giám sát.

#### 1.2.1.3 Ứng dụng của Linux trong đề tài
Trong đề tài "Giám sát và điều khiển Raspberry Pi từ xa qua giao diện Web", nhóm sử dụng hệ điều hành Raspberry Pi OS (dựa trên Debian Linux) làm nền tảng triển khai. Hệ thống tận dụng các đặc tính của Linux như sau:

*   **Thu thập dữ liệu hệ thống qua SNMP:** Triển khai SNMP Agent (snmpd) trên Raspberry Pi để expose các metrics hệ thống theo chuẩn MIB (Management Information Base). Manager Engine sử dụng thư viện PySNMP để truy vấn các OID (Object Identifier) định kỳ, thu thập thông tin CPU, RAM, Disk, Network I/O và lưu trữ vào cơ sở dữ liệu MySQL.

*   **Xây dựng Web Server:** Triển khai Flask framework chạy trên môi trường Python của Linux để cung cấp giao diện Web và các REST API phục vụ việc quản lý file, xác thực người dùng, và truy vấn dữ liệu lịch sử từ database.

*   **Truyền tải thời gian thực:** Tích hợp Socket.IO để thiết lập kênh WebSocket song công (full-duplex), cho phép server chủ động đẩy (push) dữ liệu giám sát về client mà không cần polling, giảm độ trễ và tải mạng.

*   **Điều khiển hệ thống từ xa:** Sử dụng thư viện Paramiko để tạo phiên SSH nội bộ, cho phép người dùng thực thi lệnh Terminal trực tiếp trên Raspberry Pi thông qua giao diện Web một cách an toàn.

### 1.2.2 Giao thức và mô hình mạng lõi

#### 1.2.2.1 Mô hình OSI
**a) Tổng quan**  
Mô hình OSI (Open Systems Interconnection) là mô hình tham chiếu kết nối các hệ thống mở, thiết lập các tiêu chuẩn chung cho việc truyền thông giữa các hệ thống máy tính khác nhau.

**b) Cấu trúc 7 tầng của mô hình OSI**
1.  **Physical (Tầng Vật lý):** Truyền tải dòng bit qua môi trường vật lý.
2.  **Data Link (Tầng Liên kết dữ liệu):** Đóng gói dữ liệu thành Frame, kiểm soát lỗi và luồng.
3.  **Network (Tầng Mạng):** Định tuyến gói tin (Packet) giữa các mạng khác nhau (IP).
4.  **Transport (Tầng Giao vận):** Đảm bảo truyền dữ liệu tin cậy giữa hai đầu cuối (TCP/UDP).
5.  **Session (Tầng Phiên):** Thiết lập, duy trì và đồng bộ hóa các phiên giao tiếp.
6.  **Presentation (Tầng Trình diễn):** Định dạng, mã hóa và nén dữ liệu.
7.  **Application (Tầng Ứng dụng):** Cung cấp giao diện cho các ứng dụng mạng người dùng (HTTP, FTP).

#### 1.2.2.2 Mô hình TCP/IP
**a) Tổng quan**  
TCP/IP (Transmission Control Protocol/Internet Protocol) là bộ giao thức truyền thông thực tế đang được sử dụng làm nền tảng cho Internet hiện nay.

**b) Cấu trúc 4 tầng của mô hình TCP/IP**
1.  **Network Access (Tầng Truy cập mạng):** Tương ứng với tầng Physical và Data Link của OSI.
2.  **Internet (Tầng Mạng):** Tương ứng với tầng Network (IP).
3.  **Transport (Tầng Giao vận):** Tương ứng với tầng Transport (TCP).
4.  **Application (Tầng Ứng dụng):** Tương ứng với 3 tầng trên cùng của OSI.

#### 1.2.2.3 Giao thức IP (Internet Protocol)
**a) Tổng quan**  
Là giao thức thuộc tầng Internet, chịu trách nhiệm định địa chỉ và định tuyến các gói tin để chúng có thể đi từ nguồn đến đích qua các mạng kết nối. IP hoạt động theo mô hình "best-effort" (nỗ lực tối đa), không đảm bảo độ tin cậy.

**b) Cấu trúc gói tin (packets)**
Gồm 2 phần chính:
1.  **Header (Tiêu đề):** Chứa thông tin điều khiển như Địa chỉ IP nguồn, Địa chỉ IP đích, Version, TTL, Checksum.
2.  **Payload (Dữ liệu):** Chứa dữ liệu của tầng trên (ví dụ: segment TCP hoặc datagram UDP).

#### 1.2.2.4 Giao thức TCP (Transmission Control Protocol)
**a) Tổng quan**
*   **Khái niệm:** Là giao thức hướng kết nối (connection-oriented) thuộc tầng Giao vận.
*   **Đặc điểm:** Cung cấp khả năng truyền dữ liệu tin cậy, đảm bảo dữ liệu đến đích đúng thứ tự và không bị mất mát thông qua cơ chế bắt tay ba bước (3-way handshake) và kiểm soát lỗi.

**b) Các cờ TCP trong giao thức**
Các cờ (Flags) nằm trong TCP Header để điều khiển trạng thái kết nối:
*   **SYN (Synchronize):** Yêu cầu thiết lập kết nối.
*   **ACK (Acknowledge):** Xác nhận đã nhận được gói tin.
*   **FIN (Finish):** Yêu cầu ngắt kết nối.
*   **RST (Reset):** Ngắt kết nối ngay lập tức khi có lỗi.
*   **PSH (Push):** Yêu cầu đẩy dữ liệu lên tầng ứng dụng ngay.
*   **URG (Urgent):** Đánh dấu dữ liệu khẩn cấp.

#### 1.2.2.5 Ứng dụng của mô hình mạng trong đề tài
Trong đề tài này, TCP/IP là nền tảng cốt lõi. Giao thức IP giúp định danh Raspberry Pi trong mạng LAN. Giao thức TCP đảm bảo việc truyền tải code HTML, CSS, JS và dữ liệu giám sát WebSocket luôn chính xác, không bị mất gói tin, đảm bảo tính toàn vẹn của giao diện điều khiển.

### 1.2.3 Các giao thức ứng dụng Web

#### 1.2.3.1 Giao thức HTTP (Hypertext Transfer Protocol)
**a) Tổng quan**  
HTTP là giao thức truyền tải siêu văn bản hoạt động ở tầng Ứng dụng, dùng để trao đổi dữ liệu giữa Web Browser và Web Server.

**b) Cấu trúc HTTP Request (Yêu cầu)**

| Thành phần | Chi tiết | Chức năng |
| :--- | :--- | :--- |
| **Request Line** | Method (GET, POST...), URI, HTTP Version | Xác định hành động và tài nguyên mong muốn. |
| **Headers** | Host, User-Agent, Content-Type... | Cung cấp thông tin meta về Client và nội dung yêu cầu. |
| **Body** | Dữ liệu (JSON, Form data...) | Chứa dữ liệu gửi lên Server (thường dùng trong POST/PUT). |

**c) Cấu trúc HTTP Response (Phản hồi)**

| Thành phần | Chi tiết | Chức năng |
| :--- | :--- | :--- |
| **Status Line** | HTTP Version, Status Code (200, 404...), Reason | Thông báo trạng thái xử lý của Server. |
| **Headers** | Content-Type, Content-Length, Set-Cookie... | Thông tin meta về Server và dữ liệu trả về. |
| **Body** | HTML, JSON, File binary... | Nội dung chính mà Client yêu cầu hiển thị. |

#### 1.2.3.2 Giao thức Websocket
**a) Tổng quan**  
WebSocket là một giao thức truyền thông cung cấp kênh giao tiếp song công (full-duplex) qua một kết nối TCP duy nhất, cho phép Server chủ động gửi dữ liệu xuống Client.

**b) Cơ chế hoạt động**
Quá trình bắt đầu bằng một HTTP Handshake. Client gửi yêu cầu Upgrade lên WebSocket. Nếu Server chấp nhận, kết nối HTTP sẽ chuyển sang kết nối WebSocket bền vững, cho phép truyền dữ liệu hai chiều liên tục với độ trễ thấp (low latency) và overhead nhỏ (header rất nhẹ sau khi kết nối).

**c) Ứng dụng của giao thức Websocket**
WebSocket là lựa chọn tối ưu cho các ứng dụng thời gian thực (Real-time) như: Chat trực tuyến, Game online, cập nhật giá chứng khoán, và trong đề tài này là **Cập nhật biểu đồ giám sát hệ thống**.

#### 1.2.3.3 Ứng dụng các giao thức trong thiết kế hệ thống
*   **HTTP:** Sử dụng để tải giao diện ban đầu (HTML/CSS/JS) và thực hiện các API RESTful quản lý File (Upload, Download, Delete) vì tính chất phi trạng thái (stateless) phù hợp cho các tác vụ này.
*   **WebSocket (thư viện Socket.IO):** Sử dụng để stream dữ liệu CPU/RAM liên tục về Dashboard và duy trì phiên kết nối cho Web Terminal, đảm bảo độ trễ thấp nhất cho trải nghiệm điều khiển mượt mà.
