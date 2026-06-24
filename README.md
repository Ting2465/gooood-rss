# Gooood RSS

Auto-scrapes [gooood.cn](https://www.gooood.cn/) for the latest 100 articles and serves them as a standard RSS 2.0 feed, hosted on GitHub Pages. Works with Inoreader, Feedly, NetNewsWire, etc.

## Feed URL

Once deployed:

```
https://ting2465.github.io/gooood-rss/gooood.xml
```

## Deploy

### 1. Create an empty GitHub repo

- Open https://github.com/new
- Repository name: `gooood-rss`
- Visibility: `Public` (required for free GitHub Pages)
- Do NOT check "Add a README file" / "Add .gitignore" / "Choose a license"
- Click `Create repository`

### 2. Push the code

From the project root, in a terminal:

```bash
git init
git add .
git commit -m "init: gooood RSS"
git branch -M main
git remote add origin https://github.com/ting2465/gooood-rss.git
git push -u origin main
```

### 3. Enable GitHub Pages

Open `https://github.com/ting2465/gooood-rss/settings/pages`

- Source: `GitHub Actions`
- Wait 1-2 minutes for the first deploy

### 4. Verify

Open in browser:

```
https://ting2465.github.io/gooood-rss/gooood.xml
```

You should see 100 `<item>` entries in RSS XML.

### 5. Add to Inoreader

- Open https://www.inoreader.com/
- Click `+ Add a subscription` -> `Feed URL`
- Paste the feed URL above -> `Add`
- Done.

## Update frequency

GitHub Actions runs every day at UTC 16:00 (Beijing 00:00), re-scrapes gooood, and pushes a fresh `gooood.xml` to Pages.

Manual trigger:
- Open repo -> `Actions` tab -> select `Build Gooood RSS` -> `Run workflow`

## Run locally

```bash
pip install -r requirements.txt   # no external deps currently
python build_rss.py               # generates gooood.xml
```

## Files

```
.
├── .github/workflows/build.yml   # GitHub Actions: daily cron + manual trigger
├── build_rss.py                  # RSS generator (Python 3.10+, stdlib only)
├── gooood.xml                    # output (auto-maintained by Actions)
├── index.html                    # friendly landing page
├── requirements.txt              # Python deps
└── README.md
```

## License

MIT
