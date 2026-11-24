# AutoVideo

Công cụ làm **video truyện audio tiếng Việt** cho YouTube (kèm clip TikTok và YouTube Shorts) từ truyện
tiếng Trung, chạy tự động trên PC. Bạn duyệt và đăng bằng điện thoại.

Mục tiêu là **ra view thật**, không phải ra thật nhiều video. Vì vậy công cụ:
- loại truyện yếu trước khi làm,
- mở mỗi video bằng một hook 2–5 phút,
- làm 3 phương án tiêu đề/thumbnail,
- dùng TikTok và Shorts để kéo người xem về video dài,
- đo kết quả rồi dồn sức cho chủ đề ăn khách.

> 📘 Đọc thêm **[PLAYBOOK.md](PLAYBOOK.md)**: chiến lược xây kênh, những gì công cụ không làm thay bạn được, và các rủi ro chính sách/bản quyền cần biết.

```
 tìm truyện ─► bóc băng ─► CHẤM ĐIỂM ─► dịch + QA ─► hook 2–5' ─► giọng đọc ─► đóng gói ─► render
 (Bilibili,     (Whisper)   loại truyện   bảng nhân    câu đầu      Google/Edge/   3 tiêu đề   YouTube 16:9
  YouTube,                  yếu/dở dang   vật, xưng hô  gây sốc,     ElevenLabs     3 thumbnail TikTok 9:16
  inbox/)                                               dừng ở                      mục lục     Shorts ≤3'
                                                        cao trào                    chương
        ─► Telegram trên điện thoại: xem clip, chọn phương án, bấm Đăng/Hẹn giờ ─► YouTube + Shorts
        ─► báo cáo view/giữ chân hằng tuần ─► tự dồn sản lượng cho chủ đề ăn khách
```

---

## 1. Cài đặt (Windows, khoảng 15 phút)

1. Cài **Python 3.10+** từ python.org (tick *Add python.exe to PATH*).
2. Tải repo này về máy, mở thư mục, **chạy `scripts\install.bat`**. Script sẽ:
   - cài FFmpeg (nếu thiếu) và các thư viện,
   - tải font tiếng Việt,
   - mở **trình cài đặt hỏi đáp** (`setup`): chọn tên kênh, máy mạnh/yếu, chủ đề, giọng đọc, cách vẽ ảnh, Telegram, rồi dán các khóa API,
   - chạy **`doctor`** để kiểm tra và chỉ ra còn thiếu gì.
3. Bỏ tài nguyên kênh vào `assets/` (xem mục 3). Chạy `python -m autovideo doctor` đến khi báo ✅.
4. Xem trước nhận diện kênh: `python -m autovideo brand --real`, rồi mở `output/brand_preview/index.jpg`.
   Chỉnh màu, mascot, font trong `config.yaml` cho tới khi ưng ý. Đây là bước quan trọng nhất để kênh trông chuyên nghiệp.

macOS/Linux: `pip install -r requirements.txt && python scripts/get_fonts.py && python -m autovideo setup`.

### Khóa API cần có

`setup` hỏi đúng những khóa bạn cần và lưu vào `.env`.

| Khóa | Dùng cho | Lấy ở đâu |
|---|---|---|
| `ANTHROPIC_API_KEY` | dịch, chấm điểm, viết hook/tiêu đề (Claude) | console.anthropic.com |
| `GEMINI_API_KEY` | vẽ ảnh bằng Imagen (hoặc dịch bằng Gemini) | aistudio.google.com |
| `GROQ_API_KEY` | bóc băng trên cloud (máy yếu), có gói miễn phí | console.groq.com |
| `GOOGLE_TTS_API_KEY` | giọng Google Chirp 3 HD | Google Cloud Console → Text-to-Speech API |
| `ELEVENLABS_API_KEY` | giọng ElevenLabs (tùy chọn) | elevenlabs.io |
| `TELEGRAM_BOT_TOKEN` | duyệt bằng điện thoại | @BotFather trên Telegram |

## 2. Dùng hằng ngày

