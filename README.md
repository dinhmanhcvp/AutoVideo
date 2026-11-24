# AutoVideo

Pipeline Python tự động: **audio truyện tiếng Trung → video truyện audio tiếng Việt 16:9** cho YouTube
(cổ trang, tu tiên, ngôn tình, tâm sự đêm khuya).

```
yt-dlp ──► Faster-Whisper ──► LLM dịch + biên tập ──► edge-tts / F5-TTS ──► ComfyUI + Pillow ──► FFmpeg
 fetch        asr               translate             tts                  thumbnail            render
```

Thay vì ghép nguyên pyvideotrans / MoneyPrinterTurbo (nặng, khó chỉnh prompt), repo này viết lại
đúng phần lõi của các công cụ đó thành các module nhỏ, gọi trực tiếp thư viện gốc
(`yt-dlp`, `faster-whisper`, `edge-tts`, FFmpeg) — dễ chỉnh prompt dịch và kiểm soát chất lượng.

## Cài đặt

```bash
# Cần FFmpeg (bản có h264_nvenc nếu dùng GPU NVIDIA) và Python 3.10+
pip install -r requirements.txt
cp config.example.yaml config.yaml

export ANTHROPIC_API_KEY=...     # nếu llm.provider: anthropic
export GEMINI_API_KEY=...        # nếu llm.provider: gemini
```

## Chế độ tự động hoàn toàn

Khai báo các **chủ đề** trong `config.yaml` → `topics:`. Mỗi chủ đề có: từ khóa tiếng Trung, các nguồn tìm
(`bilisearch` = Bilibili, `ytsearch` = YouTube), độ dài truyện chấp nhận, thể loại văn phong (`genre`),
giọng đọc/tốc độ/cao độ riêng (`tts`), và cách dựng hình riêng (`render`: footage tone nào, ảnh minh họa
hay chỉ dùng thumbnail).

```bash
python -m autovideo auto -c config.yaml --dry-run          # xem trước sẽ lấy truyện nào
python -m autovideo auto -c config.yaml                    # chạy thật, mọi chủ đề
python -m autovideo auto -c config.yaml --topic tam_su_dem_khuya --per-topic 2
```

Mỗi lần chạy, với từng chủ đề:
1. Tìm trên mọi (từ khóa × nguồn), xen kẽ nguồn, lọc theo độ dài.
2. Bỏ truyện đã làm (`output/history.json`), kể cả bản re-up trùng tiêu đề ở nguồn khác; truyện lỗi quá `max_attempts` lần thì bỏ qua.
3. Chạy trọn pipeline với giọng và văn phong của chủ đề.
4. Gom thành phẩm vào **`ready/<ngày>_<tiêu-đề>/`**: `video.mp4`, `thumbnail.jpg`, `title.txt`, `description.txt`, `tags.txt`, `source_info.json`. Bạn chỉ việc mở thư mục và đăng.

**Lên lịch hằng ngày trên Windows** (ví dụ 2 giờ sáng, lúc PC rảnh GPU):

```bat
schtasks /Create /TN AutoVideo /SC DAILY /ST 02:00 /TR "C:\duong-dan\AutoVideo\scripts\run_auto.bat"
```

Log ghi ở `logs\auto.log`.

### Máy yếu: dùng `config.lite.yaml`

```bash
pip install PyYAML Pillow yt-dlp edge-tts requests anthropic google-genai   # không cần faster-whisper/torch
set GROQ_API_KEY=...  &  set ANTHROPIC_API_KEY=...  &  set GEMINI_API_KEY=...
python -m autovideo auto -c config.lite.yaml
```

| Việc | Máy mạnh (`config.example.yaml`) | Máy yếu (`config.lite.yaml`) |
|---|---|---|
| Nhận giọng tiếng Trung | Faster-Whisper large-v3 trên GPU | **Groq** Whisper large-v3 (cloud, có free tier) hoặc Gemini |
| Dịch | API Claude/Gemini | như bên trái |
| Đọc tiếng Việt | edge-tts / F5-TTS local | edge-tts (server Microsoft) |
| Vẽ ảnh | ComfyUI local | **Google Imagen** (cloud, trả phí theo ảnh, khoảng 1.000đ/ảnh) |
| Render hình | NVENC | Chỉ render 1 chu kỳ zoom mỗi ảnh rồi nối lặp, không encode lại |

Đo trên CPU 4 nhân, không GPU, ảnh tĩnh 1080p: dựng 5 phút hình mất **26 giây** ở chế độ lặp (gần như
không tăng theo độ dài video), so với **112 giây** khi render đầy đủ (~22 phút cho video 1 tiếng).
Chế độ `footage` cũng nhẹ: mỗi clip chỉ chuẩn hóa 1 lần rồi cache, các video sau nối bằng stream copy.

Mẹo thêm: hạ `render.resolution` xuống `[1280, 720]`; để `auto.per_topic: 1` và lên lịch chạy ban đêm.

### 3 kiểu hình nền (`render.mode`, đặt riêng theo chủ đề)

| mode | Hình | Hợp với |
|---|---|---|
| `footage` | Ghép footage nấu ăn/chill cùng tone (`assets/footage/<tone>/`), xáo thứ tự, lặp đủ độ dài, áp LUT chung | tâm sự, hiện đại |
| `still` | 5–10 ảnh minh họa theo diễn biến truyện, Ken Burns + overlay bụi/mưa | cổ trang, tu tiên |
| `thumbnail` | Chỉ dùng chính thumbnail (có tiêu đề) làm nền, zoom chậm | nhanh, nhẹ nhất |

## Chạy thủ công

