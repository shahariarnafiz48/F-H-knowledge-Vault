# Free live demo on Vercel (real email-code sign-in)

Everything below uses free plans: **GitHub** (code), **Neon** (database), **Gmail** (sends the codes) and **Vercel** (hosting). About 20 minutes.

> **Use for a demo / pilot only.** Vercel's free *Hobby* plan is for personal, non-commercial use. For permanent company use, move to the paid Vercel Pro plan or the VPS in `DEPLOY.md` (same code, nothing to rebuild).

## 1. Database (Neon, free)
1. Sign up at neon.com (use "Continue with GitHub").
2. **Create project** → name `fh-vault` → **Region: Asia Pacific (Singapore)** → Postgres 16 or newer → Create.
3. On the project dashboard click **Connect**. Tick **Connection pooling** and copy the connection string. It looks like `postgresql://user:password@ep-xxxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`. Keep it private; this is `DATABASE_URL`.
4. Open **SQL Editor**, paste the **entire** contents of `db/schema.sql`, click **Run**. It should finish without errors.
5. Make your staff list `staff.csv` (header `email,name,role`; role = viewer / editor / reviewer / admin). Give it to the person who runs `python3 scripts/staff_to_sql.py staff.csv > staff.sql` (or send it to Claude to generate). Paste `staff.sql` into the SQL Editor and **Run**. Include yourself as `admin`.

## 2. Mailbox that sends the codes (Gmail, free)
1. In the Google account that will send the codes: **Manage your Google Account → Security → 2-Step Verification** (turn it on).
2. Search "App passwords", create one named `fh-vault`, and copy the 16-character password. This is `SMTP_PASSWORD`.
3. Limit: about 500 emails a day, plenty for a demo. Codes show the Gmail address as the sender.

## 3. Publish on Vercel
1. Sign up at vercel.com with **Continue with GitHub**. When asked, let Vercel access `F-H-knowledge-Vault` (private repo: choose "Only select repositories").
2. **Add New → Project → Import** `F-H-knowledge-Vault`. Leave **Framework Preset = Other**, root directory unchanged.
3. Open **Environment Variables** and add these (all environments):

| Name | Value |
|---|---|
| `DATABASE_URL` | the Neon pooled connection string from step 1 |
| `OTP_PEPPER` | any long random secret, 40+ characters (make one with a password manager, or `openssl rand -base64 48`) |
| `OTP_ALLOWED_DOMAINS` | `fiberathome.net` (add `,gmail.com` only if you are testing with Gmail addresses) |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_SECURITY` | `ssl` |
| `SMTP_USER` | the Gmail address |
| `SMTP_PASSWORD` | the 16-character app password |
| `SMTP_FROM` | `Fiber@Home Knowledge Vault <the Gmail address>` |
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
- Neon free: 0.5 GB storage, pauses when idle. Gmail: ~500 codes a day.
- Edits made in the vault's Update Center are held in each browser only (see `docs/00-status.md`).
