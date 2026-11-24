# Germany Job Agent

Find jobs in Germany for **your field and your city**, get a **daily digest** on your phone, and **track every application** — without signing up anywhere, installing anything, or handing your data to anyone.

- **Daily job feed.** Every morning at 08:00 (Berlin time) it searches the Bundesagentur für Arbeit, Arbeitnow and Remotive, removes duplicates, scores each listing for fit, and publishes a dashboard on your own GitHub Pages site.
- **Daily notification.** A short digest of new matches arrives as a GitHub notification (GitHub mobile app and email). Telegram is optional.
- **Application tracker.** Press **Applied** on a listing, or answer *“Did you apply?”* when you come back from a posting, and it lands in *My applications* with status, notes, follow-up reminders and stats. Gmail auto-detection is optional.
- **Your data stays yours.** The job feed is public listings. Everything you save, apply to or write is stored only in your browser. There is no server and no database, and nothing is collected.

Live example: **https://ot-coder.github.io/germany-job-agent/** (computer-science roles across Germany plus part-time work around Leipzig).

## Get your own in 5 minutes

You only need a free GitHub account.

1. **Copy it.** Click **Use this template → Create a new repository** at the top of this page. Keep it **public**: GitHub Pages is free for public repositories.
2. **Turn on the website.** In your new repository open **Settings → Pages**, and under *Build and deployment → Source* choose **GitHub Actions**.
3. **Tell it what you're looking for.** Open the **Actions** tab, choose **Set up my job agent → Run workflow**, and fill in:
   | Field | Example |
   |---|---|
   | Job field (comma-separated, add German words) | `marketing, social media, kommunikation` |
   | City | `Köln` |
   | Radius (km) | `30` |
   | Level | `student` (Werkstudent + entry level), `entry`, or `any` (any non-senior role) |
   | Where to look for your field | `germany` or `local` |
   | Also list part-time/minijobs near you | ✓ |

That's it. The first search starts automatically. A few minutes later your dashboard is live at `https://<your-username>.github.io/<repository-name>/` and your first digest issue appears.

> **Phone notifications:** install the GitHub mobile app and allow notifications. The daily digest is assigned to you, so it shows up there and in your email. To change what you receive, go to **github.com/settings/notifications**.

## Tracking applications

| How | What happens |
|---|---|
| **Applied** button on a job | Adds it to *My applications*, linked to the listing. |
| Open a posting, then come back | A banner asks *“Did you apply to … ?”*. One tap logs it. |
| **+ Add application** | Adds a job you found elsewhere. |
| **Gmail auto-detection** (optional) | Scans recent emails for application confirmations, in your browser. See [guides/gmail.md](guides/gmail.md). |

Statuses are Applied, Waiting, Interview, Offer, Rejected and Ghosted. An application with no answer after 14 days is automatically treated as *ghosted* and shows up under **Follow-up needed**.

**Backups and other devices.** Your tracker lives in the browser you use it in. Use **Settings → Export backup** now and then, and **Import** to restore it or move it to another device or browser. Import also accepts exports from the older *job-tracker* app.

## Configuration

The setup form writes [`jobs-agent.toml`](jobs-agent.toml). You can also edit that file directly on GitHub. Each `[[categories]]` entry becomes one tab on the dashboard.

```toml
[profile]
title = "Marketing jobs · Köln"
city = "Köln"
radius_km = 30
nearby_towns = []          # empty: trust the Bundesagentur radius search; or list towns to allow
min_score = 55             # 0–100; raise it for fewer, better matches
include_remote = true      # also pull remote roles from Remotive
gmail_client_id = ""       # optional, see guides/gmail.md (a client ID is not a secret)

[[categories]]
id = "field"
label = "Marketing"
scope = "germany"          # "germany" or "local" (within radius_km of city)
keywords = ["marketing", "social media", "kommunikation"]   # one must appear in the job title
levels = ["werkstudent", "entry-level", "part-time", "minijob"]  # add "any" for regular roles
queries = ["werkstudent marketing", "junior marketing"]          # searches sent to the Bundesagentur
```

**Job sources:** two of the three sources (Bundesagentur für Arbeit and Arbeitnow) only cover Germany.

## Run it on your own computer instead

Needs Python 3.11 or newer. There are no other dependencies.

```bash
git clone https://github.com/ot-coder/germany-job-agent.git && cd germany-job-agent
python3 -m jobs_agent setup --field "software, entwickler" --city Leipzig   # writes jobs-agent.toml
python3 -m jobs_agent serve --refresh                                        # fetch jobs, open http://127.0.0.1:8787
```

Without GitHub Actions there are no daily notifications. Run `serve --refresh` whenever you want fresh listings.

## Privacy

- **Public:** your copy's `jobs-agent.toml` (job field and city) and the job listings, because a free GitHub Pages site needs a public repository.
- **Private, in your browser only:** saved and dismissed jobs, applications, notes, your Gmail client ID setting and anything detected from Gmail. Gmail is read directly from your browser using *your own* Google OAuth client. The access token is discarded after each scan.
- **Encrypted GitHub secrets:** your Telegram bot token, if you use Telegram.
- **Nothing is sent to the project author.** There is no analytics, tracking or telemetry.

## Optional: Telegram

Create a bot with [@BotFather](https://t.me/BotFather), send it any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your chat ID. Add both under **Settings → Secrets and variables → Actions** as `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## How it works

```text
GitHub Actions (daily, in your copy)        Your browser
┌──────────────────────────────────┐        ┌───────────────────────────────────┐
│ jobs_agent publish               │        │ docs/index.html + app.js          │
│  sources.py  fetch & normalise   │ Pages  │  Jobs tab   ← jobs.json           │
│  core.py     categorise & score  ├───────►│  Tracker    ← localStorage        │
│  publish.py  jobs.json, digest   │        │  gmail.js   → Gmail API (optional)│
│ gh issue create  → notification  │        └───────────────────────────────────┘
└──────────────────────────────────┘
```

```text
jobs-agent.toml            your search configuration
jobs_agent/config.py       config loading and defaults
jobs_agent/sources.py      job sources, local filtering, de-duplication
jobs_agent/core.py         role classification and scoring
jobs_agent/publish.py      static site, jobs.json, notification texts
jobs_agent/setup.py        turns setup answers into jobs-agent.toml
jobs_agent/site/           the dashboard and tracker (plain HTML/CSS/JS, no build step)
jobs_agent/cli.py          fetch, publish, serve and setup commands
.github/workflows/         daily refresh and the one-time setup form
tests/                     Python tests (unittest) and JS tests (node --test)
```

## Contributing

Issues and pull requests are welcome. Run the tests before opening a pull request:

```bash
python3 -m unittest discover -s tests
node --test tests/js/*.test.mjs
```

Job availability changes constantly, so always check a posting on its source page before applying.

## License

[MIT](LICENSE)