```bash
# 1 video từ URL (Bilibili / Douyin / YouTube / Ximalaya…)
python -m autovideo run "https://www.bilibili.com/video/BVxxxx" -c config.yaml

# Đã có text tiếng Trung cào từ web truyện → bỏ qua ASR (sạch và nhanh hơn)
python -m autovideo run truyen.txt -c config.yaml --genre co_trang

# Hàng loạt
python -m autovideo run --batch urls.txt -c config.yaml
python -m autovideo run --keyword "古风 有声小说" --keyword "深夜情感电台" --limit 3 -c config.yaml

# Chạy lại một vài bước (xóa file đầu ra của bước đó trước)
python -m autovideo run <url> --stages tts,render -c config.yaml
```

Kết quả nằm ở `output/<slug>/`:

| File | Bước |
|---|---|
| `source.m4a`, `source_info.json` | fetch |
| `transcript_zh.json` (timestamp), `source_zh.txt` | asr |
| `translate_progress.json`, `story_vi.txt`, `metadata.json`, `youtube_description.txt`, `script_vi.txt` (intro + truyện + outro) | translate |
| `tts/*.wav`, `voice.wav` | tts |
| `thumb_bg.png`, `thumbnail.jpg`, `scenes/*.png` | thumbnail |
| `render/mix.m4a`, `render/bg.mp4`, **`video.mp4`** | render |

Mỗi bước tự bỏ qua nếu file đầu ra đã có ⇒ bị ngắt giữa chừng (mất mạng, hết quota API) chỉ cần
chạy lại đúng lệnh. Dịch được lưu theo từng chunk nên không mất tiền gọi lại đoạn đã dịch.

## Các module

| Module | File | Ghi chú |
|---|---|---|
| 1. Thu thập | `autovideo/fetch.py` | yt-dlp; tìm theo từ khóa với `bilisearch`/`ytsearch`. Nguồn cần đăng nhập: `source.cookies_file`. |
| 1. ASR | `autovideo/asr.py` | Faster-Whisper `large-v3`, VAD, ép xuất giản thể có dấu câu; khoảng lặng dài ⇒ xuống đoạn. |
| 2. Dịch | `autovideo/translate.py`, `prompts/` | Chia chunk ~1500 ký tự, gửi kèm đuôi bản dịch trước + bảng thuật ngữ để giữ xưng hô/tên riêng nhất quán. Prompt thể loại ở `prompts/genres/*.md` — thêm thể loại mới chỉ cần thêm file. |
| 4. Metadata | `prompts/metadata.md` | JSON: `youtube_title`, `description`, `tags`, `thumb_text` (2 dòng), `image_prompt`, `scene_prompts`, `intro`, `outro`. |
| 3. TTS | `autovideo/tts.py` | Chia 200–300 chữ/đoạn ở ranh giới câu. `edge` (HoaiMy/NamMinh, rate/pitch) hoặc `command` để gọi F5-TTS/XTTS-v2 clone giọng. |
| 4. Thumbnail | `autovideo/thumbnail.py`, `autovideo/comfyui.py` | ComfyUI API (Flux/SDXL) → Pillow: gradient tối vùng chữ, layer khung PNG của kênh, chữ tự co cỡ, viền + đổ bóng. Chưa bật ComfyUI thì dùng ảnh gradient giữ chỗ. |
| 5. Render | `autovideo/render.py` | Xem bên dưới. |

### Render (FFmpeg)

- **`mode: footage`** — bốc clip trong `assets/footage/<tone>/` (warm/dark/bright), chuẩn hóa 1 lần
  (scale/crop 16:9, fps, `eq` hạ sáng, LUT `.cube`) và cache ở `assets/footage/.cache/`; mỗi video xáo
  thứ tự khác nhau, không để 1 clip lặp liền nhau, rồi nối bằng stream copy (không encode lại).
- **`mode: still`** — mỗi `scene_prompts` một ảnh, chia đều theo thời lượng; Ken Burns zoom in/out
  dạng cos rất chậm (cảnh chẵn/lẻ ngược chiều), fade giữa cảnh, tùy chọn overlay (bụi/mưa/khói) blend
  `screen`.
- **Âm thanh** — playlist nhạc nền xáo trộn từ `assets/music/`; `ducking: sidechain` (sidechaincompress,
  nhạc tự hạ khi có giọng) hoặc `fixed` (cố định -22 → -25 dB); fade in/out, `loudnorm` -16 LUFS.
- **Encoder** — `auto` thử `h264_nvenc`, không được thì `libx264`.

## Thư mục assets (tự chuẩn bị)

```
assets/
  footage/warm|dark|bright/*.mp4   # footage nấu ăn / phong cảnh có bản quyền
  music/*.mp3                      # nhạc nền có bản quyền / royalty-free
  overlays/dust.mp4                # hiệu ứng nền đen (bụi, mưa, khói)
  templates/frame.png              # khung thumbnail 1280x720 PNG trong suốt (logo, viền)
  fonts/thumb.ttf                  # font Việt hóa
  comfyui_workflow_api.json        # workflow export "API format", có {{PROMPT}} (và {{SEED}})
  voice_ref.wav                    # mẫu giọng 10–30s cho F5-TTS/XTTS
```

## Lưu ý bật kiếm tiền

- Dùng `mode: footage` đã chỉnh màu hoặc `mode: still` với 5–10 cảnh (`render.still.scenes`) — tránh 1 ảnh tĩnh cho cả video.
- Giữ `channel.intro`/`channel.outro: true` để có lời dẫn và lời bình riêng của kênh (original commentary).
- Bạn chịu trách nhiệm về bản quyền nội dung truyện gốc, footage và nhạc nền.

## Test

```bash
python -m pytest -q     # offline: giả lập LLM, sinh media bằng FFmpeg lavfi
```