**Cách khuyên dùng:** để bot chạy thường trực. Tạo shortcut tới `scripts\start_bot.bat` trong thư mục Startup (`Win+R` → `shell:startup`).

- **Mỗi đêm (`review.daily_run`)**, bot tự chạy một lượt:
  - tìm truyện theo chủ đề và loại truyện yếu,
  - làm video, gửi từng video về Telegram.
- **Trên điện thoại, mỗi video bạn nhận được:**
  1. Thumbnail kèm điểm truyện và tóm tắt một câu. Hai phương án thumbnail/tiêu đề còn lại có nút **Chọn phương án**.
  2. **Clip TikTok** (chính là hook): xem để duyệt hook, giữ để lưu về máy rồi đăng TikTok. Kèm caption để sao chép.
  3. Một đoạn giữa video để kiểm tra giọng, nhạc và hình.
  4. File toàn văn bản dịch.
  5. Tiêu đề, mô tả có mục lục, tag, bình luận ghim, và nút **✅ Đăng ngay · 🕒 Hẹn giờ · ✏️ Sửa tiêu đề · 🗑 Bỏ**.
- **Bấm Đăng hoặc Hẹn giờ**, PC sẽ:
  - upload video dài cùng thumbnail,
  - thêm video vào playlist của chủ đề,
  - đăng Shorts có link sang video dài,
  - gửi lại bình luận để bạn dán và ghim.
- **Lệnh gõ cho bot:**
  - `/run [chủ_đề]`: chạy ngay
  - `/status`: tình trạng máy và video
  - `/pending`: video đang chờ duyệt
  - `/report`: báo cáo kênh. Báo cáo cũng tự gửi mỗi tuần.

**Làm thủ công một video từ truyện bạn chọn:**

```bash
python -m autovideo make "https://www.bilibili.com/video/BV..." --topic pha_an_kinh_di --export
python -m autovideo make truyen.txt --topic hai_huoc_gia_dinh --export     # .txt tiếng Trung hoặc tiếng Việt
```

**Thư mục `inbox/`:** thả file `.txt` truyện bạn tự tuyển vào `inbox/<tên_chủ_đề>/`. Lượt chạy tự động sẽ làm các file này **trước** truyện tự tìm. Đây là nguồn truyện chất lượng nhất.

| Lệnh | Việc |
|---|---|
| `python -m autovideo setup` | cài đặt hỏi đáp (chạy lại để đổi lựa chọn) |
| `python -m autovideo doctor [--online]` | kiểm tra cài đặt; `--online` gọi thử thật từng dịch vụ |
| `python -m autovideo brand [--real]` | xem trước thumbnail và clip TikTok mọi chủ đề |
| `python -m autovideo voices --engine google` | liệt kê giọng tiếng Việt |
| `python -m autovideo auto [--dry-run] [--topic X]` | chạy một lượt tự động |
| `python -m autovideo make <nguồn> [--topic X] [--export]` | làm video từ nguồn bạn chọn |
| `python -m autovideo make <nguồn> --stages package,render` | làm lại vài bước (xóa file đầu ra của bước đó trước) |
| `python -m autovideo bot` | bot Telegram thường trực |
| `python -m autovideo report` | báo cáo view và giữ chân theo chủ đề |

## 3. Tài nguyên kênh (`assets/`)

| Đường dẫn | Nội dung | Ghi chú |
|---|---|---|
| `assets/templates/mascot.png` | mascot/logo kênh, PNG trong suốt | hiện trên mọi thumbnail, giúp người xem nhận ra kênh |
| `assets/fonts/` | `python scripts/get_fonts.py` | Anton, Oswald, Baloo 2; có tiếng Việt, giấy phép OFL |
| `assets/music/` | ≥ 5 bài nhạc nền **không bản quyền** | YouTube Audio Library là nguồn an toàn nhất, nhất là khi đăng TikTok |
| `assets/footage/<tone>/` | ≥ 8 clip cùng tone (chủ đề dùng `mode: footage`) | dùng footage bạn có quyền sử dụng |
| `assets/overlays/` | hiệu ứng nền đen (bụi, mưa, khói), tùy chọn | |

## 4. Công cụ làm gì để video có view

