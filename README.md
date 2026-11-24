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

## Chạy

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
