# Product Feed Watcher (GitHub Actions)

Cloud-based RSS/Atom watcher that checks product feeds on a schedule and emails alerts for new products.

## What it does

- Polls one or more feeds on a schedule (every 10 minutes by default)
- Tracks seen entries in `seen_feed_items.json`
- Sends email only for newly discovered products
- Commits updated state file automatically from GitHub Actions

## Configure repository secrets

In GitHub: **Settings -> Secrets and variables -> Actions -> New repository secret**

Required:

- `FEED_URLS`: comma-separated feed URLs
  - Example: `https://site1.com/collections/all.atom,https://site2.com/feed`
- `SMTP_USERNAME`: sender account username
- `SMTP_PASSWORD`: sender account password or app password
- `EMAIL_TO`: comma-separated recipients
  - Example: `you@example.com` or `you@example.com,friend@example.com`

Optional (recommended):

- `SMTP_HOST`: defaults to `smtp.gmail.com`
- `SMTP_PORT`: defaults to `465`
- `EMAIL_FROM`: defaults to `SMTP_USERNAME`

## Run manually

1. Open the **Actions** tab
2. Select **Watch product feeds**
3. Click **Run workflow**

First run bootstraps existing feed entries and should not email historical products.

## Local run (optional)

```bash
pip install -r requirements.txt
python rss_product_watcher.py
```

Set environment variables locally before running.
