"""
DM Logic — Grab Extractor Service (v2)

Bot-detection-resistant yt-dlp wrapper.
Hardening:
  - curl_cffi for Chrome TLS fingerprint (bypasses cloud-IP bot blocks)
  - youtube extractor_args with multiple player clients (mweb/tv_simply/web_safari)
  - realistic User-Agent
  - retries with backoff
"""

import os
import logging
import random
from flask import Flask, request, jsonify
import yt_dlp

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("grab")

app = Flask(__name__)
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")

UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]


@app.route("/health")
def health():
    return {"ok": True, "ytdlp_version": yt_dlp.version.__version__}


@app.route("/extract", methods=["POST"])
def extract():
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
        return jsonify({"ok": False, "error": "extractor_failed", "detail": str(e)[:500]}), 502
    except Exception as e:
        log.exception("unexpected url=%s", url)
        return jsonify({"ok": False, "error": "internal", "detail": str(e)[:500]}), 500


def run_ytdlp(url: str) -> dict:
    """Extract metadata + media URLs. Doesn't download files."""
    ua = random.choice(UA_POOL)

    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "retries": 3,
        "fragment_retries": 3,
        "http_headers": {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Mode": "navigate",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb", "tv_simply", "web_safari", "android"],
                "skip": ["dash"],
            },
        },
    }

    # Add Chrome TLS impersonation if curl_cffi is available
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        ydl_opts["impersonate"] = ImpersonateTarget("chrome")
    except Exception:
        log.info("impersonate API unavailable, falling back to vanilla requests")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        if "impersonate" in str(e).lower() or "curl" in str(e).lower():
            log.info("retry without impersonate")
            ydl_opts.pop("impersonate", None)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        else:
            raise

    return normalize(info)


def normalize(info: dict) -> dict:
    if not info:
        return {}

    if info.get("_type") == "playlist":
        media_type = "carousel"
    elif info.get("vcodec") and info.get("vcodec") != "none":
        media_type = "video"
    elif info.get("acodec") and info.get("acodec") != "none":
        media_type = "audio"
    else:
        media_type = "unknown"

    text = " ".join(filter(None, [info.get("title"), info.get("description")]))
    hashtags = sorted(set(t for t in text.split() if t.startswith("#")))
    mentions = sorted(set(t for t in text.split() if t.startswith("@")))

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

    author_info = {
        "id": info.get("uploader_id") or info.get("channel_id"),
        "username": info.get("uploader") or info.get("channel"),
        "display_name": info.get("uploader") or info.get("channel"),
        "url": info.get("uploader_url") or info.get("channel_url"),
        "follower_count": info.get("channel_follower_count"),
        "verified": info.get("channel_is_verified"),
    }

    engagement = {
        "views": info.get("view_count"),
        "likes": info.get("like_count"),
        "comments": info.get("comment_count"),
        "shares": info.get("repost_count"),
    }

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
