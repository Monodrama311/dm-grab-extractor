# Extractor — yt-dlp service

Current service version: **v4**.

- Public YouTube videos use yt-dlp's `android_vr` client so extraction does
  not depend on a personal Google account cookie or a manually rotated PO token.
- `YT_COOKIES` remains optional and should only be used for content that
  genuinely requires an account. Never commit cookie contents.
- `/health` reports `service_version`, yt-dlp version, and whether cookies are loaded.

部署到 Render(免费层),被 Worker 调用。

## 文件
- `app.py` — Flask 服务
- `requirements.txt` — Python 依赖
- `render.yaml` — Render 部署配置
- `.gitignore`

## 部署到 Render

1. 把这个文件夹推到一个独立的 GitHub repo(建议私有):`dm-grab-extractor`
2. Render → New Web Service → 选 repo → Plan: Free
3. 加环境变量 `INTERNAL_TOKEN`(用 `openssl rand -hex 32` 生成)
4. Deploy 完成后,记下 URL(类似 `https://dm-grab-extractor.onrender.com`)
5. 测试: `curl https://你的URL/health` → 应返回 `{"ok": true, ...}`

## 本地测试(可选)

```bash
cd extractor
pip install -r requirements.txt
INTERNAL_TOKEN=test python3 app.py
# 另一个终端:
curl http://localhost:10000/health
```

## ⚠️ Render 免费层注意

15 分钟无请求会休眠,首次唤醒慢 30 秒。
解决方案二选一:
- 升 $7/月(无休眠)
- Cloudflare Worker Cron 每 10 分钟 ping 一次保活
