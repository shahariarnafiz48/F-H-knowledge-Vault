# Putting the Knowledge Vault live (Hostinger VPS, staff only)

You need: a Hostinger **VPS** (Ubuntu 24.04), a domain/subdomain such as `vault.fiberathome.net`, a no-reply mailbox for the codes, and the list of staff emails.

## 1. Point the address at the server
In your DNS, add an **A record**: `vault` → the VPS IP address. Wait until `ping vault.fiberathome.net` shows that IP.

## 2. Let the server read this repository (read-only deploy key)
On the VPS:
```bash
ssh-keygen -t ed25519 -C "vps-deploy" -f ~/.ssh/vault_deploy -N ""
cat ~/.ssh/vault_deploy.pub                    # copy this line
```
GitHub → repository → **Settings → Deploy keys → Add deploy key** → paste it, **leave "Allow write access" unticked**.
```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/vault_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
ssh -T git@github.com                           # should greet the repository
sudo git clone git@github.com:shahariarnafiz48/F-H-knowledge-Vault.git /srv/vault
```
(If `sudo git clone` cannot see your key, run `sudo -E` or clone as root with the key in `/root/.ssh`.)

## 3. Run the one-time setup
```bash
cd /srv/vault
sudo bash deploy/setup_server.sh vault.fiberathome.net your.name@fiberathome.net
```
It installs the database and web server, turns on the firewall, creates the database, loads the knowledge, creates your administrator account and starts the service with automatic HTTPS and nightly backups.

## 4. Set the mailbox that sends the codes
```bash
sudo nano /etc/fhl-vault.env       # set SMTP_USER, SMTP_PASSWORD (and SMTP_HOST / SMTP_PORT / SMTP_SECURITY if not Hostinger)
sudo systemctl restart fhl-vault
```
In your DNS, add the **SPF and DKIM** records your mail provider gives you, otherwise codes may land in spam.

## 5. Add your staff
Create `staff.csv` (header `email,name,role,department`; role = viewer/editor/reviewer/admin; department blank = all):
```bash
cd /srv/vault && set -a && . /etc/fhl-vault.env && set +a
.venv/bin/python scripts/import_staff.py staff.csv --dry-run     # check first
.venv/bin/python scripts/import_staff.py staff.csv               # then import
```

## 6. Test before announcing
1. Open `https://vault.fiberathome.net` - you see only the sign-in page.
2. Enter your email → the code arrives → enter it → the vault opens.
3. A wrong code is refused; an email that is not on the list receives nothing (and sees the same screen).
4. Sign out, press Back: the vault must not reappear.

## Updating later
```bash
cd /srv/vault && sudo bash deploy/deploy.sh
```

## Keep in mind
- Anyone not in the staff list, or outside `OTP_ALLOWED_DOMAINS`, can never receive a code.
- Backups run nightly into `/var/backups/fhl-vault`; copy them off the server regularly (Hostinger snapshots too).
- Apply Ubuntu updates monthly: `sudo apt update && sudo apt upgrade`.
- Edits made in the vault's Update Center are held in each browser only. Saving them to the database for everyone is the next build step (see `docs/00-status.md`).
