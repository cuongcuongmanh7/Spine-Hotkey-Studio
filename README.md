# Spine Hotkey Studio

Tool desktop nhỏ gọn để chỉnh nhanh `hotkeys.txt` của Spine, phát hiện phím trùng và quản lý nhiều bộ preset riêng.

## Mở tool

Nhấp đúp `SpineHotkeyStudio.exe` (hoặc `launch.bat` nếu cần). Tool mặc định đọc file:

```text
C:\Users\Admin\Spine\hotkeys.txt
```

Hoặc chạy với một file khác:

```powershell
python app.py --file "D:\duong-dan\hotkeys.txt"
```

Tool chỉ dùng thư viện chuẩn của Python, không cần cài thêm package.

## Cách sử dụng

1. Tìm và chọn lệnh trong bảng.
2. Bấm **Ghi tổ hợp phím**, sau đó nhấn hotkey mong muốn; hoặc nhập cú pháp Spine trực tiếp vào ô chỉnh sửa rồi nhấn Enter.
3. Xử lý các cảnh báo trùng phím nếu cần.
4. Có thể bấm **Lưu thành preset mới** để giữ lại toàn bộ bộ phím hiện tại.
5. Đóng Spine hoàn toàn, sau đó bấm **Áp dụng vào Spine**.

Mỗi lần áp dụng, file cũ được sao lưu tự động trong thư mục `backups`. Preset cá nhân nằm trong `presets` và được Git bỏ qua mặc định.

## An toàn dữ liệu

- Không sửa `hotkeys.txt` cho đến khi bấm **Áp dụng vào Spine**.
- Không cho ghi khi tiến trình Spine còn chạy.
- Nếu file đã bị ứng dụng khác sửa sau lúc tool tải vào, tool sẽ tải lại thay vì ghi đè.
- Giữ nguyên thứ tự dòng, nhóm trùng, lệnh trùng và kiểu xuống dòng CRLF của file gốc.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
```
