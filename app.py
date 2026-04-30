"""
DM Logic — Grab Extractor Service

一个 Flask 服务,接受 URL,返回 metadata + 媒体直链。
部署到 Render 免费层。

文件结构:
  app.py              ← 这个文件
  requirements.txt    ← 见下方注释

环境变量(Render Dashboard 设置):
  INTERNAL_TOKEN      ← Worker 调本服务用的密钥(自己生成 32 位随机串)
"""

import os
import logging
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("grab")

app = Flask(__name__)
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")


# ─────────────────────────────────────────────
# 健康检查(Render 用,也用来手动测)
# ─────────────────────────────────────────────
@app.route("/health")
def health():
    return {"ok": True, "ytdlp_version": yt_dlp.version.__version__}


# ─────────────────────────────────────────────
# 主接口:抓取
# ─────────────────────────────────────────────
@app.route("/extract", methods=["POST"])
def extract():
    # 内部 token 校验
    if request.headers.get("X-Internal-Token") != INTERNAL_TOKEN:
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    url = data.get("url")
    if not url:
        return jsonify({"error": "missing_url"}), 400

    try:
        result = run_ytdlp(url)
        return jsonify({"ok": True, "data": result}), 200
    except yt_dlp.utils.DownloadError as e:
        log.warning("ytdlp_error url=%s err=%s", url, e)
        return jsonify({"ok": False, "error": "extractor_failed", "detail": str(e)}), 502
    except Exception as e:
        log.exception("unexpected url=%s", url)
        return jsonify({"ok": False, "error": "internal", "detail": str(e)}), 500


def run_ytdlp(url: str) -> dict:
    """提取元数据 + 媒体直链,不下载文件本身。"""
    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return normalize(info)


def normalize(info: dict) -> dict:
    """yt-dlp 字段 → 统一格式。"""
    if not info:
        return {}

    # 媒体类型
    if info.get("_type") == "playlist":
        media_type = "carousel"
    elif info.get("vcodec") and info.get("vcodec") != "none":
        media_type = "video"
    elif info.get("acodec") and info.get("acodec") != "none":
        media_type = "audio"
    else:
        media_type = "unknown"

    # hashtags / mentions(简单从文本里抽)
    text = " ".join(filter(None, [info.get("title"), info.get("description")]))
    hashtags = sorted(set(t for t in text.split() if t.startswith("#")))
    mentions = sorted(set(t for t in text.split() if t.startswith("@")))

    # 媒体 URL
    media_urls = []
    if info.get("formats"):
        for f in info["formats"]:
            if not f.get("url"):
                continue
            media_urls.append({
                "type": "video" if (f.get("vcodec") and f["vcodec"] != "none") else "audio",
                "url": f["url"],
                "width": f.get("width"),
                "height": f.get("height"),
                "filesize": f.get("filesize"),
                "ext": f.get("ext"),
                "format_id": f.get("format_id"),
                "abr": f.get("abr"),
                "vbr": f.get("vbr"),
            })

    # 作者
    author_info = {
        "id": info.get("uploader_id") or info.get("channel_id"),
        "username": info.get("uploader") or info.get("channel"),
        "display_name": info.get("uploader") or info.get("channel"),
        "url": info.get("uploader_url") or info.get("channel_url"),
        "follower_count": info.get("channel_follower_count"),
        "verified": info.get("channel_is_verified"),
    }

    # 互动数据
    engagement = {
        "views": info.get("view_count"),
        "likes": info.get("like_count"),
        "comments": info.get("comment_count"),
        "shares": info.get("repost_count"),
    }

    # 发布时间
    published_at = None
    if info.get("upload_date"):
        d = info["upload_date"]
        published_at = f"{d[0:4]}-{d[4:6]}-{d[6:8]}T00:00:00Z"

    return {
        "media_type": media_type,
        "title": info.get("title"),
        "caption": info.get("description"),
        "description": info.get("description"),
        "hashtags": hashtags,
        "mentions": mentions,
        "author_info": author_info,
        "engagement": engagement,
        "media_urls": media_urls,
        "thumbnail_url": info.get("thumbnail"),
        "duration_sec": info.get("duration"),
        "content_published_at": published_at,
        "extractor": info.get("extractor"),
        "extractor_version": yt_dlp.version.__version__,
        "raw_response": {
            "id": info.get("id"),
            "webpage_url": info.get("webpage_url"),
            "tags": info.get("tags"),
            "categories": info.get("categories"),
        },
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ============================================================
# requirements.txt 内容(单独保存):
# ============================================================
# flask==3.0.0
# yt-dlp>=2024.10.0
# gunicorn==21.2.0
# ============================================================

# ============================================================
# render.yaml(放仓库根目录):
# ============================================================
# services:
#   - type: web
#     name: dm-grab-extractor
#     env: python
#     plan: free
#     buildCommand: "pip install -r requirements.txt && pip install --upgrade yt-dlp"
#     startCommand: "gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 2"
#     envVars:
#       - key: INTERNAL_TOKEN
#         sync: false
# ============================================================
