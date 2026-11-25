"""Giao diện web của AutoVideo: `python -m autovideo ui` rồi mở trình duyệt.

Chỉ dùng thư viện chuẩn của Python. Mặc định chỉ nghe ở 127.0.0.1 (chỉ máy bạn truy cập).
`--lan`: mở cho điện thoại cùng Wi‑Fi, mọi API khi đó cần mã truy cập in ra màn hình lúc khởi động.

Việc nặng (tự động, tạo video, khảo sát...) chạy bằng tiến trình con `python -m autovideo ...`, nhật ký ghi
ra output/ui_logs/ và hiển thị trực tiếp trên giao diện; đóng trình duyệt không làm dừng việc đang chạy.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from ..config import _deep_merge, load_config

STATIC = Path(__file__).resolve().parent / "static"
ENV_KEYS = ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "GOOGLE_TTS_API_KEY",
            "ELEVENLABS_API_KEY", "TELEGRAM_BOT_TOKEN"]
EDITABLE_TEXTS = {"title.txt", "description.txt", "tags.txt", "pinned_comment.txt", "tiktok_caption.txt"}
HEAVY = {"auto", "make"}  # chỉ chạy 1 việc nặng một lúc (tránh tranh GPU/CPU, đánh số tập trùng)


# ====================================================================== việc chạy nền

class Task:
    def __init__(self, kind: str, label: str, log: Path):
        self.id = uuid.uuid4().hex[:8]
        self.kind, self.label, self.log = kind, label, log
        self.started = datetime.now().isoformat(timespec="seconds")
        self.ended: str | None = None
        self.proc: subprocess.Popen | None = None
        self.thread_status: str | None = None  # cho việc chạy bằng luồng (đăng YouTube)

    @property
    def status(self) -> str:
        if self.proc is not None:
            rc = self.proc.poll()
            if rc is None:
                return "running"
            if not self.ended:
                self.ended = datetime.now().isoformat(timespec="seconds")
            return "done" if rc == 0 else "failed"
        return self.thread_status or "running"

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "label": self.label, "status": self.status,
                "started": self.started, "ended": self.ended}


class Tasks:
    def __init__(self, root: Path, log_dir: Path):
        self.root, self.log_dir = root, log_dir
        self.items: dict[str, Task] = {}
        self.lock = threading.Lock()

    def running_heavy(self) -> Task | None:
        return next((t for t in self.items.values() if t.kind in HEAVY and t.status == "running"), None)

    def start(self, kind: str, argv: list[str], label: str) -> Task:
        with self.lock:
            if kind in HEAVY and (busy := self.running_heavy()):
                raise RuntimeError(f"Đang có việc khác chạy: {busy.label}. Đợi xong hoặc bấm Dừng.")
            self.log_dir.mkdir(parents=True, exist_ok=True)
            task = Task(kind, label, self.log_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}.log")
            pkg_parent = str(Path(__file__).resolve().parents[2])  # để `python -m autovideo` chạy ở mọi thư mục
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
                   "PYTHONPATH": os.pathsep.join(filter(None, [pkg_parent, os.environ.get("PYTHONPATH")]))}
            logf = open(task.log, "w", encoding="utf-8")
            task.proc = subprocess.Popen([sys.executable, "-m", "autovideo", *argv], cwd=self.root,
                                         stdout=logf, stderr=subprocess.STDOUT, env=env)
            self.items[task.id] = task
            return task

    def start_thread(self, kind: str, label: str, fn) -> Task:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        task = Task(kind, label, self.log_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}.log")
        task.log.write_text("", encoding="utf-8")

        def run():
            try:
                fn(UILog(task.log))
                task.thread_status = "done"
            except Exception:
                with open(task.log, "a", encoding="utf-8") as f:
                    f.write(traceback.format_exc())
                task.thread_status = "failed"
            task.ended = datetime.now().isoformat(timespec="seconds")

        self.items[task.id] = task
        threading.Thread(target=run, daemon=True).start()
        return task

    def stop(self, task_id: str) -> None:
        t = self.items.get(task_id)
        if t and t.proc and t.proc.poll() is None:
            t.proc.terminate()


class UILog:
    """Thay cho bot Telegram khi thao tác từ giao diện: ghi thông báo vào nhật ký việc."""
    chat_id = "ui"

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def text(self, text: str, buttons=None, **_):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
        return {"message_id": 0}

    def edit_buttons(self, *_, **__):
        return None


# ====================================================================== dữ liệu

class App:
    def __init__(self, root: Path, token: str | None = None):
        self.root = root.resolve()
        self.token = token
        self.tasks = Tasks(self.root, self.root / "output" / "ui_logs")

    # ---- cấu hình
    def cfg(self) -> dict:
        cp = self.root / "config.yaml"
        cfg = load_config(cp if cp.exists() else None)
        for key in ("workdir",):
            cfg[key] = str((self.root / cfg[key]).resolve()) if not Path(cfg[key]).is_absolute() else cfg[key]
        cfg["auto"]["ready_dir"] = str(self.abs(cfg["auto"]["ready_dir"]))
        cfg["review"]["state_file"] = str(self.abs(cfg["review"]["state_file"]))
        cfg["auto"]["history_file"] = str(self.abs(cfg["auto"]["history_file"]))
        return cfg

    def abs(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (self.root / path).resolve()

    def user_config(self) -> dict:
        cp = self.root / "config.yaml"
        return (yaml.safe_load(cp.read_text(encoding="utf-8")) or {}) if cp.exists() else {}

    def save_user_config(self, patch: dict) -> dict:
        cp = self.root / "config.yaml"
        current = self.user_config()
        topics_enabled = patch.pop("topics_enabled", None)
        merged = _deep_merge(current, patch)
        if topics_enabled is not None:
            full = load_config(cp if cp.exists() else None)["topics"]
            merged["topics"] = [{**t, "enabled": bool(topics_enabled.get(t["name"], t.get("enabled", True)))}
                                for t in full]
        if cp.exists():
            shutil.copy(cp, cp.with_suffix(".yaml.bak"))
        cp.write_text("# Sửa từ giao diện AutoVideo — mọi tùy chọn khác xem config.example.yaml\n"
                      + yaml.safe_dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return merged

    def env_status(self) -> dict:
        from ..setup_wizard import read_env

        env = read_env(self.root / ".env")
        return {k: bool(env.get(k) or os.environ.get(k)) for k in ENV_KEYS}

    def save_env(self, values: dict) -> None:
        from ..setup_wizard import read_env, write_env

        path = self.root / ".env"
        env = read_env(path)
        for k, v in values.items():
            if k in ENV_KEYS and isinstance(v, str) and v.strip():
                env[k] = v.strip()
                os.environ[k] = v.strip()  # tiến trình con kế thừa ngay
        write_env(path, env)

    # ---- thành phẩm
    def ready_dir(self) -> Path:
        return Path(self.cfg()["auto"]["ready_dir"])

    def ready_items(self) -> list[dict]:
        from ..review import review_id, reviews_store

        cfg = self.cfg()
        reviews = reviews_store(cfg).load()
        root = self.ready_dir()
        out = []
        groups = [(root, None), (root / "_approved", "approved"), (root / "_rejected", "rejected")]
        for folder, forced in groups:
            if not folder.exists():
                continue
            for d in sorted(folder.iterdir(), reverse=True):
                if not d.is_dir() or d.name.startswith("_") or not (d / "video.mp4").exists():
                    continue
                rec = reviews.get(review_id(d), {})
                out.append(self.item_summary(d, rec, forced))
        return out

    def item_summary(self, d: Path, rec: dict, forced: str | None = None) -> dict:
        def read(name, default=""):
            p = d / name
            return p.read_text(encoding="utf-8") if p.exists() else default

        analysis = json.loads(read("analysis.json", "{}") or "{}")
        cost = json.loads(read("cost.json", "{}") or "{}")
        status = forced or rec.get("status") or "pending"
        return {
            "id": d.name, "path": str(d), "rel": self.rel(d), "title": read("title.txt").strip(),
            "titles": json.loads(read("titles.json", "[]") or "[]"), "status": status,
            "score": analysis.get("score"), "logline": analysis.get("logline_vi", ""),
            "scores": analysis.get("scores", {}), "cost": cost.get("total_usd"),
            "youtube_id": rec.get("youtube_id"), "shorts_id": rec.get("shorts_id"),
            "publish_at": rec.get("publish_at"), "variant": rec.get("variant", 1),
            "files": [f.name for f in sorted(d.iterdir()) if f.is_file()],
            "texts": {n: read(n) for n in sorted(EDITABLE_TEXTS)},
        }

    def find_item(self, item_id: str) -> Path:
        if not re.fullmatch(r"[\w.\-]+", item_id):
            raise ValueError("tên không hợp lệ")
        root = self.ready_dir()
        for folder in (root, root / "_approved", root / "_rejected"):
            if (folder / item_id).is_dir():
                return folder / item_id
        raise FileNotFoundError(item_id)

    def ensure_review(self, d: Path) -> str:
        from ..review import review_id, reviews_store

        cfg = self.cfg()
        rid = review_id(d)
        store = reviews_store(cfg)
        if not store.get(rid):
            store.update(rid, dest=str(d), title=(d / "title.txt").read_text(encoding="utf-8").strip(),
                         topic="", status="pending", message_id=0,
                         created=datetime.now().isoformat(timespec="minutes"))
        return rid

    def rel(self, p: Path) -> str:
        try:
            return str(p.resolve().relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(p)

    # ---- tổng quan
    def overview(self) -> dict:
        cfg = self.cfg()
        items = self.ready_items()
        counts: dict[str, int] = {}
        for it in items:
            counts[it["status"]] = counts.get(it["status"], 0) + 1
        month = datetime.now().strftime("%Y-%m")
        cost_month = round(sum(it["cost"] or 0 for it in items if it["id"].startswith(month)), 2)
        topics = [{"name": t["name"], "label": t.get("label", t["name"]), "enabled": t.get("enabled", True) is not False}
                  for t in cfg.get("topics", [])]
        return {
            "channel": cfg["channel"]["name"], "counts": counts, "total": len(items), "cost_month": cost_month,
            "topics": topics, "keys": self.env_status(),
            "engines": {"llm": f"{cfg['llm']['provider']} · {cfg['llm']['model']}", "asr": cfg["asr"].get("engine"),
                        "tts": cfg["tts"]["engine"], "image": cfg["thumbnail"].get("image_engine"),
                        "review": bool(cfg["review"].get("enabled")), "youtube": bool(cfg["youtube"].get("enabled"))},
            "config_exists": (self.root / "config.yaml").exists(),
            "tasks": [t.to_dict() for t in sorted(self.tasks.items.values(), key=lambda t: t.started, reverse=True)][:10],
            "market": self.latest_market() is not None,
        }

    def latest_market(self) -> dict | None:
        folder = Path(self.cfg()["workdir"]) / "market"
        files = sorted(f for f in folder.glob("market_*.json") if "raw" not in f.name) if folder.exists() else []
        if not files:
            return None
        data = json.loads(files[-1].read_text(encoding="utf-8"))
        return {"date": files[-1].stem.replace("market_", ""), "niches": data}


# ====================================================================== HTTP

class Handler(BaseHTTPRequestHandler):
    app: App = None  # gán khi tạo server
    server_version = "AutoVideoUI/1.0"

    def log_message(self, fmt, *args):  # yên lặng, tránh rác cửa sổ lệnh
        pass

    # ---- tiện ích phản hồi
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def error(self, msg: str, status=400):
        self.send_json({"error": msg}, status)

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20 * 1024 * 1024:
            raise ValueError("dữ liệu quá lớn")
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def authorized(self) -> bool:
        if not self.app.token:
            return True
        q = parse_qs(urlparse(self.path).query)
        given = self.headers.get("X-Token") or (q.get("token") or [""])[0]
        cookie = self.headers.get("Cookie") or ""
        m = re.search(r"av_token=([\w-]+)", cookie)
        return secrets.compare_digest(given or (m.group(1) if m else ""), self.app.token)

    # ---- định tuyến
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method: str):
        url = urlparse(self.path)
        path = unquote(url.path)
        try:
            if method == "GET" and path in ("/", "/index.html"):
                return self.static("index.html", set_token=True)
            if method == "GET" and path.startswith("/static/"):
                return self.static(path[len("/static/"):])
            if not self.authorized():
                return self.error("Cần mã truy cập (mở đúng đường link in ở cửa sổ lệnh)", 401)
            if method == "GET" and path == "/files":
                return self.file(parse_qs(url.query).get("p", [""])[0])
            for pattern, fn in ROUTES.get(method, []):
                m = re.fullmatch(pattern, path)
                if m:
                    return fn(self, *m.groups())
            return self.error("không tìm thấy", 404)
        except FileNotFoundError as e:
            return self.error(f"không tìm thấy: {e}", 404)
        except (ValueError, RuntimeError) as e:
            return self.error(str(e), 400)
        except Exception as e:
            traceback.print_exc()
            return self.error(f"lỗi: {e}", 500)

    def static(self, name: str, set_token: bool = False):
        path = (STATIC / name).resolve()
        if STATIC not in path.parents or not path.is_file():
            return self.error("không tìm thấy", 404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(str(path))[0] or "application/octet-stream")
                         + ("; charset=utf-8" if path.suffix in {".html", ".js", ".css"} else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        if set_token and self.app.token:
            q = parse_qs(urlparse(self.path).query)
            tok = (q.get("token") or [""])[0]
            if tok and secrets.compare_digest(tok, self.app.token):
                self.send_header("Set-Cookie", f"av_token={tok}; Path=/; SameSite=Strict; HttpOnly")
        self.end_headers()
        self.wfile.write(data)

    def file(self, rel: str):
        """Phục vụ ảnh/video trong ready/ và output/ (có Range để tua video)."""
        app = self.app
        path = (app.root / rel).resolve()
        allowed = [app.ready_dir().resolve(), Path(app.cfg()["workdir"]).resolve()]
        if not any(path == a or a in path.parents for a in allowed) or not path.is_file():
            return self.error("không được phép", 403)
        size = path.stat().st_size
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or path.suffix in {".json", ".log", ".md"}:
            ctype += "; charset=utf-8"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:  # bytes=-N
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-cache")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # trình duyệt dừng tải video giữa chừng — bình thường


# ---------------------------------------------------------------------- API

def api_overview(h: Handler):
    h.send_json(h.app.overview())


def api_config(h: Handler):
    cfg = h.app.cfg()
    h.send_json({"config": cfg, "user": h.app.user_config(), "keys": h.app.env_status()})


def api_config_save(h: Handler):
    merged = h.app.save_user_config(h.body())
    h.send_json({"ok": True, "user": merged})


def api_env_save(h: Handler):
    h.app.save_env(h.body())
    h.send_json({"ok": True, "keys": h.app.env_status()})


def api_tasks(h: Handler):
    items = sorted(h.app.tasks.items.values(), key=lambda t: t.started, reverse=True)
    h.send_json([t.to_dict() for t in items])


def api_task_start(h: Handler):
    b = h.body()
    kind = b.get("kind")
    app = h.app
    if kind == "auto":
        argv, label = ["auto"], "Chạy 1 lượt tự động"
        if b.get("dry_run"):
            argv.append("--dry-run")
            label = "Xem trước lượt tự động"
        for t in b.get("topics") or []:
            argv += ["--topic", t]
        if b.get("per_topic"):
            argv += ["--per-topic", str(int(b["per_topic"]))]
    elif kind == "make":
        source = (b.get("source") or "").strip()
        if b.get("text"):
            folder = app.root / "output" / "ui_sources"
            folder.mkdir(parents=True, exist_ok=True)
            from ..pipeline import slugify

            name = slugify(b.get("name") or b["text"][:40]) or "truyen"
            src = folder / f"{datetime.now():%Y%m%d-%H%M%S}-{name}.txt"
            src.write_text(b["text"], encoding="utf-8")
            source = str(src)
        if not source:
            raise ValueError("Cần link truyện, hoặc dán/tải văn bản truyện")
        argv, label = ["make", source, "--export"], f"Tạo video: {Path(source).name if Path(source).exists() else source}"
        if b.get("topic"):
            argv += ["--topic", b["topic"]]
    elif kind in ("market", "doctor", "brand", "report"):
        argv = [kind]
        if kind == "doctor" and b.get("online"):
            argv.append("--online")
        if kind == "brand" and b.get("real"):
            argv.append("--real")
        label = {"market": "Khảo sát thị trường", "doctor": "Kiểm tra cài đặt", "brand": "Xem trước nhận diện",
                 "report": "Báo cáo kênh"}[kind]
    else:
        raise ValueError(f"việc không hỗ trợ: {kind}")
    task = app.tasks.start(kind, argv, label)
    h.send_json(task.to_dict())


def api_task_log(h: Handler, task_id: str):
    t = h.app.tasks.items.get(task_id)
    if not t:
        raise FileNotFoundError(task_id)
    offset = int(parse_qs(urlparse(h.path).query).get("offset", ["0"])[0])
    data = t.log.read_bytes() if t.log.exists() else b""
    h.send_json({"task": t.to_dict(), "text": data[offset:].decode("utf-8", "replace"), "offset": len(data)})


def api_task_stop(h: Handler, task_id: str):
    h.app.tasks.stop(task_id)
    h.send_json({"ok": True})


def api_ready(h: Handler):
    h.send_json(h.app.ready_items())


def api_item(h: Handler, item_id: str):
    from ..review import review_id, reviews_store

    d = h.app.find_item(item_id)
    rec = reviews_store(h.app.cfg()).get(review_id(d)) or {}
    forced = "approved" if d.parent.name == "_approved" else "rejected" if d.parent.name == "_rejected" else None
    h.send_json(h.app.item_summary(d, rec, forced))


def api_item_text(h: Handler, item_id: str):
    b = h.body()
    name = b.get("file")
    if name not in EDITABLE_TEXTS:
        raise ValueError("không sửa được file này")
    d = h.app.find_item(item_id)
    (d / name).write_text(b.get("content", ""), encoding="utf-8")
    if name == "title.txt":
        from ..review import reviews_store

        rid = h.app.ensure_review(d)
        reviews_store(h.app.cfg()).update(rid, title=b.get("content", "").strip())
    h.send_json({"ok": True})


def api_item_variant(h: Handler, item_id: str):
    from ..review import do_select_variant

    d = h.app.find_item(item_id)
    n = int(h.body().get("n", 1))
    rid = h.app.ensure_review(d)
    if n == 1:
        if (d / "thumbnail_1.jpg").exists():
            shutil.copy(d / "thumbnail_1.jpg", d / "thumbnail.jpg")
        titles = json.loads((d / "titles.json").read_text(encoding="utf-8"))
        (d / "title.txt").write_text(titles[0], encoding="utf-8")
        from ..review import reviews_store

        reviews_store(h.app.cfg()).update(rid, title=titles[0], variant=1)
    else:
        do_select_variant(rid, n, h.app.cfg(), UILog(h.app.root / "output" / "ui_logs" / "variants.log"))
    h.send_json({"ok": True})


def api_item_action(h: Handler, item_id: str, action: str):
    from ..review import do_publish, do_reject, reviews_store

    app = h.app
    d = app.find_item(item_id)
    rid = app.ensure_review(d)
    cfg = app.cfg()
    if action in ("publish", "schedule"):
        if not cfg["youtube"].get("enabled"):
            raise ValueError("Chưa bật upload YouTube (Cài đặt → YouTube)")
        task = app.tasks.start_thread("publish", f"Đăng: {d.name}",
                                      lambda log: do_publish(rid, cfg, log, action == "schedule"))
        return h.send_json(task.to_dict())
    if action == "manual":
        reviews_store(cfg).update(rid, status="published_manual")
        return h.send_json({"ok": True})
    if action == "reject":
        do_reject(rid, cfg, UILog(app.root / "output" / "ui_logs" / "actions.log"))
        return h.send_json({"ok": True})
    if action == "restore":
        target = app.ready_dir() / d.name
        if d.parent != app.ready_dir():
            shutil.move(str(d), target)
        reviews_store(cfg).update(rid, status="pending", dest=str(target))
        return h.send_json({"ok": True})
    raise ValueError(f"thao tác không hỗ trợ: {action}")


def api_market(h: Handler):
    h.send_json(h.app.latest_market() or {})


def api_report(h: Handler):
    from ..analytics import report_text

    h.send_json({"text": report_text(h.app.cfg())})


def api_inbox(h: Handler):
    b = h.body()
    cfg = h.app.cfg()
    topic = b.get("topic") or ""
    if topic and topic not in {t["name"] for t in cfg["topics"]}:
        raise ValueError("chủ đề không tồn tại")
    from ..pipeline import slugify

    folder = h.app.abs(cfg["auto"].get("inbox_dir", "inbox")) / topic
    folder.mkdir(parents=True, exist_ok=True)
    text = b.get("text", "")
    if len(text.strip()) < 200:
        raise ValueError("Văn bản truyện quá ngắn")
    name = slugify(b.get("name") or text[:40]) or f"truyen-{int(time.time())}"
    (folder / f"{name}.txt").write_text(text, encoding="utf-8")
    h.send_json({"ok": True, "path": h.app.rel(folder / f'{name}.txt')})


def api_inbox_list(h: Handler):
    cfg = h.app.cfg()
    root = h.app.abs(cfg["auto"].get("inbox_dir", "inbox"))
    files = [h.app.rel(p) for p in sorted(root.rglob("*.txt")) if "_done" not in p.parts] if root.exists() else []
    h.send_json(files)


ROUTES = {
    "GET": [
        (r"/api/overview", api_overview), (r"/api/config", api_config), (r"/api/tasks", api_tasks),
        (r"/api/tasks/(\w+)/log", api_task_log), (r"/api/ready", api_ready), (r"/api/ready/([\w.\-]+)", api_item),
        (r"/api/market", api_market), (r"/api/report", api_report), (r"/api/inbox", api_inbox_list),
    ],
    "POST": [
        (r"/api/config", api_config_save), (r"/api/env", api_env_save), (r"/api/tasks", api_task_start),
        (r"/api/tasks/(\w+)/stop", api_task_stop), (r"/api/ready/([\w.\-]+)/text", api_item_text),
        (r"/api/ready/([\w.\-]+)/variant", api_item_variant),
        (r"/api/ready/([\w.\-]+)/(publish|schedule|manual|reject|restore)", api_item_action),
        (r"/api/inbox", api_inbox),
    ],
}


def make_server(root: Path, host: str = "127.0.0.1", port: int = 8765, token: str | None = None):
    handler = type("BoundHandler", (Handler,), {"app": App(root, token)})
    return ThreadingHTTPServer((host, port), handler)


def lan_ip() -> str:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def serve(port: int = 8765, lan: bool = False, open_browser: bool = True) -> None:
    root = Path.cwd()
    token = secrets.token_urlsafe(12) if lan else None
    host = "0.0.0.0" if lan else "127.0.0.1"
    srv = make_server(root, host, port, token)
    local = f"http://127.0.0.1:{port}/" + (f"?token={token}" if token else "")
    print("=" * 60)
    print(f" AutoVideo — giao diện đang chạy: {local}")
    if lan:
        print(f" Trên điện thoại (cùng Wi‑Fi): http://{lan_ip()}:{port}/?token={token}")
        print(" (Không chia sẻ đường link có mã này cho người khác)")
    print(" Đóng cửa sổ này hoặc bấm Ctrl+C để tắt giao diện.")
    print("=" * 60)
    if open_browser:
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(local)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
