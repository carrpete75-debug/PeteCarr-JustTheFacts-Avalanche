"""Shared header/footer markup for Avalanche Desk pages (no JS, locked layout).

Usage: header(active="schedule", prefix="") where prefix is "" from docs/ root
or "../" from docs/archive/. `active` gets aria-current="page"; pass None for
archive snapshots.
"""
CSS_VERSION = "desk-logo-1"  # bump only when docs/styles.css changes (then on every page)

NAV = [("home", "Home", "index.html"), ("schedule", "Schedule", "schedule.html"),
       ("roster", "Roster", "roster.html"), ("archive", "Archive", "archive/index.html"),
       ("hof", "Hall of Fame", "hall-of-fame.html")]


def stylesheet(prefix=""):
    return f'<link rel="stylesheet" href="{prefix}styles.css?v={CSS_VERSION}">'


def nav(active=None, prefix=""):
    out = []
    for key, label, href in NAV:
        h = href
        if prefix == "../":
            h = "index.html" if key == "archive" else "../" + href
        cur = ' aria-current="page"' if key == active else ""
        out.append(f'        <a href="{h}"{cur}>{label}</a>')
    return "\n".join(out)


def header(active=None, prefix=""):
    home = "index.html" if prefix == "" else "../index.html"
    return f'''  <header class="site-header">
    <div class="avalanche-banner" role="img" aria-label="Colorado Avalanche — Just the Facts">
      <span class="avalanche-banner__accent avalanche-banner__accent--left" aria-hidden="true"></span>
      <span class="avalanche-banner__accent" aria-hidden="true"></span>
      <div class="avalanche-banner__inner">
        <div class="avalanche-banner__titles">
          <p class="avalanche-banner__team">Colorado Avalanche</p>
          <span class="avalanche-banner__rule" aria-hidden="true"></span>
          <p class="avalanche-banner__site">Just the Facts</p>
        </div>
      </div>
    </div>
    <img class="avalanche-desk-logo" src="{prefix}avalanche-desk-logo.png" alt="Avalanche Desk logo" width="112" height="112">
    <div class="header-bar">
      <div class="header-inner header-inner--main">
        <div class="brand-block">
          <div>
            <a class="brand" href="{home}">Just the Facts — Avalanche</a>
            <p class="tagline">A daily, unofficial fan briefing</p>
          </div>
        </div>
        <nav class="nav" aria-label="Primary navigation">
{nav(active, prefix)}
      </nav>
      </div>
    </div>
  </header>'''


def footer(extra="Odds and market prices move; this page is a snapshot, not a betting recommendation."):
    return ('  <footer class="footer"><div class="footer-inner"><p>Unofficial fan briefing. '
            'Not affiliated with the Colorado Avalanche or the NHL. ' + extra + '</p></div></footer>')
