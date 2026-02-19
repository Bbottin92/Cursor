#!/usr/bin/env bash
set -euo pipefail

# One-shot helper to prepare Cursor/VS Code Remote-SSH access.
#
# What it does:
#   - Ensures ~/.ssh permissions are sane
#   - Generates an Ed25519 key (if missing)
#   - Prints the public key (so you can import + authorize in cPanel)
#   - Adds/updates a host entry in ~/.ssh/config (so Cursor can connect)
#
# What it cannot do:
#   - Open firewalls / allowlist your IP
#   - Enable shell access on the hosting account
# Those must be handled by your host (NuNames support / cPanel settings).

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: Missing required command: $1" >&2
    exit 2
  fi
}

need_cmd ssh
need_cmd ssh-keygen
need_cmd chmod
need_cmd mkdir
need_cmd sed
need_cmd awk

DEFAULT_HOST_ALIAS="liquidgov"
DEFAULT_KEY_PATH="$HOME/.ssh/liquidgov_cursor"

echo ""
echo "== Cursor Remote-SSH setup (one-shot) =="
echo ""

read -r -p "SSH hostname (from cPanel SSH Access page) [host04.nunames.net]: " SSH_HOST
SSH_HOST="${SSH_HOST:-host04.nunames.net}"

read -r -p "SSH username (cPanel username) [liquidgo]: " SSH_USER
SSH_USER="${SSH_USER:-liquidgo}"

read -r -p "SSH port (from cPanel; often 22/2222/2200/2022) [22]: " SSH_PORT
SSH_PORT="${SSH_PORT:-22}"

read -r -p "SSH config host alias (what you'll type in Cursor) [${DEFAULT_HOST_ALIAS}]: " HOST_ALIAS
HOST_ALIAS="${HOST_ALIAS:-$DEFAULT_HOST_ALIAS}"

read -r -p "Key path [${DEFAULT_KEY_PATH}]: " KEY_PATH
KEY_PATH="${KEY_PATH:-$DEFAULT_KEY_PATH}"

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [[ ! -f "$KEY_PATH" ]]; then
  echo ""
  echo "Generating key: $KEY_PATH"
  ssh-keygen -t ed25519 -a 64 -f "$KEY_PATH" -C "${HOST_ALIAS}" </dev/tty
else
  echo ""
  echo "Key already exists: $KEY_PATH"
fi

chmod 600 "$KEY_PATH"
chmod 644 "${KEY_PATH}.pub"

echo ""
echo "== Public key (import this in cPanel -> SSH Access -> Manage SSH Keys -> Import -> Authorize) =="
echo ""
cat "${KEY_PATH}.pub"
echo ""

SSH_CONFIG="$HOME/.ssh/config"
touch "$SSH_CONFIG"
chmod 600 "$SSH_CONFIG"

echo "Updating $SSH_CONFIG ..."

tmp="$(mktemp)"
awk -v alias="$HOST_ALIAS" '
  BEGIN { in_block=0; wrote=0 }
  $1 == "Host" && $2 == alias {
    in_block=1
    next
  }
  $1 == "Host" && in_block==1 {
    in_block=0
  }
  in_block==0 { print }
  END { }
' "$SSH_CONFIG" > "$tmp"

cat >>"$tmp" <<EOF

Host ${HOST_ALIAS}
  HostName ${SSH_HOST}
  User ${SSH_USER}
  Port ${SSH_PORT}
  IdentityFile ${KEY_PATH}
  IdentitiesOnly yes
EOF

mv "$tmp" "$SSH_CONFIG"

echo ""
echo "== Test command =="
echo "ssh -v ${HOST_ALIAS}"
echo ""
echo "== Cursor =="
echo "Cursor -> Command Palette -> Remote-SSH: Connect to Host... -> ${HOST_ALIAS}"
echo ""
echo "If you get CONNECTION TIMEOUT, your host must allowlist your IP / open SSH."
echo ""

