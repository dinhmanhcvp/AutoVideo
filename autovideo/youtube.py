"""Upload / xuất bản lên YouTube qua YouTube Data API v3 (OAuth, lần đầu đăng nhập trên PC).

LƯU Ý: Google giới hạn project API chưa qua "audit": video upload qua API có thể bị khóa ở chế độ
Riêng tư. Xem README mục "YouTube API" để gửi yêu cầu audit trước khi bật đăng công khai tự động.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCOPES = [
    "https://www.googleapis.com/auth/youtube",               # upload, sửa trạng thái, playlist
    "https://www.googleapis.com/auth/yt-analytics.readonly",  # % giữ chân người xem cho báo cáo
]


def credentials(cfg: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token = Path(cfg["token_file"])
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:  # chỉ lần đầu: mở trình duyệt trên PC để đăng nhập kênh
        flow = InstalledAppFlow.from_client_secrets_file(cfg["client_secrets"], SCOPES)
        creds = flow.run_local_server(port=0)
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def service(cfg: dict):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=credentials(cfg), cache_discovery=False)


def analytics_service(cfg: dict):
    from googleapiclient.discovery import build

    return build("youtubeAnalytics", "v2", credentials=credentials(cfg), cache_discovery=False)


def add_to_playlist(yt, playlist_id: str, video_id: str) -> None:
    yt.playlistItems().insert(part="snippet", body={"snippet": {
        "playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()


def upload(yt, video: Path, thumb: Path, meta: dict, cfg: dict, publish_at: datetime | None = None) -> str:
    """Upload video. publish_at=None => công khai ngay; có giá trị => hẹn giờ (riêng tư tới lúc đó)."""
    from googleapiclient.http import MediaFileUpload

    status = {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    if publish_at:
        status = {"privacyStatus": "private", "publishAt": publish_at.isoformat(), "selfDeclaredMadeForKids": False}
    if cfg.get("declare_synthetic", True):
        status["containsSyntheticMedia"] = True  # khai báo nội dung có giọng AI
    body = {
        "snippet": {
            "title": meta["youtube_title"][:100],
            "description": meta.get("description_full", meta.get("description", ""))[:5000],
            "tags": meta.get("tags", [])[:30],
            "categoryId": str(cfg.get("category_id", 24)),  # 24 = Entertainment
            "defaultLanguage": "vi",
            "defaultAudioLanguage": "vi",
        },
        "status": status,
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=16 * 1024 * 1024, resumable=True))
    response, retries = None, 0
    while response is None:
        try:
            _, response = req.next_chunk()
        except Exception:  # mạng chập chờn: upload resumable cho phép gửi tiếp
            retries += 1
            if retries > 8:
                raise
            time.sleep(min(60, 2 ** retries))
    video_id = response["id"]
    try:
        yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg")).execute()
    except Exception as e:  # kênh chưa xác minh số điện thoại thì không đặt được thumbnail tùy chỉnh
        print(f"  [youtube] không đặt được thumbnail: {e}")
    return video_id


def delete(yt, video_id: str) -> None:
    yt.videos().delete(id=video_id).execute()


def next_slot(slots: list[str], tz: str, taken: list[str], now: datetime | None = None,
              min_lead_minutes: int = 30) -> datetime:
    """Khung giờ đăng trống tiếp theo (vd ["19:30", "21:00"]) theo múi giờ kênh, bỏ các giờ đã hẹn."""
    zone = ZoneInfo(tz)
    now = (now or datetime.now(zone)).astimezone(zone)
    taken_set = {datetime.fromisoformat(t).astimezone(zone).replace(second=0, microsecond=0) for t in taken}
    for day in range(60):
        d = (now + timedelta(days=day)).date()
        for s in sorted(slots):
            h, m = map(int, s.split(":"))
            cand = datetime(d.year, d.month, d.day, h, m, tzinfo=zone)
            if cand >= now + timedelta(minutes=min_lead_minutes) and cand not in taken_set:
                return cand
    raise RuntimeError("Không còn khung giờ trống trong 60 ngày tới")
