#!/usr/bin/env python3
"""Build docs/schedule.html (full Avalanche season schedule) from the NHL API.

Data: https://api-web.nhle.com/v1/club-schedule-season/COL/<season|now> is the
single source for dates, opponents, venues, US TV, results and ticket links.
Ticket links are the `ticketsLink` the NHL publishes for each game: the Avs'
own avs.social short links (resolved to the Ticketmaster event they redirect
to) for home games and the host team's official Ticketmaster link for road
games. Tracking params (utm_*, wt.mc_id, camefrom) are stripped; the event ID
is never changed. If a game has no ticketsLink, the host team's official
nhl.com/<team>/tickets page is used. No resale links.

Usage: python3 tools/build_schedule.py [--season 20262027] [--out docs/schedule.html]
Writes /workspace/avalanche-data/schedule-YYYY-MM-DD.json.
"""
import argparse, html, json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_chrome  # noqa: E402

MT = ZoneInfo("America/Denver")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AvalancheDesk/1.0"}
# Host team official tickets pages (fallback only when the NHL lists no ticketsLink)
SLUG = {"ANA": "ducks", "BOS": "bruins", "BUF": "sabres", "CAR": "hurricanes", "CBJ": "bluejackets",
        "CGY": "flames", "CHI": "blackhawks", "COL": "avalanche", "DAL": "stars", "DET": "redwings",
        "EDM": "oilers", "FLA": "panthers", "LAK": "kings", "MIN": "wild", "MTL": "canadiens",
        "NJD": "devils", "NSH": "predators", "NYI": "islanders", "NYR": "rangers", "OTT": "senators",
        "PHI": "flyers", "PIT": "penguins", "SEA": "kraken", "SJS": "sharks", "STL": "blues",
        "TBL": "lightning", "TOR": "mapleleafs", "UTA": "mammoth", "VAN": "canucks", "VGK": "goldenknights",
        "WPG": "jets", "WSH": "capitals"}
STRIP = ("utm_", "wt.mc_id", "camefrom")


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def clean(url):
    p = urllib.parse.urlsplit(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(STRIP)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))


def resolve(url):
    """Follow a team short link (avs.social) to the seller URL it points at.
    Ticketmaster answers bots with 401/403, so we read the redirect target only."""
    if "avs.social" not in url:
        return url
    req = urllib.request.Request(url, headers=UA, method="GET")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(req, timeout=20)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
        if loc and "ticketmaster" in loc:
            return loc
    except Exception:
        pass
    return url  # keep the official short link if it can't be resolved


