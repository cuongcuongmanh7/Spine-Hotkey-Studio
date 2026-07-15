# Spine Hotkey Studio

Ứng dụng desktop Tauri 2 để chỉnh nhanh `hotkeys.txt` của Spine, phát hiện phím trùng và quản lý nhiều bộ preset riêng. Giao diện dark mode hiện đại, bo tròn và không cần cài Python.

## Tính năng

- Tìm kiếm và lọc hotkey theo nhóm.
- Chọn lệnh rồi nhấn trực tiếp tổ hợp phím cần gán.
- Nhập tay cú pháp phím đặc biệt của Spine.
- Cảnh báo hotkey trùng trước khi áp dụng.
- Tạo, nạp, đổi tên, sao chép và xóa preset.
- Đọc được preset JSON tạo bởi phiên bản Python cũ.
- Tạo backup tự động và thay file theo cơ chế atomic của Windows.
- Từ chối ghi khi Spine đang chạy hoặc `hotkeys.txt` vừa bị ứng dụng khác thay đổi.
- Bảo toàn thứ tự dòng, nhóm/lệnh trùng và CRLF của file Spine.

## Sử dụng

Tải installer từ trang Releases hoặc build ứng dụng rồi chạy:

```text
src-tauri\target\release\bundle\nsis\Spine Hotkey Studio_1.0.0_x64-setup.exe
```

Ứng dụng mặc định đọc:

```text
%USERPROFILE%\Spine\hotkeys.txt
```

Preset và backup được lưu trong thư mục dữ liệu ứng dụng của Windows, tách biệt khỏi repository và thư mục Spine.

## Phát triển

Yêu cầu:

- Node.js 20.19 trở lên.
- Rust stable với toolchain MSVC.
- Microsoft C++ Build Tools.
- Microsoft Edge WebView2.

Cài dependency và chạy development:

```powershell
npm install
npm run tauri dev
```

Chạy toàn bộ kiểm thử:

```powershell
npm run check
```

Build frontend và installer Windows:

```powershell
npm run tauri build
```

## Kiến trúc

- `src/`: frontend TypeScript/CSS thuần, không dùng framework UI.
- `src-tauri/src/lib.rs`: parser hotkey, preset, backup, kiểm tra tiến trình Spine và Tauri commands.
- `src-tauri/tauri.conf.json`: cấu hình cửa sổ và NSIS installer.

Frontend chỉ có quyền gọi các command Rust đã đăng ký. Toàn bộ thao tác filesystem được kiểm tra đường dẫn ở backend.
