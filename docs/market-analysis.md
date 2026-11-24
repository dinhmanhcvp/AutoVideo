# Phân tích thị trường truyện audio tiếng Việt trên YouTube — 24/11/2026

> Chạy lại bất cứ lúc nào: `python -m autovideo market` (kết quả trong `output/market/`). Nên chạy hằng tháng: xu hướng ngách thay đổi nhanh.

## Cách đo

- **12 ngách**, mỗi ngách tìm bằng 3 từ khóa người Việt hay gõ (ví dụ "truyện tổng tài", "truyện ma có thật", "tâm sự đêm khuya").
- Chỉ tính **video dài trên 20 phút đăng trong 31 ngày gần nhất**, đúng định dạng công cụ làm ra. Mỗi từ khóa lấy cả danh sách *xem nhiều nhất tháng* lẫn *liên quan nhất*.
- Tách riêng kênh **review phim ngắn Trung Quốc**. Loại kênh này lẫn nhiều vào kết quả tìm kiếm nhưng không phải truyện audio.
- Các chỉ số:
  - **Trung vị view/ngày**: độ đều.
  - **P75**: mức trần khá.
  - **% trúng**: tỷ lệ video đạt ≥ 1.000 view/ngày.
  - **Kênh trúng**: số kênh *khác nhau* có video trúng. Càng nhiều nghĩa là cầu càng rộng và kênh mới càng dễ vào.

**Giới hạn cần biết:**
- Kết quả tìm kiếm ưu tiên video đang thắng, nên các số này cao hơn mức trung bình của một kênh mới. Hãy dùng chúng để **so sánh giữa các ngách**, đừng coi là kỳ vọng tuyệt đối.
- Mỗi lượt tìm chỉ lấy trang đầu (~20 video), và đây là ảnh chụp một thời điểm.
- Video vừa đăng vài giờ được tính tối thiểu 0,5 ngày, nên có thể làm view/ngày cao vọt.

## Kết quả

| # | Ngách | Video mẫu | Trung vị view/ngày | P75 | % trúng | Kênh trúng | Độ dài TV | Điểm |
|---|---|---|---|---|---|---|---|---|
| 1 | Drama gia đình, mẹ chồng nàng dâu, ngoại tình | 25 | 7.455 | 14.842 | 100% | 20/20 | 61' | **97.4** |
| 2 | Tâm sự đêm khuya, chuyện đời thật | 81 | 5.388 | 11.030 | 91% | 38/42 | 128' | **93.4** |
| 3 | **Ngôn tình hiện đại / tổng tài** | 53 | 5.240 | 8.616 | 92% | 27/30 | 66' | **93.0** |
| 4 | Truyện ma, kinh dị, tâm linh | 71 | 6.010 | 13.666 | 76% | 21/27 | 62' | **90.4** |
| 5 | Phá án, trinh thám, hình sự | 61 | 3.112 | 5.736 | 79% | 24/28 | 65' | **87.0** |
| 6 | Cổ trang, cung đấu, ngôn tình cổ đại | 59 | 2.947 | 5.082 | 73% | 21/27 | 60' | **85.1** |
| 7 | Xuyên không, hệ thống, xuyên sách | 24 | 2.540 | 9.096 | 71% | 16/23 | 174' | **85.1** |
| 8 | Thanh xuân, thầm thích, học đường | 66 | 1.697 | 5.003 | 58% | 21/42 | 50' | **79.2** |
| 9 | Nữ cường, vả mặt, trọng sinh báo thù | 67 | 1.320 | 3.253 | 61% | 23/31 | 57' | **78.2** |
| 10 | Hài hước, "mỏ hỗn", sảng văn đời thường | 71 | 1.468 | 5.140 | 56% | 20/33 | 60' | **78.2** |
| 11 | Tu tiên, tiên hiệp, huyền huyễn | 61 | 426 | 1.780 | 33% | 15/36 | 342' | **65.7** |
| 12 | Truyện ngắn "Zhihu" | 71 | 134 | 1.127 | 25% | 13/33 | 42' | **58.5** |

