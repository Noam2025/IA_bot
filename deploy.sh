cat > deploy.sh <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

# =========================
# CONFIG (à adapter 1 fois)
# =========================
VPS_USER="noam"
VPS_HOST="5.75.144.64"          # <-- ton IP VPS (mets la tienne)
VPS_PROJECT_DIR="~/IA_bot"
VPS_BACKEND_DIR="$VPS_PROJECT_DIR/backend"
UVICORN_APP="main:app"
UVICORN_HOST="0.0.0.0"
UVICORN_PORT="8000"

# tmux (recommandé en VPS pour garder le backend actif)
USE_TMUX="${USE_TMUX:-1}"        # 1=tmux, 0=mode simple
TMUX_SESSION="backend"

# commit message automatique si non fourni
MSG="${1:-"fix: deploy"}"

# =========================
# 1) Push sur GitHub (Mac)
# =========================
echo "==> [MAC] Git add/commit/push..."
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "ERROR: pas dans un repo git"; exit 1; }

git add backend
if git diff --cached --quiet; then
  echo "Nothing to commit (backend)."
else
  git commit -m "$MSG"
fi
git push

# =========================
# 2) Pull + restart sur VPS
# =========================
echo "==> [VPS] Pull + restart uvicorn..."
ssh -o StrictHostKeyChecking=accept-new "${VPS_USER}@${VPS_HOST}" bash -lc "'
set -e

cd ${VPS_PROJECT_DIR}
git pull

cd ${VPS_BACKEND_DIR}

# kill uvicorn (au cas où)
pkill -f \"uvicorn ${UVICORN_APP}\" >/dev/null 2>&1 || true
pkill -f \"python -m uvicorn ${UVICORN_APP}\" >/dev/null 2>&1 || true

if [ \"${USE_TMUX}\" = \"1\" ]; then
  command -v tmux >/dev/null 2>&1 || { echo \"tmux not installed. Install: sudo apt-get update && sudo apt-get install -y tmux\"; exit 1; }

  # stop ancienne session si existe
  tmux kill-session -t ${TMUX_SESSION} >/dev/null 2>&1 || true

  # démarre en tmux
  tmux new-session -d -s ${TMUX_SESSION} \"python -m uvicorn ${UVICORN_APP} --host ${UVICORN_HOST} --port ${UVICORN_PORT}\"
  echo \"Started in tmux session: ${TMUX_SESSION}\"
else
  # démarre en foreground (attention: coupe quand tu fermes SSH)
  python -m uvicorn ${UVICORN_APP} --host ${UVICORN_HOST} --port ${UVICORN_PORT}
fi

# healthcheck rapide
sleep 1
curl -s http://127.0.0.1:${UVICORN_PORT}/health || true
'"

echo "==> DONE"
BASH

chmod +x deploy.sh
