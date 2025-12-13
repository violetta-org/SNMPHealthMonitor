# Đối chiếu hai tài liệu SNMP cho Raspberry Pi

## Nguồn tham chiếu
- Hướng dẫn tùy biến SNMP với OID đo nhiệt độ/điện áp từ repo công khai của Thomas Stolt ([ThomasStolt/Raspberry-Pi-Temperatur-and-Voltage-via-SNMP](https://github.com/ThomasStolt/Raspberry-Pi-Temperatur-and-Voltage-via-SNMP)).
- Ghi chép nội bộ `rasberrypi.md` trong dự án hiện tại.

## Nội dung chính của repository Thomas Stolt
- Repo giới thiệu cách thêm hai OID tùy biến (`.1.3.6.1.4.1.8072.9999.9999.1` và `.2`) thông qua chỉ thị `pass` trong `snmpd.conf`, mỗi OID gọi một script shell để trả về nhiệt độ CPU (milli-Celsius) và điện áp core (milli-Volt). Các script được đặt tại `/usr/local/bin`, snmpd chạy chúng khi nhận `snmpget` vào OID tương ứng và trả về Gauge32 đã chuẩn hóa ([ThomasStolt/Raspberry-Pi-Temperatur-and-Voltage-via-SNMP](https://github.com/ThomasStolt/Raspberry-Pi-Temperatur-and-Voltage-via-SNMP)).
- Quy trình triển khai ngắn gọn: thêm hai dòng `pass`, copy script, đảm bảo user `Debian-snmp` nằm trong nhóm `video`, rồi kiểm tra bằng `snmpget`. Đây là giải pháp tối ưu khi cần nhanh chóng xuất một số tham số không có sẵn trong MIB mặc định nhưng vẫn muốn giữ SNMP làm kênh thu thập.

## Nội dung chính của `rasberrypi.md`
- Tài liệu nội bộ đi sâu hơn: mục tiêu là dựng toàn bộ bộ chỉ số trên Raspberry Pi 5 chạy LibreNMS, bao gồm SNMP core MIB, UCD-SNMP và cả NET-SNMP-EXTEND-MIB. Ngoài CPU/memory/disk còn có script nhiệt độ thông qua `extend temp`.

```47:76:query-service/markdowns/rasberrypi.md
rocommunity public
disk / 10000
view systemonly included .1.3.6.1.2.1.
view systemonly included .1.3.6.1.4.1.8072.
extend temp /bin/bash /usr/local/bin/snmp-temperature.sh
#!/bin/bash
vcgencmd measure_temp | sed "s/temp=//;s/'C//"
sudo usermod -aG video Debian-snmp
sudo reboot
```

- Tài liệu còn nêu rõ cách chạy `snmpwalk` cho từng OID UCD, bật các module trong LibreNMS, chạy poller/rediscovery, và checklist đồ thị hiển thị trên dashboard để xác nhận trạng thái cuối ([`query-service/markdowns/rasberrypi.md`](query-service/markdowns/rasberrypi.md)).

## So sánh và phân tích
- **Mục tiêu**: Repo Thomas Stolt tập trung vào hai phép đo chuyên biệt (nhiệt độ, điện áp) cho mục đích logging dài hạn, trong khi `rasberrypi.md` mô tả blueprint hoàn chỉnh để thay thế thiếu hụt Host Resources MIB trên ARM, đảm bảo LibreNMS vẫn có đủ dữ liệu CPU/memory/storage/health.
- **Cơ chế mở rộng**: Repo dùng `pass` (chạy script khi OID được hỏi), còn tài liệu nội bộ tận dụng `extend` (script luôn sẵn, được map vào NET-SNMP-EXTEND-MIB). `pass` thuận tiện cho OID “ảo” đặt dưới doanh nghiệp OID tree tùy ý, `extend` cho phép truy vấn dưới namespace chuẩn `NET-SNMP-EXTEND-MIB::nsExtendOutput1Line."name"`.
- **Đối tượng sử dụng**: Hướng dẫn công khai phù hợp khi muốn tách lệnh đo ra ngoài SNMP chuẩn để phục vụ nhiều công cụ (telegraf, MRTG). Ghi chép nội bộ tập trung vào LibreNMS trong container, kèm thao tác `docker exec`, `lnms poller`, nên thích hợp cho đội vận hành hệ thống giám sát.
- **Độ bao phủ metric**: Repo không đề cập CPU/memory/disk chuẩn vì giả định đã có sẵn; tài liệu nội bộ chứng minh các OID UCD-SNMP hoạt động, nêu rõ lệnh kiểm tra `snmpwalk -v2c -c public localhost hrProcessorLoad` cùng các OID `.1.3.6.1.4.1.2021.*` để kích hoạt biểu đồ LibreNMS.

## Đề xuất kết hợp
- Dùng cấu trúc extend trong `rasberrypi.md` để xuất nhiệt độ/điện áp thay vì `pass`, giúp mọi custom sensor hiển thị trực tiếp dưới NET-SNMP-EXTEND, đồng thời giữ khả năng truy cập qua doanh nghiệp OID nếu cần tương thích ngược.
- Viết thêm script đo điện áp dựa trên mẫu repo Thomas Stolt rồi đăng ký qua `extend voltage ...` để LibreNMS health tab có cả voltage sensor.
- Xuất bản bản rút gọn của `rasberrypi.md` (ví dụ README nội bộ) để chia sẻ cộng đồng, tận dụng repo Thomas Stolt làm nguồn tham chiếu chính thức cho phần custom OID, đảm bảo bản quyền/ghi nhận nguồn.

