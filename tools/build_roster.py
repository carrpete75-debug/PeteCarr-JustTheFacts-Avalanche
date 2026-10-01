#!/usr/bin/env python3
"""Build docs/roster.html (current Avalanche roster) from the NHL API.

Data:
  - https://api-web.nhle.com/v1/roster/COL/current  (active roster: number, position,
    shoots/catches, height, weight, birth date/place) -- primary list
  - https://api-web.nhle.com/v1/club-stats/COL/now  (season stats, regular season)
  - https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams/col/roster
    (cross-check; ESPN also carries injured-reserve / non-roster players)
  - https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/teams/17/injuries
    (status, type, date ESPN last updated)
Players on ESPN's list but not on the NHL active roster are shown in an
"Injured reserve / non-roster" group ONLY if ESPN lists an injury for them;
any other disagreement exits with ROSTER MISMATCH (use --allow-mismatch to
publish anyway; the page then lists the mismatch).
Writes /workspace/avalanche-data/roster-YYYY-MM-DD.json.
"""
import argparse, html, json, os, sys, unicodedata, urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_chrome  # noqa: E402

MT = ZoneInfo("America/Denver")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
POS = {"C": "C", "L": "LW", "R": "RW", "D": "D", "G": "G"}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url.replace("http://", "https://"), headers=UA), timeout=30) as r:
        return json.load(r)


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())