## Đọc kỹ từng ngách top (điểm cao chưa chắc đã hợp với bạn)

Điểm thị trường chỉ là một nửa. Nửa còn lại là **ngách đó có hợp với công cụ của bạn không**: nguồn truyện tiếng Trung, giọng AI, sản xuất đều đặn.

| Ngách | Thị trường | Hợp công cụ? | Lý do |
|---|---|---|---|
| Drama gia đình (#1) | rất tốt, nhưng mẫu nhỏ (25 video) | ⚠ trung bình | Nhiều video top thực chất là **ngôn tình hào môn** (Mèo Cưng Audio, Mộng Lạc Audio) bị trùng từ khóa. Phần còn lại là "chuyện đời" bối cảnh Việt. |
| Tâm sự đêm khuya (#2) | rất rộng (38 kênh trúng), video 2–3 tiếng | ✘ thấp | Truyện **bối cảnh Việt Nam**, khán giả lớn tuổi ("Đại tá gặp lại tình cũ…", "Ông bà bán nhà ở quê…"). Dịch từ truyện Trung sẽ lạc bối cảnh. Nhiều kênh đang sản xuất kiểu công thức hàng loạt, **rủi ro cao với chính sách *inauthentic content***. |
| **Ngôn tình hiện đại (#3)** | rất đều (92% trúng), 27 kênh trúng | ✅ **cao nhất** | Video top **chính là truyện ngắn Trung dịch** (Tạ Tổng, Kỷ Tổng, thái tử gia…), dài 50–60 phút, khớp đúng những gì công cụ làm ra. Nguồn truyện Trung dồi dào nhất. Khán giả nữ trung thành, nghe nhiều video liền. |
| Truyện ma (#4) | cao nhưng **71% view rơi vào 3 kênh** | ✘ thấp | Bị thống trị bởi kênh có **người đọc thật** (Đất Đồng Radio – Nguyễn Huy) với truyện ma Việt. Giọng AI khó cạnh tranh không khí. |
| Phá án (#5) | khá | ⚠ trung bình | Lẫn nhiều thể loại; "vụ án Trung Quốc" có khán giả nhưng mỏng hơn. |
| Cổ trang / cung đấu (#6) | khá đều, 21 kênh trúng | ✅ tốt (ngách phụ) | Cũng là truyện Trung dịch, **cùng tệp khán giả** với ngôn tình hiện đại, nên mở rộng sang rất tự nhiên. |
| Tu tiên, "Zhihu" (#11, #12) | thấp | — | Tu tiên là truyện siêu dài, người nghe tìm kênh lớn có sẵn. "Zhihu" không phải từ khóa người xem gõ (các kênh không ghi nguồn Zhihu). |

## Công thức tiêu đề (ngôn tình hiện đại + drama + nữ cường, 136 video)

So nhóm **≥ 5.000 view/ngày** (48 video) với nhóm **< 1.000 view/ngày** (30 video):

| Dấu hiệu | Nhóm cao | Nhóm thấp | Kết luận |
|---|---|---|---|
| Có chữ "Tôi" (ngôi thứ nhất) | 35% | 10% | **Viết tên truyện theo ngôi nữ chính** |
| Có tiền tố "[Truyện Audio]" | 65% | 33% | Giữ mẫu tiêu đề hiện tại của công cụ |
| Có "Tổng", "thái tử gia", "thiếu gia", "hào môn" | 8% / 6% / 6% / 4% | 0% | Gọi nam chính bằng **Họ + Tổng** / thái tử gia |
| Có "vả mặt", "trọng sinh", "trà xanh" | 8% / 2% / 6% | 23% / 20% / 17% | **Từ sáo đã bão hòa**, đừng mở đầu tiêu đề bằng chúng |
| Độ dài trung vị | 55 phút | 63 phút | Gọn 45–60 phút tốt hơn |
| Đánh số tập "Số N" | 17% | 7% | Giữ nhãn số tập |

Một số tiêu đề top tháng này (để tham khảo cấu trúc, **đừng chép**):
- "Sau Ba Lần Từ Chối Tôi Buông Tay" (~36.800 view/ngày)
- "Vợ Nuôi Từ Bé Bỗng Nhiên Né Tránh, Thái Tử Gia Hoảng Rồi" (~30.900 view/ngày)
- "Vợ Yêu Bỗng Nhiên Ngoan Ngoãn, Kỷ Tổng Ghen Điên Rồi" (~29.600 view/ngày)
- "Tôi Đòi Ly Hôn, Tạ Tổng Lại Vừa Khóc Vừa Bám Dính Không Buông" (~17.100 view/ngày)

Cấu trúc chung: **[tình huống/hành động của nữ chính] + [phản ứng mất kiểm soát của nam chính quyền lực]**, tạo tò mò "vì sao anh ta lại như vậy?".

## Quyết định

**Ngách chính: Ngôn tình hiện đại – hôn nhân hào môn / tổng tài** (`ngon_tinh_hao_mon`, đã bật).
- Văn phong dịch riêng trong `prompts/genres/ngon_tinh.md`: ngôi thứ nhất nữ chính, xưng hô theo diễn biến tình cảm, giữ danh xưng "Hoắc Tổng", "thái tử gia", "bạch nguyệt quang", lược cảnh nhạy cảm để an toàn quảng cáo.
- Công thức tiêu đề ở trên được đưa vào `title_style` của chủ đề. LLM đặt 3 phương án tên theo công thức này.
- Nguồn tìm truyện: từ khóa tiếng Trung 豪门 甜宠 / 先婚后爱 / 追妻火葬场 / 霸总 离婚, truyện dài 25–90 phút.
- Thumbnail tông hồng – đỏ rượu, tranh minh họa kiểu manhua (không dùng ảnh người thật). Giọng nữ, đọc gần nhịp bình thường (rate −3%).

**Ngách phụ (đang tắt): Ngôn tình cổ đại – cung đấu** (`ngon_tinh_co_dai`). Bật khi ngách chính đã có view đều (sau khoảng 4–6 tuần). Ngách này cùng tệp khán giả, nên kênh không bị loãng.

**Không chọn:**
- Tâm sự đêm khuya, truyện ma: lệch nguồn, giọng AI yếu thế, rủi ro chính sách.
- Tu tiên: video siêu dài, kênh lớn đã chiếm.
- Hài "mỏ hỗn": trung vị thấp, một kênh lớn chiếm phần đáng kể.

## Cạnh tranh và cách khác biệt

Ngách chính có ít nhất 15 kênh đang ra video ≥ 5.000 view/ngày. Cầu lớn nhưng cũng nhiều đối thủ. Để nổi bật:
1. **Giọng đọc khác** (Google Chirp 3 HD hoặc ElevenLabs), thay vì HoaiMy mà phần lớn kênh đang dùng.
2. **Hook 2–5 phút ở đầu.** Đa số kênh đối thủ mở bằng lời chào và đọc từ đầu truyện.
3. **Chọn truyện khắt khe hơn:** đặt `quality.min_score: 7` khi nguồn đã dồi dào.
4. **Nhận diện kênh riêng:** mascot và tông màu riêng. Đừng bắt chước mascot mèo, dứa… của kênh khác.
5. **Đều đặn:** 1 video/ngày cùng giờ, cộng TikTok và Shorts mỗi ngày.

*Lưu ý bản quyền:* ngách này dùng truyện ngắn Trung Quốc có chủ sở hữu, xem mục 8 trong [PLAYBOOK.md](../PLAYBOOK.md).
