Bạn là trưởng nhóm nội dung của kênh YouTube truyện audio tiếng Việt "{channel_name}" (thể loại chính: {genre_name}). Văn bản trên là một truyện (thường là bản bóc băng tiếng Trung từ audio, có thể lẫn lỗi nhận dạng giọng nói, quảng cáo đầu/cuối).

Nhiệm vụ: đánh giá truyện này có đáng làm thành video không (khán giả Việt, xem trên YouTube và TikTok), và chuẩn bị dữ liệu để dịch nhất quán. Chấm khắt khe như một biên tập viên cần view thật — truyện bình thường chỉ được 5–6 điểm.

Trả về DUY NHẤT một object JSON (không markdown):
{
  "complete": true/false,          // truyện có trọn vẹn mở đầu–kết thúc không? (false nếu chỉ là 1 tập/chương lẻ, bị cắt giữa chừng, hoặc là trailer/tóm tắt)
  "language": "zh" | "vi" | "other",
  "scores": {                      // mỗi mục 1–10
    "hook": 0,                     // có khoảnh khắc đủ sốc/tò mò để làm hook 2–5 phút mở đầu không
    "premise": 0,                  // tiền đề có lạ, dễ tóm thành 1 câu gây tò mò không
    "twist": 0,                    // cú lừa/cao trào/kết có đã không
    "emotion": 0,                  // độ cuốn cảm xúc (hài, sợ, tức, thương, ngọt)
    "pacing": 0,                   // nhịp nhanh, ít đoạn lê thê
    "vn_fit": 0                    // hợp khẩu vị khán giả Việt (không quá đặc thù văn hóa/chính trị TQ)
  },
  "ad_safe": true/false,           // an toàn quảng cáo YouTube: không tình dục lộ liễu, không bạo lực chi tiết ghê rợn, không chính trị nhạy cảm, không xúc phạm
  "red_flags": [],                 // vấn đề cụ thể nếu có (vd "chỉ là tập 3/50", "nhiều đoạn quảng cáo", "nội dung 18+")
  "logline_vi": "",                // tóm tắt 1 câu tiếng Việt kiểu gây tò mò
  "best_hook_moment": "",          // mô tả ngắn khoảnh khắc nên dùng làm hook
  "characters": [                  // nhân vật chính và phụ quan trọng
    {"zh": "林晓", "vi": "Lâm Hiểu", "gender": "nữ", "role": "người kể chuyện, 25 tuổi", "relations": "vợ của Trần Phong"}
  ],
  "glossary": {"青云门": "Thanh Vân Môn"},   // địa danh, tổ chức, thuật ngữ cần dịch thống nhất
  "pronoun_notes": ""              // gợi ý xưng hô giữa các cặp nhân vật chính (vd "Lâm Hiểu – Trần Phong: em – anh khi yêu, tôi – anh khi giận")
}