| Khâu | Cách làm | Vì sao |
|---|---|---|
| **Chọn truyện** | LLM chấm 6 tiêu chí (hook, tiền đề, twist, cảm xúc, nhịp, hợp khẩu vị Việt), kiểm tra truyện trọn vẹn và an toàn quảng cáo. Truyện dưới `quality.min_score` bị loại trước khi dịch. | Truyện dở thì đóng gói đẹp mấy cũng không giữ chân được người xem; loại sớm thì không tốn phí dịch, đọc, render. |
| **Dịch** | Trích bảng nhân vật (tên Hán Việt, giới tính, quan hệ, gợi ý xưng hô) trước khi dịch. Mỗi đoạn qua QA (sót chữ Hán, bị lược, bị bịa, bị từ chối) và được dịch lại nếu lỗi. | Xưng hô sai là lỗi khiến người nghe bỏ ngay. |
| **Hook 2–5 phút** | Chọn khoảnh khắc gay cấn nhất. Câu đầu gây sốc trong 5 giây, cứ 30–60 giây có chi tiết mới, dừng ở cao trào. Giọng vào ngay từ giây 0,5. | Phút đầu quyết định thời lượng xem trung bình; hook cũng là clip TikTok/Shorts. |
| **Đóng gói** | 3 phương án tên truyện (mỗi cái một góc gây tò mò) và 3 thumbnail; tiêu đề theo mẫu kênh; mô tả có 2 dòng đầu gây tò mò, mục lục chương lấy từ timeline giọng đọc thật, CTA, 3 hashtag; bình luận ghim kích thích tranh luận. | CTR và tương tác. 3 thumbnail dùng được cho *Thử nghiệm & so sánh* của YouTube Studio. |
| **Phễu** | TikTok (hook đầy đủ, phụ đề cháy chữ, banner sang YouTube) và Shorts (cắt ở câu treo, ≤ 3 phút) tự đăng kèm link sang video dài. | Kênh mới gần như không có lượt hiển thị; clip ngắn mang người xem đầu tiên về. |
| **Đo và điều chỉnh** | Báo cáo view/ngày và % giữ chân theo chủ đề, cảnh báo video giữ chân < 25%. `auto.adaptive` tự dồn sản lượng cho chủ đề tốt nhất, vẫn chừa phần thử chủ đề mới. | Làm nhiều cái đang chạy tốt, bỏ cái không chạy. |

## 5. Chi phí ước tính cho một video khoảng 1 tiếng

| Hạng mục | Lựa chọn | Ước tính |
|---|---|---|
| LLM (chấm điểm, dịch, metadata, hook) | Claude Opus 5.5 / Sonnet 5.5 | ~1–1,5 USD / ~0,6 USD |
| Giọng đọc | Edge / Google Chirp 3 HD / ElevenLabs | 0 / ~1–2 USD / cao (tùy gói) |
| Ảnh | Imagen, 1–6 ảnh | ~0,04 USD/ảnh |
| Bóc băng | Groq / máy bạn | rất thấp / 0 |

Đây là số ước tính. Chi phí LLM thật của từng video được ghi trong `cost.json`, và LLM có dùng prompt caching cho toàn văn truyện. Truyện bị loại chỉ tốn phí bóc băng và một lần chấm điểm.

## 6. Cấu hình

Mọi tùy chọn và giải thích nằm trong **`config.example.yaml`**. `config.yaml` của bạn chỉ chứa những gì khác mặc định. Các nhóm chính:

- `channel`: tên, mẫu tiêu đề, link đăng ký, chân mô tả
- `topics`: từng chủ đề có từ khóa, nguồn, giọng, màu, phong cách ảnh, kiểu hình nền
- `quality`: điểm tối thiểu, bắt buộc truyện trọn vẹn và an toàn quảng cáo
- `hook`, `tiktok`, `shorts`: độ dài hook, banner, tự đăng Shorts
- `review`, `youtube`: Telegram, lịch chạy, giờ đăng, playlist theo chủ đề
- `auto`: số video mỗi lượt, `adaptive`, `inbox`

