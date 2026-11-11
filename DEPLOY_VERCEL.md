# Free live demo on Vercel (real email-code sign-in)

Everything below uses free plans: **GitHub** (code), **Neon** (database), **Brevo** (sends the codes) and **Vercel** (hosting). About 20 minutes.

> **Use for a demo / pilot only.** Vercel's free *Hobby* plan is for personal, non-commercial use. For permanent company use, move to the paid Vercel Pro plan or the VPS in `DEPLOY.md` (same code, nothing to rebuild).

## 1. Database (Neon, free)
1. Sign up at neon.com (use "Continue with GitHub").
2. **Create project** → name `fh-vault` → **Region: Asia Pacific (Singapore)** → Postgres 16 or newer → Create.
3. On the project dashboard click **Connect**. Tick **Connection pooling** and copy the connection string. It looks like `postgresql://user:password@ep-xxxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`. Keep it private; this is `DATABASE_URL`.
4. Open **SQL Editor**, paste the **entire** contents of `db/schema.sql`, click **Run**. It should finish without errors.
5. Make your staff list `staff.csv` (header `email,name,role`; role = viewer / editor / reviewer / admin). Give it to the person who runs `python3 scripts/staff_to_sql.py staff.csv > staff.sql` (or send it to Claude to generate). Paste `staff.sql` into the SQL Editor and **Run**. Include yourself as `admin`.

## 2. Mail sender for the codes (Brevo, free)
Vercel blocks outbound SMTP (Gmail connections are cut off), so codes are sent over HTTPS through Brevo's API.
1. Sign up at brevo.com (free plan, 300 emails a day). Ignore the paid-plan page.
2. Settings > Senders, Domains & Dedicated IPs > Senders > Add a sender (use a mailbox you can open) and click the link in the verification email. Later, authenticate fiberathome.net so mail stops landing in Spam.
3. Settings > SMTP & API > API keys & MCP > Generate a new API key (SMS check). Use Restricted access with permission to send email if offered. Leave IP blocking off (Vercel addresses change). This is `BREVO_API_KEY`.

## 3. Publish on Vercel
1. Sign up at vercel.com with **Continue with GitHub**. When asked, let Vercel access `F-H-knowledge-Vault` (private repo: choose "Only select repositories").
2. **Add New → Project → Import** `F-H-knowledge-Vault`. Leave **Framework Preset = Other**, root directory unchanged.
3. Open **Environment Variables** and add these (all environments):

| Name | Value |
|---|---|
| `DATABASE_URL` | the Neon pooled connection string from step 1 |
| `OTP_PEPPER` | any long random secret, 40+ characters (make one with a password manager, or `openssl rand -base64 48`) |
| `OTP_ALLOWED_DOMAINS` | `fiberathome.net` (add `,gmail.com` only if you are testing with Gmail addresses) |
| `BREVO_API_KEY` | the Brevo API key (starts with `xkeysib-`) |
| `SMTP_FROM` | `Fiber@Home Knowledge Vault <the verified Brevo sender address>` |
| `COOKIE_SECURE` | `true` |

4. Click **Deploy**. When it finishes, Vercel shows your address, for example `https://f-h-knowledge-vault.vercel.app`.

## 4. Check it works
1. Open the address: you see only the sign-in page.
2. Enter a staff email from your list → the code arrives by email (check spam the first time) → enter it → the vault opens.
3. A wrong code is refused. An email that is not on the list receives nothing.
4. Sign out, press Back: the vault must not reappear.

## Updating later
Push changes to `main` on GitHub; Vercel redeploys by itself. Adding staff: run more SQL in Neon's SQL Editor.

## If something fails
Vercel → your project → **Deployments → the latest → Logs** (build) or **Logs** tab (runtime). Send the red error lines to Claude.

## Known limits of the free setup
- The first request after a quiet period can take a few seconds (database and function wake up).
- Neon free: 0.5 GB storage, pauses when idle. Brevo free: 300 emails a day.
- Edits made in the vault's Update Center are held in each browser only (see `docs/00-status.md`).
