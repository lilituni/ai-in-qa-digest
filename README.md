Fetches today's LinkedIn posts from a profile and sends each one to a
Telegram channel through a bot.
 
## What it does
 
```
Fetch posts (Apify)  →  Keep only today's posts  →  Format message  →  Send to Telegram
```
 
1. Calls an Apify actor that reads a public LinkedIn profile — no login
   required.
2. Keeps only posts whose `datePublished` falls on today's calendar date, in
   the `TIMEZONE` you configure. Older posts are skipped even if they're
   still at the top of the feed.
3. Sends each matching post to Telegram: author, a short excerpt, and a link
   to the original.
4. If nothing matches, it sends one "No new posts today." message instead.
## This is a scheduled job, not something you run by hand
 
`digest.py` itself just runs once and exits — it doesn't loop or wait. The
"runs once a day" part comes from **GitHub Actions**, which acts as the
cron scheduler: it checks out the repo, installs dependencies, and runs
`python digest.py` on a timer, on GitHub's servers — not your laptop.
 
The schedule lives in `.github/workflows/daily-digest.yml`:
 
```yaml
on:
  schedule:
    - cron: "0 17 * * *"   # 17:00 UTC = 21:00 Yerevan time, every day
  workflow_dispatch:        # lets you trigger a run manually, for testing
```
 
Cron time is always **UTC**. [crontab.guru](https://crontab.guru) is useful
for building or checking an expression.
 
Because it runs on GitHub's servers, it fires every day whether or not your
computer is on — which is the point: the assignment requires the job to run
with no manual trigger, and a local cron job only manages that if your
laptop is awake at the scheduled time every single day.
 
**To test the schedule without waiting a day:** push the repo, add your
secrets, then go to the repo's **Actions** tab → **Daily Influencer Digest**
→ **Run workflow**. That button only exists because of
`workflow_dispatch` in the yaml.
 
## Configuration
 
All settings come from environment variables — nothing is hardcoded.
Locally these come from a `.env` file (never committed); on GitHub Actions
they come from repository secrets.
 
| Variable | Required | Default |
|---|---|---|
| `APIFY_TOKEN` | yes | — |
| `TELEGRAM_BOT_TOKEN` | yes | — |
| `TELEGRAM_CHAT_ID` | yes | — |
| `PROFILE_URL` | no | Lex Fridman's LinkedIn profile |
| `AUTHOR_NAME` | no | "Lex Fridman" |
| `APIFY_ACTOR` | no | `myagizm~linkedin-profile-posts-scraper` |
| `TIMEZONE` | no | `Asia/Yerevan` |
| `SEND_EMPTY_MESSAGE` | no | `true` |
 
## Running it locally (for development, not the daily schedule)
 
```bash
pip install -r requirements.txt
cp .env.example .env      # fill in real values
python digest.py --debug
```
 
`--debug` prints the field names and raw date value from the first fetched
post, and every post's date — useful for confirming the actor's output
shape before trusting the filter.