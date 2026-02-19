# LiquidGov one-shot remote edit helper

If your hosting does **not** provide SSH, you can still edit the live website
using cPanel's JSON API (File Manager endpoints).

This helper script is designed to make updates **one command** instead of
clicking through File Manager.

## Setup (on your computer)

1) Copy the env template:

```bash
cp tools/liquidgov.env.example tools/.liquidgov.env
```

2) Edit `tools/.liquidgov.env` and set `CPANEL_PASS`.

3) Load env vars:

```bash
set -a && source tools/.liquidgov.env && set +a
```

4) Sanity check:

```bash
python3 tools/liquidgov_remote.py doctor
```

## Common one-shot commands

List your webroot:

```bash
python3 tools/liquidgov_remote.py ls
```

Download a file from the live site:

```bash
python3 tools/liquidgov_remote.py get styles.css --out styles.css
```

Upload a local file to the live site (defaults to `webroot/<basename>`):

```bash
python3 tools/liquidgov_remote.py put styles.css
```

Replace text in a live file:

```bash
python3 tools/liquidgov_remote.py replace styles.css --old "flex-wrap: wrap;" --new "flex-wrap: nowrap;"
```

Tail the PHP error log:

```bash
python3 tools/liquidgov_remote.py tail --lines 160
```

## Notes / limitations

- This tool is for **text files** (HTML/CSS/JS/PHP/.htaccess). For images or
  other binary files, use SFTP/FTP or cPanel File Manager upload.
- `put` and `replace` create a remote backup (`*.bak.<timestamp>`) unless you
  pass `--no-backup`.

## Cursor / Remote-SSH helper

If your host enables SSH, you can create a simple SSH config entry for Cursor:

```bash
bash tools/setup_cursor_remote_ssh.sh
```

It will generate a key, print the public key for cPanel import/authorization,
and update `~/.ssh/config` with a host alias you can select in Cursor.

