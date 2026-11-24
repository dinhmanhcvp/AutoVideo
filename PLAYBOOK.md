# Playbook xây kênh truyện audio

Công cụ lo phần sản xuất. Playbook này nói về những thứ quyết định kênh có lên hay không, và các rủi ro bạn cần biết trước.

> **Nói thẳng:** không công cụ nào bảo đảm viral. Thứ công cụ làm được là nâng xác suất: chỉ làm truyện có tiềm năng, đóng gói theo cách đã được chứng minh, đo kết quả và làm nhiều hơn thứ đang chạy. Phần còn lại là **sự đều đặn và khả năng phán đoán của bạn khi duyệt**.

---

## 1. YouTube đề xuất video dựa trên gì

Kênh truyện audio sống nhờ **trang chủ và video đề xuất**, không nhờ tìm kiếm. YouTube đề xuất một video khi:

1. **Người ta bấm vào:** tỷ lệ bấm (CTR) đến từ thumbnail và tiêu đề.
2. **Người ta ở lại:** thời lượng xem trung bình, và phần trăm còn lại sau phút đầu tiên.
3. **Người ta xem tiếp:** sang video khác của kênh, quay lại kênh vào hôm sau.

Truyện audio có lợi thế lớn ở điểm 2: người nghe thường bật khi ngủ, lái xe, làm việc, nên thời lượng xem rất dài. Vì vậy:

- **Hook quyết định tất cả.** Người nghe qua được 3–5 phút đầu thì thường nghe hết.
  - Công cụ đặt hook ở đầu video và dừng ở cao trào.
  - Bạn kiểm tra hook mỗi ngày qua clip TikTok trên Telegram.
- **Thumbnail và tiêu đề quyết định có ai thử hay không.**
  - Mỗi video có 3 phương án. Hãy dùng *Thử nghiệm & so sánh* (Test & Compare) trong YouTube Studio cho video quan trọng.
- **Playlist theo chủ đề và lời mời ở outro** giữ người nghe ở lại kênh.
  - Điền `youtube.playlists` để mô tả có link playlist và video tự được thêm vào.

## 2. Chọn ngách

- **Kênh mới: 1 chủ đề, tối đa 2.** YouTube cần hiểu "khán giả của kênh này là ai" để biết đề xuất cho ai.
  - Kênh trộn hài, kinh dị và ngôn tình làm thuật toán khó khớp khán giả.
  - Mở rộng khi một chủ đề đã có lượt xem đều.
- **Ngách nên tránh khi mới bắt đầu:** truyện cực dài nhiều tập (khó giữ người nghe qua các video), truyện đề tài chính trị hay tôn giáo nhạy cảm, truyện 18+ (bị giới hạn quảng cáo).
- **Chủ đề đã có sẵn trong config:** hài gia đình, phá án có cú twist, ngôn tình hiện đại, thanh xuân thầm thích, kèm cổ trang và tâm sự đêm khuya (đang tắt).
  - Chạy `brand` để xem nhận diện từng chủ đề.
  - Chọn chủ đề bạn **thích nghe**, vì bạn sẽ phải duyệt chúng mỗi ngày.

## 3. Nhận diện kênh

- **Một mascot riêng** (nhân vật hoặc con vật) có mặt trên mọi thumbnail, và **một bảng màu cố định cho mỗi chủ đề**. Người xem nhận ra kênh trước cả khi đọc chữ.
- **Đừng sao chép mascot, tên hay logo của kênh khác.** Bố cục chung (ảnh một bên, tên truyện chữ lớn) thì ai cũng dùng được; nhận diện riêng mới giúp kênh không bị coi là kênh nhái.
- **Đọc thử thumbnail ở kích thước nhỏ** bằng cách thu ảnh còn 20% trên điện thoại. Không đọc được tên truyện trong 1 giây thì giảm chữ hoặc đổi màu.
- **Dùng ảnh minh họa thật** (`image_engine: cloud` hoặc `comfyui`). Ảnh nền màu chỉ để chạy thử.

## 4. Giọng đọc

- Giọng Edge HoaiMy và NamMinh **rất nhiều kênh đang dùng**. Người nghe lâu năm nhận ra ngay và dễ cho là "kênh rác AI".
- Giọng Google Chirp 3 HD hoặc ElevenLabs tạo khác biệt rõ với chi phí nhỏ.
- Chạy `voices --engine google` để nghe thử, và **giữ một giọng cố định cho mỗi chủ đề**. Giọng là thương hiệu.

## 5. Phễu TikTok và Shorts

Kênh mới gần như không được hiển thị. Clip ngắn mang về những người xem đầu tiên.

- **TikTok:** mỗi ngày đăng 1–3 clip hook (`tiktok.mp4`), kèm caption có sẵn.
  - Đặt link kênh YouTube ở bio.
  - Trả lời bình luận "tên truyện là gì?" bằng tên kênh.
  - Bật nhãn **"Nội dung do AI tạo"** vì giọng đọc là AI.
- **Shorts:** bot tự đăng `short.mp4` kèm link sang video dài.
  - Trong YouTube Studio → Shorts, đặt **"Video liên quan"** là video dài. Đây là nút bấm sang trực tiếp, hiệu quả hơn link trong mô tả (API không làm được việc này, bạn phải tự đặt).
- **Không đăng lại y hệt một clip ở nhiều tài khoản.** Một tài khoản TikTok đều đặn tốt hơn nhiều tài khoản đăng tràn lan.

## 6. Nhịp đăng