**Máy yếu:** chọn "máy yếu" trong `setup`, hoặc dùng `-c config.lite.yaml`. Khi đó bóc băng và vẽ ảnh chạy trên cloud, còn ảnh tĩnh chỉ render một vòng zoom rồi nối lặp. Trên CPU 4 nhân, 5 phút hình mất 26 giây so với 112 giây khi render đầy đủ.

## 7. Upload YouTube tự động (`youtube.enabled: true`)

1. Google Cloud Console → tạo project → bật **YouTube Data API v3** và **YouTube Analytics API**.
2. OAuth consent screen: chọn External, thêm email kênh vào Test users, rồi **Publish app** (để chế độ Testing thì Google bắt đăng nhập lại mỗi 7 ngày).
3. Credentials → OAuth client ID → **Desktop app** → tải JSON về `secrets/client_secret.json`.
4. Lần đầu bấm Đăng, PC mở trình duyệt để bạn đăng nhập kênh.
5. Kênh cần xác minh số điện thoại mới đặt được thumbnail tùy chỉnh.

> ⚠️ **Thử 1 video trước.** Theo chính sách YouTube API (bản mới nhất chưa được kiểm chứng khi viết công cụ này), video upload từ project chưa qua *audit* có thể bị **khóa ở chế độ Riêng tư**. Nếu bị khóa, gửi đơn audit (miễn phí). Trong lúc chờ, để `youtube.enabled: false`: nút ✅ Duyệt sẽ chuyển video vào `ready/_approved/` để bạn tự đăng.

## 8. Thành phẩm

`ready/<ngày>_<tiêu-đề>/` gồm:

| Nhóm | File |
|---|---|
| Video | `video.mp4`, `tiktok.mp4`, `short.mp4` |
| Thumbnail | `thumbnail.jpg`, `thumbnail_2.jpg`, `thumbnail_3.jpg` |
| Chữ để đăng | `title.txt`, `titles.json`, `description.txt`, `tags.txt`, `pinned_comment.txt`, `tiktok_caption.txt` |
| Tham khảo | `script_vi.txt`, `analysis.json` (điểm truyện), `cost.json`, `source_info.json` |

File trung gian của từng video nằm trong `output/<slug>/`. Mỗi bước tự bỏ qua nếu đã có kết quả, nên bị ngắt giữa chừng chỉ cần chạy lại lệnh.

## 9. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Không biết thiếu gì | `python -m autovideo doctor --online` |
| "Truyện không đạt" quá nhiều | thêm từ khóa hoặc nguồn, thả truyện tuyển vào `inbox/`, hoặc hạ `quality.min_score` (không nên dưới 6) |
| Hook dài hoặc ngắn quá | log cảnh báo; chỉnh `hook.words_per_minute` theo tốc độ giọng bạn dùng |
| Bản dịch có đoạn lỗi | xem `output/<slug>/translate_qa.json`; xóa `story_vi.txt` và `translate_progress.json` để dịch lại |
| Muốn đổi tiêu đề/thumbnail sau khi render | xóa `thumbnail*.jpg` rồi chạy `make <nguồn> --stages package` |
| YouTube chặn tải (yêu cầu đăng nhập) | đặt `source.cookies_file` (xuất cookies từ trình duyệt) |

## 10. Phát triển

```bash
python -m pytest -q    # 43 test offline: LLM/TTS giả lập, media sinh bằng FFmpeg, có test end-to-end đủ 7 bước
```

Mã nguồn chính trong `autovideo/`:

| Nhóm | Module |
|---|---|
| Điều phối | `pipeline.py` (7 bước) |
| Nội dung | `analyze.py` (cổng chất lượng), `translate.py`, `hook.py` (hook, TikTok, Shorts), `package.py` (chương, mô tả, phương án) |
| Âm thanh | `tts.py` |
| Hình và video | `thumbnail.py`, `render.py` |
| Đăng và theo dõi | `review.py` (bot), `youtube.py`, `analytics.py` |
| Dễ dùng | `setup_wizard.py`, `doctor.py`, `brand.py` |

Prompt nằm ở `prompts/`, mỗi thể loại một file trong `prompts/genres/`.
