# AutoEdit TikTok Studio — Windows

## Mở giao diện từ mã nguồn

Trong PowerShell tại thư mục dự án:

```powershell
.\.venv\Scripts\python.exe app.py
```

Giao diện dùng Tkinter có sẵn trong Python Windows. Không chạy `test_run.py` để mở giao diện. Ứng dụng không nhập khóa API từ tệp đó.

Toàn bộ quy trình nằm trong **một tab Tạo video**. Cuộn để xem các phần; cửa sổ rộng hiển thị kịch bản và thiết lập xuất cạnh nhau, cửa sổ hẹp xếp dọc. Nút Hướng dẫn mở nội dung ngay trong tab này. Thanh bên dành cho các công cụ có thể bổ sung sau này.

1. **Video nguồn & thông tin bổ sung:** chọn video, nhập Gemini API Key và bấm **Gemini phân tích & viết**. Thông tin bổ sung là tùy chọn, mặc định để trống. Chỉ nhập giá thuê, địa chỉ hoặc dữ kiện đã xác nhận mà video không thể hiện rõ.
2. **Kịch bản & giọng:** tạo kịch bản hoặc tự viết, sửa lời bình/caption. Chọn Gemini (Aoede, có Edge dự phòng) hoặc Edge-TTS. Giọng Hoài My/Nam Minh và tốc độ là thiết lập của Edge. Bấm tạo giọng, nghe thử bằng trình phát mặc định.
3. **Nhận diện & xuất video:** logo `assets/logo/logo.png` và nhạc `assets/bgm/upbeat_tiktok_bgm.mp3` được bật mặc định. Có thể thay tệp, bật/tắt logo, nhạc, sticker và chọn thư mục xuất. Lựa chọn đã lưu được ưu tiên hơn mặc định, kể cả khi bạn tắt logo/nhạc.
4. **TẠO VIDEO:** dùng lời bình đang có; nếu trống thì gọi AI viết. Tạo giọng mới và render. **Render với giọng đã chọn** dùng tệp âm thanh hiện tại, không gọi TTS lại. Nếu sửa lời bình sau khi tạo giọng, hãy tạo lại giọng.

Video MP4 giữ tỷ lệ nguồn, xuất 30 fps với H.264/AAC. Chưa tự cắt video ngang thành 9:16. Mỗi video có tên riêng theo thời gian, kèm `.script.txt` và `.caption.txt` nếu có nội dung. Nút xem video mới nhất nằm trong Thiết lập xuất.

Gemini nhận ảnh ghép các khung hình trích từ video hiện tại để trả về **mô tả phòng, lời bình và caption**. Mục **Gemini quan sát được** hiển thị mô tả do AI trả về; bản mô tả cũng được lưu thành `.room.txt`. Thông tin bổ sung không được tự điền lại từ cấu hình cũ. Không có kịch bản mẫu dự phòng: nếu model không khả dụng, API lỗi, hết quota, hết thời gian chờ hoặc JSON thiếu nội dung, tác vụ dừng và báo lỗi trước khi tạo giọng/render. Model sử dụng đúng tên đang nhập trong giao diện; hãy chọn model được tài khoản của bạn hỗ trợ.

Bạn vẫn có thể sửa lời bình/caption hoặc nhập nội dung riêng. Sau khi đổi video, nếu còn kịch bản Gemini của video trước, ứng dụng yêu cầu phân tích lại trước khi render. Phân tích khung hình không đảm bảo nhận biết những chi tiết không xuất hiện trong ảnh; kiểm tra lại nội dung AI trước khi xuất.

## Xử lý nền và dữ liệu

- AI/TTS cần Internet; quota/quyền truy cập phụ thuộc tài khoản dịch vụ. Nhập lời bình và chọn tệp giọng có sẵn để render hoàn toàn ngoại tuyến.
- API Key, đường dẫn và lựa chọn bật/tắt được lưu khi bắt đầu tác vụ hoặc đóng ứng dụng: `.appdata/settings.json` khi chạy mã nguồn; `%LOCALAPPDATA%/AutoEditTikTok/settings.json` khi chạy EXE. API Key nằm trong JSON cục bộ dạng văn bản và được che trong giao diện/nhật ký. Tệp cấu hình không được đưa vào bản đóng gói. Nội dung về một căn phòng không được lưu vào cấu hình chung để tránh dùng nhầm cho video khác.
- Mỗi lượt chạy dùng `<thư mục xuất>/.autoedit_work/<job_id>` rồi dọn dữ liệu trung gian khi hoàn tất hoặc gặp lỗi. Thư mục cha được xóa nếu đã rỗng. Giọng đọc (`.voice.mp3` hoặc `.voice.wav`) và ảnh tham khảo (`.storyboard.jpg`) được lưu cạnh video để nghe, xem và render lại sau khi dọn tạm.
- Nút Dừng kết thúc tác vụ và tiến trình FFmpeg của nó rồi dọn thư mục tạm của tác vụ đã nhận. Video chưa hoàn tất không được công bố. Thư mục cũ từ các phiên bản trước hoặc khi máy tắt đột ngột không bị tự xóa.
- Log xuất hiện ngay trong cửa sổ; lỗi FFmpeg có chi tiết ở cuối nhật ký. Thanh chạy biểu thị tác vụ còn hoạt động, không phải phần trăm chính xác.