def age(bd):
    b = date.fromisoformat(bd[:10]); t = date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def ht(inches):
    return f"{inches // 12}′{inches % 12}″" if inches else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "roster.html"))
    ap.add_argument("--allow-mismatch", action="store_true")
    a = ap.parse_args()
    now = datetime.now(MT)

    nhl = get_json("https://api-web.nhle.com/v1/roster/COL/current")
    stats = get_json("https://api-web.nhle.com/v1/club-stats/COL/now")
    espn = get_json("https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams/col/roster")
    inj_idx = get_json("https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/teams/17/injuries")

    injuries = {}
    for it in inj_idx.get("items", []):
        d = get_json(it["$ref"])
        ath = get_json(d["athlete"]["$ref"])
        injuries[norm(ath["displayName"])] = dict(
            name=ath["displayName"], status=d.get("status"), date=(d.get("date") or "")[:10],
            detail=(d.get("details") or {}).get("type"), fantasy=((d.get("details") or {}).get("fantasyStatus") or {}).get("abbreviation"),
            comment=d.get("shortComment"))

    sk = {s["playerId"]: s for s in stats.get("skaters", [])}
    gk = {s["playerId"]: s for s in stats.get("goalies", [])}

    espn_players = {}
    for grp in espn["athletes"]:
        for p in grp["items"]:
            espn_players[norm(p["fullName"])] = p

    players, nhl_keys = [], set()
    for grp in ("forwards", "defensemen", "goalies"):
        for p in nhl.get(grp, []):
            name = f'{p["firstName"]["default"]} {p["lastName"]["default"]}'
            k = norm(name); nhl_keys.add(k)
            pid = p["id"]
            if p["positionCode"] == "G":
                s = gk.get(pid)
                line = (f'{s["gamesPlayed"]} GP · {s.get("wins", 0)}–{s.get("losses", 0)}–{s.get("overtimeLosses", 0)} · '
                        f'{s["savePercentage"]:.3f} SV%' if s and s.get("savePercentage") is not None else None)
            else:
                s = sk.get(pid)
                line = f'{s["gamesPlayed"]} GP · {s["goals"]}–{s["assists"]}–{s["points"]}' if s else None
            ep = espn_players.get(k)
            players.append(dict(group={"forwards": "Forwards", "defensemen": "Defense", "goalies": "Goalies"}[grp],
                                id=pid, name=name, num=p.get("sweaterNumber"), pos=POS.get(p["positionCode"], p["positionCode"]),
                                shoots=p.get("shootsCatches", "—"), ht=ht(p.get("heightInInches")),
                                wt=p.get("weightInPounds"), age=age(p["birthDate"]),
                                birth=", ".join(x for x in [p.get("birthCity", {}).get("default"),
                                                            (p.get("birthStateProvince") or {}).get("default"),
                                                            p.get("birthCountry")] if x),
                                stats=line, injury=injuries.get(k),
                                espn_num=ep.get("jersey") if ep else None, on_espn=bool(ep)))

    ir, mismatch = [], []
    for k, ep in espn_players.items():
        if k in nhl_keys:
            continue
        if k in injuries:
            ir.append(dict(name=ep["fullName"], num=ep.get("jersey"), pos=(ep.get("position") or {}).get("abbreviation", "—"),
                           ht=ep.get("displayHeight", "—"), wt=ep.get("weight"), age=ep.get("age"), injury=injuries[k],
                           espn_url=f'https://www.espn.com/nhl/player/_/id/{ep["id"]}'))
        else:
            mismatch.append(f'{ep["fullName"]} is on ESPN’s roster but not the NHL active roster')
    for p in players:
        if not p["on_espn"]:
            mismatch.append(f'{p["name"]} is on the NHL active roster but not on ESPN’s roster')
    if mismatch and not a.allow_mismatch:
        print("ROSTER MISMATCH:\n  " + "\n  ".join(mismatch)); sys.exit(2)

    def esc(x):
        return html.escape(str(x)) if x not in (None, "") else '<span class="unavail">—</span>'

    rows = []
    for grp in ("Forwards", "Defense", "Goalies"):
        g = sorted([p for p in players if p["group"] == grp], key=lambda p: (p["num"] is None, p["num"] or 0))
        rows.append(f'        <tr class="ros-group"><th colspan="9" scope="colgroup">{grp} · {len(g)}</th></tr>')
        for p in g:
            tag = ""
            if p["injury"]:
                i = p["injury"]
                tag = f' <span class="ros-inj">{html.escape(i["status"] or "Injured")} · {html.escape(i["date"])}</span>'
            fn = ""
            if p["espn_num"] and str(p["num"]) != str(p["espn_num"]):
                fn = '<sup class="ros-fn">†</sup>'
            rows.append(
                f'        <tr><td data-label="#" class="ros-num">{esc(p["num"])}{fn}</td>'
                f'<td data-label="Player" class="ros-player"><a href="https://www.nhl.com/player/{p["id"]}" target="_blank" rel="noopener noreferrer">{html.escape(p["name"])}</a>{tag}</td>'
                f'<td data-label="Pos" class="ros-stat">{p["pos"]}</td><td data-label="Shoots" class="ros-stat">{esc(p["shoots"])}</td>'
                f'<td data-label="Ht" class="ros-stat">{p["ht"]}</td><td data-label="Wt" class="ros-stat">{esc(p["wt"])} lb</td>'
                f'<td data-label="Age" class="ros-stat">{p["age"]}</td><td data-label="Birthplace" class="ros-wide">{esc(p["birth"])}</td>'
                f'<td data-label="Season" class="ros-wide">{esc(p["stats"]) if p["stats"] else "<span class=\"unavail\">No games yet</span>"}</td></tr>')
    if ir:
        rows.append(f'        <tr class="ros-group"><th colspan="9" scope="colgroup">Injured reserve / non-roster (ESPN) · {len(ir)}</th></tr>')
        for p in sorted(ir, key=lambda p: int(p["num"] or 999)):
            i = p["injury"]
            rows.append(
                f'        <tr class="ros-camp"><td data-label="#" class="ros-num">{esc(p["num"])}</td>'
                f'<td data-label="Player" class="ros-player"><a href="{p["espn_url"]}" target="_blank" rel="noopener noreferrer">{html.escape(p["name"])}</a>'
                f' <span class="ros-inj">{html.escape(i.get("fantasy") or i["status"] or "IR")} · {html.escape(i["date"])}</span></td>'
                f'<td data-label="Pos" class="ros-stat">{html.escape(p["pos"])}</td><td data-label="Shoots" class="ros-stat"><span class="unavail">—</span></td>'
                f'<td data-label="Ht" class="ros-stat">{html.escape(p["ht"].replace(" ", ""))}</td><td data-label="Wt" class="ros-stat">{esc(int(p["wt"]) if p["wt"] else None)} lb</td>'
                f'<td data-label="Age" class="ros-stat">{esc(p["age"])}</td><td data-label="Birthplace" class="ros-wide"><span class="unavail">—</span></td>'
                f'<td data-label="Season" class="ros-wide">{html.escape(i.get("detail") or "Undisclosed")}</td></tr>')

    notes = []
    if any(p["espn_num"] and str(p["num"]) != str(p["espn_num"]) for p in players):
        notes.append("† Jersey number differs on ESPN; the NHL number is shown.")
    if mismatch:
        notes.append("Roster check: " + "; ".join(mismatch) + ".")
    notes_html = "".join(f'<p class="ros-foot">{html.escape(n)}</p>' for n in notes)

    if injuries:
        inj_rows = "".join(
            f'<tr><td>{html.escape(i["name"])}</td><td>{html.escape(i.get("detail") or "Undisclosed")}</td>'
            f'<td>{html.escape(i.get("fantasy") or i["status"] or "")}</td><td>{html.escape(i["date"])}</td></tr>'
            for i in sorted(injuries.values(), key=lambda i: i["date"], reverse=True))
        inj_html = ('<div class="table-wrap"><table class="facts"><thead><tr><th>Player</th><th>Injury</th><th>Status</th>'
                    f'<th>ESPN updated</th></tr></thead><tbody>{inj_rows}</tbody></table></div>')
    else:
        inj_html = '<p class="note"><span class="unavail">ESPN lists no Avalanche injuries.</span></p>'

    coach = (espn.get("coach") or [{}])[0]
    coach_name = f'{coach.get("firstName", "")} {coach.get("lastName", "")}'.strip()
    staff = (f'<div><dt>Head coach</dt><dd>{html.escape(coach_name)}</dd></div>' if coach_name
             else '<div><dt>Head coach</dt><dd><span class="unavail">Not listed</span></dd></div>')

    n = len(players)
    by = {g: sum(1 for p in players if p["group"] == g) for g in ("Forwards", "Defense", "Goalies")}
    deck = (f'{n} players on the NHL active roster ({by["Forwards"]} forwards, {by["Defense"]} defensemen, {by["Goalies"]} goalies)'
            + (f', plus {len(ir)} on injured reserve or non-roster IR per ESPN.' if ir else '.'))
    tpl = open(os.path.join(ROOT, "tools", "roster_template.html")).read()
    out = (tpl.replace("{{CSS}}", site_chrome.stylesheet()).replace("{{HEADER}}", site_chrome.header("roster"))
              .replace("{{FOOTER}}", site_chrome.footer("Rosters change often; check the official team roster for the latest."))
              .replace("{{DECK}}", html.escape(deck)).replace("{{TOTAL}}", str(n))
              .replace("{{ASOF}}", now.strftime("%a %b %-d, %Y · %-I:%M %p ") + now.tzname())
              .replace("{{ROWS}}", "\n".join(rows)).replace("{{NOTES}}", notes_html)
              .replace("{{STAFF}}", staff).replace("{{INJURIES}}", inj_html))
    if "{{" in out:
        sys.exit("TEMPLATE ERROR: unreplaced placeholder")
    open(a.out, "w").write(out)
    fp = f"/workspace/avalanche-data/roster-{now:%Y-%m-%d}.json"
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    json.dump(dict(generated=now.isoformat(), players=players, injured_reserve=ir, injuries=list(injuries.values()),
                   mismatch=mismatch, head_coach=coach_name), open(fp, "w"), indent=1)
    print(f"roster.html: {n} active ({by}) + {len(ir)} IR · injuries {len(injuries)} · mismatches {len(mismatch)} · coach {coach_name} · {fp}")
    for m in mismatch:
        print("  MISMATCH:", m)


if __name__ == "__main__":
    main()