- **Đều đặn hơn số lượng:** 1 video dài mỗi ngày, cùng khung giờ (mặc định 19:30 hoặc 21:30), tốt hơn 5 video một ngày rồi nghỉ một tuần.
- **Tạo sẵn 7–10 video dự trữ** trước khi bắt đầu đăng đều, để những ngày bận hay PC lỗi không làm đứt nhịp.
- **Thời gian bạn cần mỗi ngày: khoảng 15 phút trên điện thoại.**
  1. Nghe 1–2 phút clip hook, đọc lướt vài đoạn bản dịch.
  2. Chọn phương án tiêu đề/thumbnail, bấm Hẹn giờ.
  3. Đăng clip TikTok, dán và ghim bình luận.
  4. Trả lời 5–10 bình luận. Bình luận sớm giúp video được đẩy.

## 7. Đọc số liệu và điều chỉnh

Bot gửi `/report` mỗi tuần. Nên **so các video của chính kênh bạn với nhau**, đừng so với con số của kênh khác.

| Dấu hiệu | Nghĩa là | Làm gì |
|---|---|---|
| CTR thấp hơn hẳn các video khác | thumbnail/tiêu đề chưa gây tò mò | đổi sang phương án 2 hoặc 3 trong Studio; dùng Test & Compare |
| Giữ chân < 25% (bot cảnh báo) | hook yếu, hoặc truyện không như tiêu đề hứa | nghe lại hook; tăng `quality.min_score`; sửa `prompts/hook.md` |
| Biểu đồ giữ chân tụt mạnh ở đoạn sau hook | câu chuyển hoặc lời dẫn dài, nhạc nền to | rút gọn intro trong prompt; hạ `audio.music_db_idle` |
| Một chủ đề vượt trội sau khoảng 10 video | ngách có khán giả | bật `auto.adaptive` để máy dồn sản lượng; cân nhắc tách kênh riêng |
| Một chủ đề yếu sau 10–15 video | ngách không hợp | tắt chủ đề (`enabled: false`), thử chủ đề khác |

Sau 2–3 tuần, khi đã có số liệu thật, hãy chỉnh prompt (`prompts/metadata.md`, `prompts/hook.md`) theo những gì tiêu đề và hook tốt nhất của **chính kênh bạn** đang làm.

## 8. Chính sách và rủi ro (đọc kỹ)

1. **Nội dung sản xuất hàng loạt.** YouTube từ chối hoặc gỡ kiếm tiền với nội dung bị coi là sản xuất hàng loạt, lặp lại, ít giá trị (từ giữa 2025, chính sách này được gọi là *inauthentic content*). Công cụ giảm rủi ro bằng:
   - cổng chất lượng,
   - hook, lời dẫn, lời bình riêng của kênh,
   - nhiều ảnh minh họa và nhận diện riêng,
   - bước duyệt của bạn.

   **Đừng tắt bước duyệt và đừng đẩy sản lượng lên quá mức bạn kiểm soát được.** Kênh bị đánh giá ở cấp kênh, nên vài chục video kém có thể kéo cả kênh.
2. **Bản quyền truyện.** Truyện mạng Trung Quốc (kể cả trên Zhihu, Bilibili, Ximalaya) phần lớn có chủ sở hữu, và **bản dịch vẫn là tác phẩm phái sinh**. Rủi ro gồm khiếu nại bản quyền, gỡ video, gậy bản quyền (3 gậy thì mất kênh). Cách giảm rủi ro:
   - ưu tiên truyện được phép sử dụng, truyện dân gian, truyện đã hết thời hạn bảo hộ, hoặc truyện bạn mua bản quyền;
   - dùng `inbox/` cho truyện bạn tự tuyển và đã kiểm tra nguồn;
   - lưu `source_info.json` (công cụ tự giữ) để biết nguồn khi có khiếu nại.
3. **Khai báo AI.** Công cụ bật `containsSyntheticMedia` khi upload (`youtube.declare_synthetic`) và khuyên gắn nhãn AI trên TikTok. Việc này không làm giảm đề xuất, nhưng **không khai báo khi bắt buộc** thì có thể bị phạt.
4. **Nhạc nền.** Chỉ dùng nhạc không bản quyền hoặc nhạc bạn có quyền dùng. TikTok tắt tiếng và YouTube Content ID nhận diện nhạc rất nhanh.
5. **Điều kiện kiếm tiền.** Mốc phổ biến của YouTube Partner Program là 1.000 người đăng ký kèm 4.000 giờ xem công khai trong 12 tháng, hoặc kèm 10 triệu lượt xem Shorts trong 90 ngày. Điều kiện có thể thay đổi theo thời gian và quốc gia, nên xem mục *Kiếm tiền* trong YouTube Studio của bạn.

## 9. Kế hoạch 30 ngày

| Tuần | Việc |
|---|---|
| 0 | `setup` → `doctor --online` → `brand --real`, chỉnh tới khi ưng. Làm mascot. Chọn 1–2 chủ đề, giọng đọc. Thêm nhạc nền. Tạo playlist cho mỗi chủ đề. |
| 1 | Bot chạy mỗi đêm. Tích 7–10 video dự trữ: **duyệt kỹ** từng video (nghe hook, đọc bản dịch) để chỉnh prompt và `min_score`. Chưa đăng. |
| 2 | Đăng 1 video/ngày cùng giờ, đăng 1–3 clip TikTok/ngày, Shorts tự đăng. Đặt "Video liên quan" cho Shorts. Trả lời bình luận. |
| 3 | Đọc `/report`. Đổi phương án thumbnail ở video có CTR thấp. Nghe lại hook của video giữ chân thấp. |
| 4 | Giữ lại chủ đề tốt, tắt chủ đề yếu. Nếu đủ số liệu, bật `auto.adaptive`. Chỉnh prompt theo các tiêu đề và hook tốt nhất của kênh. |
