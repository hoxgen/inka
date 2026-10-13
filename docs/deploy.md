# Deployment

This guide runs the server on a small always-on Linux machine as a systemd user service. The frame and the web UI reach it in different ways:

- **The frame** fetches its image from the internet through a Cloudflare tunnel. The tunnel exposes only `/api/v1/frame`, and that endpoint requires the device token.
- **The web UI** has no login of its own. It is reachable only from your Tailscale network. It also refuses requests that arrive through Cloudflare and cross-site POSTs.

Any other way of exposing the two parts works as well. The frame only needs an HTTPS or HTTP URL that it can reach.

## Prerequisites

- **Your computer:** `uv`, `rsync`, `ssh` access to the server.
- **Server:** Linux with systemd, Python ≥ 3.11 with the `venv` module, `rsync` and `curl`.
- **Cloudflare tunnel:** `cloudflared` running as a system service. Its `/etc/cloudflared/config.yml` must contain a `tunnel:` line and an ingress list that ends with `- service: http_status:404`. The domain must be in your Cloudflare account.
- **Tailscale:** installed and logged in, with HTTPS certificates enabled for the tailnet.

## Layout on the server

| What | Where |
|---|---|
| Code | `~/apps/inka/server`, venv `.venv` |
| Service | `systemctl --user … inka`, unit [`deploy/inka.service`](../deploy/inka.service) in `~/.config/systemd/user/`, linger enabled |
| Listens on | `127.0.0.1:8100` |
| Photos | `~/Sync/Inka_photos` (`PHOTOS_DIR`), e.g. synced with Syncthing. The web UI can upload into it too. |
| Data | `~/.local/share/inka` (`settings.json`, `state.json`, `library.json`, `cache/`, `tmp/`) |
| Token | `~/.config/inka/env` containing `INKA_DEVICE_TOKEN=…`, mode `0600` |
| Time zone | `INKA_TZ` in the unit file (default `Europe/Prague`). It sets the times shown in the web UI. Change it to yours before deploying. |

## First deployment

1. On the server, create the token file and directories:

   ```bash
   mkdir -p ~/.config/inka ~/.config/systemd/user ~/apps/inka ~/.local/share/inka
   (umask 077; echo "INKA_DEVICE_TOKEN=$(openssl rand -hex 24)" > ~/.config/inka/env)
   ```

2. From your computer, deploy the code. Run this from the repository root:

   ```bash
   INKA_HOST=user@host tools/deploy.sh
   ```

   The script:
   1. copies `server/`,
   2. installs dependencies from `uv.lock` (via `uv export`) into a venv on the server,
   3. installs and restarts the user service,
   4. checks `127.0.0.1:8100`.

   It does not need `sudo`. Run it again for every update.

3. Copy the setup script to the server and run it there as root:

   ```bash
   scp deploy/setup-root.sh user@host:
   ssh -t user@host 'sudo INKA_FRAME_HOST=frame.example.com bash setup-root.sh'
   ```

   The script:
   1. enables linger, so the service runs without a login session,
   2. adds an ingress rule for `INKA_FRAME_HOST` to an existing `/etc/cloudflared/config.yml` and backs up the old file as `config.yml.bak-*`,
   3. creates the tunnel DNS record,
   4. exposes the web UI in the tailnet with `tailscale serve --https=443 http://127.0.0.1:8100`.

   The ingress rule allows only `^/api/v1/frame$`. Every other path on that hostname returns 404.

4. Provision the frame with `INKA_SERVER_URL=https://frame.example.com` and the same token, see the [README](../README.md).

## Operation

Logs and status:

```bash
ssh user@host 'journalctl --user -u inka -n 50 --no-pager'
ssh user@host 'systemctl --user status inka --no-pager'
```

The web UI also shows the frame status: last contact, battery and temperature.

Rollback:

```bash
git checkout <hash>
INKA_HOST=user@host tools/deploy.sh
git checkout main
```

To change the token:

1. Edit `~/.config/inka/env` on the server.
2. Run `systemctl --user restart inka`.
3. Provision the frame again with the new value.

Backup: the only data that exists nowhere else is `~/.local/share/inka/{settings,state,library}.json`. `cache/` can be deleted at any time.

To undo the cloudflared change, restore `config.yml.bak-*` and run `sudo systemctl restart cloudflared`. To remove the web UI from the tailnet, run `sudo tailscale serve reset`.
