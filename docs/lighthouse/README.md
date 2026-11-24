# Lighthouse: before and after the speed work (23 Nov 2026)

Lighthouse 12.8.2, desktop preset, run against the app on the laptop
(`DEMO_N8N_MS=800 uv run python ../deck/demo_server.py`: made-up emails, each n8n call takes
800 ms) with a 450 ms round trip added, like Cloudflare → srv1 → ai. "Before" is commit `5519bf3`,
"after" is `b87bda4`. The demo session cookie in the reports is blanked out.

| Page | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| Sign-in, before | 96 | 95 | 96 | 90 |
| Sign-in, after | 96 | **100** | **100** | **100** |
| Queue, before | 91 | 95 | 96 | 90 |
| Queue, after | **96** | **100** | **100** | **100** |

| Page | First paint | Largest paint | Speed index | Blocking time | Layout shift |
|---|---|---|---|---|---|
| Sign-in, before | 1.1 s | 1.1 s | 1.1 s | 0 ms | 0.005 |
| Sign-in, after | 1.1 s | 1.1 s | 1.1 s | 0 ms | 0 |
| Queue, before | 1.1 s | 1.6 s | 1.4 s | 0 ms | 0 |
| Queue, after | 1.1 s | 1.2 s | 1.1 s | 0 ms | 0 |

What Lighthouse flagged before, and what fixed it:

- **Accessibility 95**: text below 4.5:1 contrast (counts, times, section titles, the P1/P2 badges
  on the sign-in page). The colour tokens were darkened (light) and lightened (dark).
- **Best practices 96**: a console error, `/favicon.ico` 404. The pages now link an SVG icon.
- **SEO 90**: no meta description. Both pages have one.
- **Queue performance 91**: the list arrived in a second request after the page. The page now
  carries the list, the account and the open email.

The remaining performance points are the two round trips a first visit cannot avoid (the page,
then its CSS); a repeat visit loads no CSS or JS at all (stamped files, cached a year).

Timings of the steps people repeat all day (open an email, J, E, Undo, switch view) are in
[app/README.md](../../app/README.md#speed).

## Reports

Open the HTML files in a browser (download them; GitHub shows HTML as source). The JSON files
load in the [Lighthouse viewer](https://googlechrome.github.io/lighthouse/viewer/).

| Page | Before | After |
|---|---|---|
| Sign-in | [HTML](before-login.report.html) · [JSON](before-login.report.json) | [HTML](after-login.report.html) · [JSON](after-login.report.json) |
| Queue | [HTML](before-app.report.html) · [JSON](before-app.report.json) | [HTML](after-app.report.html) · [JSON](after-app.report.json) |
