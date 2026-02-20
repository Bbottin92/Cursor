#!/usr/bin/env bash
set -euo pipefail

BRANCH="${BRANCH:-cursor/liquidgov-website-definition-d045}"
CP_HOST="${CP_HOST:-host04.nunames.net}"
CP_USER="${CP_USER:-liquidgo}"
SITE_URL="${SITE_URL:-https://liquidgov.us}"
TOKEN_FILE="${TOKEN_FILE:-$HOME/.liquidgov_cpanel_token}"
ROOT_DIR="${ROOT_DIR:-public_html}"

if [[ -z "${CP_TOKEN:-}" ]]; then
  if [[ -f "$TOKEN_FILE" ]]; then
    CP_TOKEN="$(<"$TOKEN_FILE")"
  else
    echo "Missing CP_TOKEN and token file: $TOKEN_FILE" >&2
    echo "Create it with:" >&2
    echo "  read -rsp \"cPanel API token: \" T; echo; printf '%s' \"\$T\" > \"$TOKEN_FILE\"; chmod 600 \"$TOKEN_FILE\"; unset T" >&2
    exit 1
  fi
fi

if [[ -z "$CP_TOKEN" ]]; then
  echo "CP_TOKEN is empty." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

if [[ "${SKIP_GIT:-0}" != "1" ]]; then
  echo "Updating local branch: $BRANCH"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
fi

FILES=(
  index.html
  app.html
  legal.html
  styles.css
  main.js
  app.js
  dataClient.js
  store.js
  login.html
  dashboard.html
  profile.html
  edit-profile.html
  js/error-handler.js
)

for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing file: $file" >&2
    exit 1
  fi
done

BASE="https://${CP_HOST}:2083"
AUTH="Authorization: cpanel ${CP_USER}:${CP_TOKEN}"

api_call() {
  curl -k -sS "$@"
}

auth_code="$(api_call -o /tmp/liquidgov_auth_check.json -w "%{http_code}" -H "$AUTH" "${BASE}/execute/Variables/get_user_information")"
if [[ "$auth_code" != "200" ]]; then
  echo "cPanel auth failed (HTTP $auth_code)." >&2
  exit 1
fi

mkdir_api() {
  local parent="$1"
  local name="$2"
  api_call -H "$AUTH" --get \
    --data-urlencode "dir=${parent}" \
    --data-urlencode "name=${name}" \
    "${BASE}/execute/Fileman/mkdir" >/dev/null
}

upload_file() {
  local file="$1"
  local dir="$ROOT_DIR/$(dirname "$file")"
  if [[ "$(dirname "$file")" == "." ]]; then
    dir="$ROOT_DIR"
  fi
  local code
  code="$(api_call -o /tmp/liquidgov_upload_resp.json -w "%{http_code}" \
    -H "$AUTH" \
    -F "dir=${dir}" \
    -F "overwrite=1" \
    -F "file-1=@${file}" \
    "${BASE}/execute/Fileman/upload_files")"
  if [[ "$code" != "200" ]]; then
    echo "Upload failed for $file (HTTP $code)." >&2
    cat /tmp/liquidgov_upload_resp.json >&2 || true
    exit 1
  fi
  echo "Uploaded: $file -> $dir"
}

mkdir_api "$ROOT_DIR" "js"

for file in "${FILES[@]}"; do
  upload_file "$file"
done

echo "Verifying live pages..."
home_code="$(curl -s -o /dev/null -w "%{http_code}" "${SITE_URL}/")"
app_code="$(curl -s -o /dev/null -w "%{http_code}" "${SITE_URL}/app.html")"
participants="$(curl -s "${SITE_URL}/api/stats/participants")"
announcements="$(curl -s "${SITE_URL}/api/announcements")"

echo "HTTP ${home_code} ${SITE_URL}/"
echo "HTTP ${app_code} ${SITE_URL}/app.html"
echo "Participants: ${participants}"
echo "Announcements: ${announcements}"

if [[ "$home_code" != "200" || "$app_code" != "200" ]]; then
  echo "Verification failed: expected HTTP 200 for homepage and app page." >&2
  exit 1
fi

echo "Deploy complete."
