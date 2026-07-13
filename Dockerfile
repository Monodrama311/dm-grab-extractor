# dm-grab-extractor — self-hosted image for the Hetzner box (Dispatch 031).
# Mirrors build.sh: Python (Flask + yt-dlp + gunicorn) AND Node (the bgutil
# POT-token provider, built to .bgutil-provider/server/build/generate_once.js).
FROM python:3.12-slim

# Node + git are needed to build the bgutil POT provider; ca-certificates for
# yt-dlp's HTTPS. curl_cffi ships manylinux wheels, so no compiler is required.
RUN apt-get update && apt-get install -y --no-install-recommends \
      nodejs npm git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first for layer caching.
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install --upgrade --pre 'yt-dlp[default,curl-cffi]'

# bgutil POT provider — same version + steps as build.sh, baked into the image.
# If the tsc build ever fails on Debian's Node, install Node 20 via nodesource.
RUN git clone --depth 1 --branch 1.3.1 \
      https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /app/.bgutil-provider \
 && npm --prefix /app/.bgutil-provider/server ci \
 && npm exec --prefix /app/.bgutil-provider/server -- tsc -p /app/.bgutil-provider/server/tsconfig.json \
 && test -f /app/.bgutil-provider/server/build/generate_once.js

# App source (a clean clone has no .bgutil-provider, so the built one survives).
COPY . .

ENV PORT=8000 \
    POT_PROVIDER_HOME=/app/.bgutil-provider/server
EXPOSE 8000

# INTERNAL_TOKEN is supplied at run time (compose/.env), never baked in.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --timeout 180 --workers 2"]
