#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --upgrade --pre 'yt-dlp[default,curl-cffi]'

provider_root=".bgutil-provider"
rm -rf "$provider_root"
git clone --depth 1 --branch 1.3.1 \
  https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
  "$provider_root"
npm --prefix "$provider_root/server" ci
npm exec --prefix "$provider_root/server" -- \
  tsc -p "$provider_root/server/tsconfig.json"

test -f "$provider_root/server/build/generate_once.js"