def tv_list(g):
    nets = [b["network"] for b in g.get("tvBroadcasts", []) if b.get("countryCode") == "US"]
    seen = []
    for n in nets:
        if n not in seen:
            seen.append(n)
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="now")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "schedule.html"))
    a = ap.parse_args()
    data = get_json(f"https://api-web.nhle.com/v1/club-schedule-season/COL/{a.season}")
    games = data["games"]
    season = str(data.get("currentSeason") or games[0]["season"])
    s_label = f"{season[:4]}–{season[6:]}"
    now = datetime.now(MT)

    rec = {1: [0, 0, 0], 2: [0, 0, 0], 3: [0, 0, 0]}
    groups, order, facts = {}, [], []
    tix_event = tix_general = 0
    for g in games:
        gt = g["gameType"]
        start = datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")).astimezone(MT)
        home = g["homeTeam"]["abbrev"] == "COL"
        opp = g["awayTeam"] if home else g["homeTeam"]
        opp_name = opp.get("commonName", {}).get("default", opp["abbrev"])
        host = g["homeTeam"]["abbrev"]
        state = g.get("gameState")
        done = state in ("FINAL", "OFF")
        result = None
        if done:
            us = g["homeTeam" if home else "awayTeam"].get("score")
            them = g["awayTeam" if home else "homeTeam"].get("score")
            last = (g.get("gameOutcome") or {}).get("lastPeriodType", "REG")
            r = rec[gt]
            if us > them:
                r[0] += 1; wl = "W"
            elif last in ("OT", "SO"):
                r[2] += 1; wl = "OTL" if last == "OT" else "SOL"
            else:
                r[1] += 1; wl = "L"
            suffix = f" ({last})" if last in ("OT", "SO") else ""
            cls = "sched-w" if wl == "W" else "sched-l"
            result = (f'<span class="{cls}">{wl}</span> {us}–{them}{suffix} '
                      f'<span class="sched-rec">({r[0]}–{r[1]}–{r[2]})</span>')
        tz = start.tzname()
        time_s = start.strftime("%-I:%M %p ") + tz
        if g.get("gameScheduleState") not in (None, "OK"):
            time_s = f'<span class="unavail">{html.escape(g["gameScheduleState"])}</span>'
        tv = tv_list(g)
        tix_html, tix_url, tix_kind = "", None, None
        if not done:
            raw = g.get("ticketsLink")
            if raw:
                tix_url = clean(resolve(raw)); tix_kind = "event"; tix_event += 1
                seller = "Avalanche official schedule" if home else f"{opp_name} official schedule"
            else:
                tix_url = f"https://www.nhl.com/{SLUG.get(host, 'avalanche')}/tickets"; tix_kind = "general"; tix_general += 1
                seller = f"{'Avalanche' if home else opp_name} official tickets page"
            away_n = opp_name if home else "Avalanche"
            home_n = "Avalanche" if home else opp_name
            label = f"Tickets: {away_n} at {home_n}, {start.strftime('%b %-d')}, {g['venue']['default']} ({seller})"
            tix_html = (f'<a class="ticket-link" href="{html.escape(tix_url)}" target="_blank" rel="noopener noreferrer" '
                        f'aria-label="{html.escape(label)}">Tickets</a>')
        key = ("pre", "Preseason") if gt == 1 else (("post", "Postseason") if gt == 3 else
              (start.strftime("m-%Y-%m"), start.strftime("%B %Y") + " · regular season"))
        if key not in groups:
            groups[key] = []; order.append(key)
        venue = html.escape(g["venue"]["default"])
        row = (f'        <tr{" class=\"is-home\"" if home else ""}><td data-label="Date">{start.strftime("%a, %b %-d")}</td>'
               f'<td data-label="Opponent"><span class="sched-ha">{"vs" if home else "@"}</span> {html.escape(opp_name)}</td>'
               f'<td data-label="Venue">{venue}</td>'
               f'<td data-label="Time / result">{result or time_s}</td>'
               f'<td data-label="TV">{" · ".join(html.escape(t) for t in tv) if tv else ("<span class=\"unavail\">Not listed</span>" if done else "<span class=\"unavail\">TBD</span>")}</td>'
               f'<td data-label="Tickets" class="sched-tix">{tix_html}</td></tr>')
        groups[key].append((row, home))
        facts.append(dict(id=g["id"], gameType=gt, date_mt=start.isoformat(), home=home, opponent=opp["abbrev"],
                          venue=g["venue"]["default"], state=state, tv_us=tv, result=result and html.unescape(
                              result.replace('<span class="sched-w">', "").replace('<span class="sched-l">', "")
                              .replace('<span class="sched-rec">', "").replace("</span>", "")),
                          tickets=tix_url, tickets_type=tix_kind, tickets_raw=g.get("ticketsLink")))

    sections = []
    head = ('<div class="table-wrap"><table class="facts sched-table"><thead><tr><th scope="col">Date (MT)</th>'
            '<th scope="col">Opponent</th><th scope="col">Venue</th><th scope="col">Time (MT) / result</th>'
            '<th scope="col">TV (US)</th><th scope="col"><span class="sr-only">Tickets</span></th></tr></thead><tbody>')
    for key in order:
        rows = groups[key]
        hid = key[0]
        title = key[1] if key[0] != "pre" else f"Preseason · {s_label}"
        sections.append(
            f'    <section class="card sched-month" aria-labelledby="{hid}-heading">\n'
            f'      <div class="card-head"><h2 id="{hid}-heading">{html.escape(title)}</h2>'
            f'<span class="sched-count">{len(rows)} games · {sum(1 for _, h in rows if h)} home</span></div>\n'
            f'      {head}\n' + "\n".join(r for r, _ in rows) + "\n      </tbody></table></div>\n    </section>\n")

    pre_n = sum(1 for g in games if g["gameType"] == 1)
    reg = [g for g in games if g["gameType"] == 2]
    reg_home = sum(1 for g in reg if g["homeTeam"]["abbrev"] == "COL")
    fmt = lambda r: f"{r[0]}–{r[1]}–{r[2]}"
    tpl = open(os.path.join(ROOT, "tools", "schedule_template.html")).read()
    out = (tpl.replace("{{CSS}}", site_chrome.stylesheet())
              .replace("{{HEADER}}", site_chrome.header("schedule"))
              .replace("{{FOOTER}}", site_chrome.footer("Schedule, TV and times can change; check the official team schedule before you go."))
              .replace("{{SEASON}}", s_label).replace("{{PRE_N}}", str(pre_n)).replace("{{REG_N}}", str(len(reg)))
              .replace("{{HOME_N}}", str(reg_home)).replace("{{AWAY_N}}", str(len(reg) - reg_home))
              .replace("{{REG_REC}}", fmt(rec[2])).replace("{{PRE_REC}}", fmt(rec[1]))
              .replace("{{ASOF}}", now.strftime("%a %b %-d, %Y · %-I:%M %p ") + now.tzname())
              .replace("{{TIX_EVENT}}", str(tix_event)).replace("{{TIX_GENERAL}}", str(tix_general))
              .replace("{{SECTIONS}}", "".join(sections)))
    if "{{" in out:
        sys.exit("TEMPLATE ERROR: unreplaced placeholder")
    open(a.out, "w").write(out)
    os.makedirs("/workspace/avalanche-data", exist_ok=True)
    fp = f"/workspace/avalanche-data/schedule-{now:%Y-%m-%d}.json"
    json.dump(dict(generated=now.isoformat(), season=season, preseason=pre_n, regular=len(reg),
                   record_regular=fmt(rec[2]), record_preseason=fmt(rec[1]), tickets_event=tix_event,
                   tickets_general=tix_general, games=facts), open(fp, "w"), indent=1)
    print(f"schedule.html: {pre_n} preseason + {len(reg)} regular ({reg_home} home) · REG {fmt(rec[2])} · PRE {fmt(rec[1])}"
          f" · tickets {tix_event} event / {tix_general} general · fact pack {fp}")


if __name__ == "__main__":
    main()
