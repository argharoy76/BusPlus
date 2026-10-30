# Deploying BusPlus: GitHub → Hostinger VPS

After this one-time setup, every `git push` to `main` is tested on GitHub and then goes live on your server by itself.

> **You need a Hostinger VPS** (for example KVM 1). Hostinger's shared Web/Cloud hosting can't run Python web apps.
> To check: in hPanel, a VPS appears under **VPS**, with a root login and an IP address.

You also need a **domain or subdomain** (for example `bus.yourdomain.com`) for HTTPS. Phones only allow GPS on HTTPS sites.

---

## 1. Put the code on GitHub (on your computer)

Create an **empty** repository on GitHub. Don't add a README; this folder has one. A **private** repository is fine.

Then, in the BusPlus folder:

```bash
git init
git add .
git status          # make sure .env, instance/ and *.db are NOT listed
git commit -m "BusPlus"
git branch -M main
git remote add origin git@github.com:<you>/<repo>.git
git push -u origin main
```

On GitHub, open the **Actions** tab. "CI and deploy" should turn green. The deploy step is skipped until step 3.

## 2. Prepare the VPS (once)

1. In hPanel → **VPS** → **OS & Panel**, choose the plain **Ubuntu 24.04** template (no control panel).
2. Point your domain at the VPS: in hPanel → **Domains** → **DNS**, add an `A` record. Name: `bus` (or `@`). Points to: your VPS IP.
3. Connect to the server: `ssh root@<VPS-IP>` (password from hPanel). Or use hPanel's **Browser terminal**.
4. Get the setup script onto the server.
   - **Public repository:**
     ```bash
     curl -fsSLO https://raw.githubusercontent.com/<you>/<repo>/main/deploy/setup_server.sh
     ```
   - **Private repository:** open `deploy/setup_server.sh` on GitHub, copy its text, then run `nano setup_server.sh` on the server, paste, save (Ctrl+O, Enter) and exit (Ctrl+X).
5. Run it, with your repo address, your domain and your email:
   ```bash
   sudo bash setup_server.sh git@github.com:<you>/<repo>.git bus.yourdomain.com you@example.com
   ```
   - A **private** repo needs `git@github.com:...` (SSH). The script shows a key and waits. Add the key on GitHub under **repo → Settings → Deploy keys → Add deploy key** (leave "write access" off), then press Enter.
   - A **public** repo can use `https://github.com/<you>/<repo>.git`.

When the script finishes, it prints:

- the **backend password** (username `admin`). Save it in your password manager.
- the values for the GitHub secrets in step 3, including a **private key**.

Open `https://bus.yourdomain.com/backend`, sign in, and add your drivers (Drivers → Add Driver).

## 3. Turn on automatic deploys (once)

On GitHub, go to **repo → Settings → Secrets and variables → Actions → New repository secret** and add:

| Name | Value |
|---|---|
| `VPS_HOST` | your VPS IP address |
| `VPS_USER` | `busplus` |
| `VPS_SSH_KEY` | the whole private key printed by the script, from `-----BEGIN` to `END...-----` |
| `VPS_PORT` | optional; only if SSH isn't on port 22 |

After copying the key, you can delete it from the server: `sudo rm /home/busplus/.ssh/github_actions`. The public half stays, so deploys keep working.

That key can only run the update script on the server, nothing else.

## 4. Every update from now on

```bash
git add .
git commit -m "Describe the change"
git push
```

GitHub then does three things:

1. Runs the code checks and the tests.
2. If they pass, logs in to the VPS and runs `deploy/update.sh`, which:
   - gets the new code
   - installs any new libraries
   - restarts the app
   - checks that the app is running
3. Shows the result in the **Actions** tab.
   - If the tests fail, nothing is deployed and the old version keeps running.
   - If the app fails to start after an update, its last log lines are shown there.

Your data is never touched by updates. `.env`, the database in `instance/` and `backups/` are not part of Git.

---

## Useful commands on the server

| What | Command |
|---|---|
| Is it running? | `sudo systemctl status busplus` |
| Live log | `sudo journalctl -u busplus -f` |
| Restart | `sudo systemctl restart busplus` |
| Update by hand | `sudo -u busplus bash /opt/busplus/deploy/update.sh` |
| Change admin password | `sudo nano /opt/busplus/.env`, then restart |
| Backups | `ls /opt/busplus/backups` (one file per night, 14 days kept) |
| Restore a backup | `sudo systemctl stop busplus`, then `sudo -u busplus cp /opt/busplus/backups/busplus-YYYY-MM-DD.db /opt/busplus/instance/busplus.db`, then `sudo systemctl start busplus` |
| HTTPS renewal | automatic (certbot); test with `sudo certbot renew --dry-run` |

## How it runs on the server

```text
phone / PC ──HTTPS──> nginx (port 443, Let's Encrypt)
                        ├─ /static/ ...... files served directly, cached
                        └─ everything else ──> gunicorn + gevent on 127.0.0.1:8000 (1 process)
                                                  └─ BusPlus (Flask) ── SQLite: /opt/busplus/instance/busplus.db
```

- **App folder:** `/opt/busplus`, owned by the `busplus` user.
- **Settings:** `/opt/busplus/.env` (readable only by `busplus`).
- **Service:** `deploy/busplus.service` (systemd restarts the app if it ever stops).
- **Web server:** `deploy/nginx-busplus.conf`.
- **Firewall:** `ufw` allows only SSH, HTTP and HTTPS.