## Đóng gói thành EXE

Chỉ chạy các lệnh dưới đây **khi bạn chủ động muốn đóng gói**. Mở ứng dụng và kiểm thử không tự tạo EXE. Đóng gói trên Windows 64-bit bằng môi trường Python của dự án; các phiên bản thư viện nằm trong `requirements-build.txt`.

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Kết quả:

```text
dist/
  AutoEditTikTok/
    AutoEditTikTok.exe
    _internal/              # Python, thư viện, ffmpeg.exe, ffprobe.exe
    HUONG_DAN.md
```

Mở `AutoEditTikTok.exe`. Khi chuyển máy, **sao chép hoặc nén ZIP toàn bộ thư mục `dist/AutoEditTikTok`**. Chép riêng EXE của bản này sẽ thiếu thư viện. Máy nhận không cần cài Python hoặc FFmpeg, nhưng cần Internet khi dùng AI/TTS. Hai tài nguyên logo/nhạc mặc định trong `assets` được đóng gói; video, cấu hình và API Key không được đóng gói. Tệp cá nhân chọn ở vị trí khác cần chọn lại trên máy nhận.

Nếu muốn đúng một tệp EXE:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1 -OneFile
```

Kết quả là `dist/AutoEditTikTok.exe`. Bản này chứa FFmpeg nên lớn và khởi động chậm hơn do giải nén vào thư mục tạm. Bản thư mục được khuyến nghị để khởi động nhanh và dễ kiểm tra lỗi. Hai lệnh đóng gói sẽ cập nhật bản build cùng tên hiện có.

Script kiểm tra môi trường, cài công cụ đóng gói, chạy kiểm thử rồi tạo EXE. Không cần quyền Administrator nếu thư mục dự án cho phép ghi. Không đưa cả thư mục dự án hoặc `test_run.py` vào gói phát hành. Nếu phân phối công khai FFmpeg đi kèm, cung cấp giấy phép và thông tin bản build tương ứng của FFmpeg (kiểm tra bằng `ffmpeg -L`).

### Khôi phục môi trường và kiểm tra mà không đóng gói

Nếu `.venv` được chép từ máy khác hoặc trỏ tới Python không còn tồn tại, script sẽ tìm Python 3.14/3.15 64-bit có Tcl/Tk trên máy hiện tại, chuyển môi trường cũ sang `.venv-backup-<thời gian>-<mã>` trong dự án rồi tạo `.venv` mới. Không xóa bản cũ và không dùng lại thư viện nhị phân khác phiên bản.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1 -SetupOnly
```

`-SetupOnly` chuẩn bị môi trường, kiểm tra đầu vào và chạy kiểm thử, **không gọi PyInstaller để tạo EXE và không sửa bản EXE hiện có**. Dòng cuối thành công là `Moi truong da san sang. SetupOnly: khong dong goi EXE.`

Nếu Python không nằm trong PATH/launcher, có thể chỉ định đường dẫn khi cần tạo lại môi trường:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1 -SetupOnly -PythonExe "C:\Python314\python.exe"
```

Kiểm tra Python riêng (không cài thư viện, không tạo môi trường):

```powershell
py -0p
py -3.14 .\scripts\check_build_python.py
```

Probe dùng tệp Python để tránh lỗi mất dấu ngoặc kép của Windows PowerShell khi truyền mã qua `-c`. Nếu thất bại, script in lỗi thực tế của từng Python đã thử, thay vì chỉ thông báo chưa cài đặt.

Cài FFmpeg và FFprobe, hoặc đặt `ffmpeg.exe` cùng `ffprobe.exe` vào thư mục `bin` ở gốc dự án. Nếu không tìm thấy nhưng bản thư mục cũ có `dist/AutoEditTikTok/_internal/bin`, script sao chép hai công cụ đó vào `bin/` (không ghi đè file có sẵn) để lần build sau không dùng chính thư mục đầu ra làm nguồn. Lõi cũng nhận FFmpeg trong PATH hoặc được cài bằng WinGet. Script chạy thử `-version` của cả hai trước khi cho phép đóng gói.

## Kiểm tra kết nối giao diện–lõi

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 app.py --smoke-test temp\desktop_smoke
```

Kiểm tra bản đóng gói:

```powershell
Start-Process -FilePath .\dist\AutoEditTikTok\AutoEditTikTok.exe -ArgumentList '--smoke-test', 'temp\exe_smoke' -Wait
Get-Content -Encoding UTF8 .\temp\exe_smoke\report.json
```

Smoke test tự tạo video/âm thanh mẫu, mở giao diện một tab, chạy render qua tiến trình nền, kiểm tra luồng hình/tiếng, lưu/đọc lại API Key giả cùng lựa chọn Logo/Nhạc, và xác nhận thư mục tạm đã được dọn. `report.json` có `ok: true` khi đạt. `interface.png` ghi lại giao diện. Không gọi API hoặc dùng quota trong phép thử này; giọng mẫu là âm sin để kiểm tra kết nối âm thanh, không phải lời đọc thật.

Các phép thử ngoại tuyến không xác nhận quota API, mạng hoặc chất lượng lời bình/giọng thực tế. Sau khi nhập key, hãy thử một video ngắn, nghe lại giọng và xem bản xuất trước khi đăng.
