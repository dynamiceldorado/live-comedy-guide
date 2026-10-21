#!/usr/bin/env python3
"""Builds the Guide's two pages from data/events.json.

  index.html              public guide (view Public + Both)
  performers/index.html   "For performers" guide (every view)

Usage:
  python3 build.py                      build for today (America/New_York)
  python3 build.py --today 2026-10-18   build as if it were that date
  python3 build.py --out /some/dir      write somewhere else (default: repo root)
  python3 build.py --inline             embed featured images as data URIs
  python3 build.py --sample FILE.json   add sample featured cells (preview only, never publish)

events.json uses the same column names as the Events tab of the Comedy Database sheet,
plus optional date_text, link_label and sort_time. No script ever ships on the pages.
"""
import argparse, base64, datetime as dt, html, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent
GUIDE = "https://guide.dynamiceldorado.com/"
FORM = "https://docs.google.com/forms/d/e/1FAIpQLSdmeltLBWwirmeO_R6KCv9PdUNMEizfonqVJX2pDmcGjky0cQ/viewform"
GENRE = {"clown": "clown", "stand-up": "stand", "improv": "impro", "sketch": "sketch", "variety": "var"}
GENRE_LABEL = {"clown": "Clown", "stand": "Stand-up", "impro": "Improv", "sketch": "Sketch", "var": "Variety"}
TYPE_CHIP = {"class": "Class", "workshop": "Workshop", "festival": "Festival", "deadline": "Deadline",
             "audition": "Audition", "jam": "Jam", "open-mic-special": "Open mic", "headliner": "Touring headliner"}
LINK_LABEL = {"show": "Tickets", "headliner": "Tickets", "class": "Register", "workshop": "Register",
              "festival": "Info", "deadline": "Details", "audition": "Details", "jam": "Info", "open-mic-special": "Info"}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
esc = html.escape


def today_et():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return dt.date.today()


def d(s):
    return dt.date.fromisoformat(s) if s else None


def fmt(day, year=False):
    return f"{DAYS[day.weekday()]} {MONS[day.month - 1]} {day.day}" + (f", {day.year}" if year else "")


def date_text(e, today):
    if e.get("date_text"):
        return e["date_text"]
    s, en = d(e["start_date"]), d(e.get("end_date"))
    yr = s.year != today.year
    if en and en != s:
        if (en - s).days > 6:
            if s.month == en.month:
                return f"{MONS[s.month - 1]} {s.day}–{en.day}" + (f", {s.year}" if yr else "")
            return f"{MONS[s.month - 1]} {s.day} – {MONS[en.month - 1]} {en.day}" + (f", {en.year}" if yr else "")
        if s.month == en.month:
            return f"{DAYS[s.weekday()]}–{DAYS[en.weekday()]} {MONS[s.month - 1]} {s.day}–{en.day}" + (f", {s.year}" if yr else "")
        return f"{fmt(s)} – {fmt(en)}" + (f", {en.year}" if yr else "")
    return fmt(s, yr)


def sort_minutes(e):
    t = e.get("sort_time") or ""
    m = re.match(r"^(\d{1,2}):(\d\d)$", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    txt = e.get("time") or ""
    hits = list(re.finditer(r"(\d{1,2})(?::(\d\d))?\s*(AM|PM)?", txt, re.I))
    if not hits:
        return 24 * 60 - 1  # no time listed: after the timed events that day
    h = hits[0]
    ap = h.group(3)
    if not ap:
        for n in hits[1:]:
            if n.group(3):
                ap = n.group(3)
                break
    hour, minute = int(h.group(1)) % 12, int(h.group(2) or 0)
    if (ap or "").upper() == "PM":
        hour += 12
    return hour * 60 + minute


def tier_rank(e):
    return 1 if e.get("tier") == "Established" else 0  # indie and Dynamic El Dorado first on ties


def windows(today):
    if today.weekday() == 6:  # Sunday run: the week starts tomorrow
        start = today + dt.timedelta(days=1)
    else:
        start = today
    end = start + dt.timedelta(days=(6 - start.weekday()))  # through the coming Sunday
    return start, end, end + dt.timedelta(days=7)


def img_src(e, inline):
    name = (e.get("image_url") or "").strip()
    if not name:
        return None
    if name.startswith(("http://", "https://", "data:")):
        return name
    path = ROOT / "img" / "featured" / pathlib.Path(name).name
    if not path.exists():
        print(f"WARNING: featured image missing for {e['id']}: {path}", file=sys.stderr)
        return None
    if inline:
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    return "/img/featured/" + path.name


def is_featured(e, inline):
    if (e.get("ded_pick") or "").upper() != "Y":
        return None
    note = (e.get("pick_note") or "").strip()
    src = img_src(e, inline)
    if not note or not src:
        print(f"WARNING: {e['id']} has ded_pick = Y but needs a square image and a pick_note to feature; shown as a normal cell.", file=sys.stderr)
        return None
    return src, note


VENUES = json.loads((ROOT / "data" / "venues.json").read_text(encoding="utf8"))


def cell(e, today, inline, compact):
    g = GENRE.get(e.get("genre") or "", "")
    feat = is_featured(e, inline)
    cls = ["ev"]
    if feat:
        cls.append("feat")
    if e.get("tier") == "DED":
        cls.append("ded")
    if e.get("status") == "unconfirmed":
        cls.append("unc")
    out = [f'<article class="{" ".join(cls)}">']
    if feat:
        out.append(f'<img class="fi" src="{esc(feat[0], quote=True)}" width="280" height="280" alt="{esc(e["title"], quote=True)}">')
    out.append('<div class="evb">')
    when = esc(date_text(e, today))
    if e.get("time"):
        when += f'<span class="t">{esc(e["time"])}</span>'
    out.append(f'<p class="when">{when}</p>')
    sq = f'<i class="sq {g}" role="img" aria-label="{GENRE_LABEL[g]}" title="{GENRE_LABEL[g]}"></i>' if g else '<i class="sq none" aria-hidden="true"></i>'
    chips = []
    if e.get("tier") == "DED":
        chips.append('<span class="tier ded">Dynamic El Dorado</span>')
    if e.get("status") == "unconfirmed":
        chips.append('<span class="chip unc">Unconfirmed</span>')
    if e.get("type") in TYPE_CHIP:
        chips.append(f'<span class="chip">{TYPE_CHIP[e["type"]]}</span>')
    if (e.get("cheap_date") or "").upper() == "Y":
        chips.append('<span class="chip cheap">Cheap date</span>')
    title = esc(e["title"])
    if e.get("link"):
        title = f'<a href="{esc(e["link"], quote=True)}">{title}</a>'
    out.append(f'<h4>{sq}{title}</h4>')
    if chips:
        out.append('<p class="chips">' + " ".join(chips) + "</p>")
    venue = e.get("venue") or ""
    venue_html = esc(venue)
    if venue and VENUES.get(venue):
        venue_html = f'<a href="{esc(VENUES[venue], quote=True)}">{venue_html}</a>'
    place = ", ".join(x for x in [venue_html, esc(e.get("area") or "")] if x)
    bits = [x for x in [place, esc(e.get("price_text") or "")] if x]
    if bits:
        out.append(f'<p class="where">{" · ".join(bits)}</p>')
    desc = (e.get("description") or "").strip()
    show_desc = desc and (not compact or e.get("type") not in ("show", "headliner"))
    if show_desc:
        out.append(f'<p class="desc">{esc(desc)}</p>')
    if feat:
        out.append(f'<p class="why"><b>Why we picked it</b>{esc(feat[1])}</p>')
    out.append("</div></article>")
    return "".join(out)


def section(sid, eyebrow, title, lead, cols, items, today, inline):
    if not items:
        return ""
    cells = "\n".join(cell(e, today, inline, compact=(cols == 3)) for e in items)
    lead_html = f'<p class="lead">{lead}</p>' if lead else ""
    return (f'<section id="{sid}">\n<p class="eyebrow">{esc(eyebrow)}</p>\n<h2>{title}</h2>\n{lead_html}\n'
            f'<div class="grid c{cols}">\n{cells}\n</div>\n</section>\n')


def load_events(performers, today):
    events = json.loads((ROOT / "data" / "events.json").read_text(encoding="utf8"))
    keep = []
    for e in events:
        if e.get("status") not in ("verified", "unconfirmed"):
            continue
        if not performers and e.get("view") not in ("Public", "Both"):
            continue
        last = d(e.get("end_date")) or d(e["start_date"])
        if e.get("status") == "verified" and last < today:
            continue
        keep.append(e)
    return keep


def build(performers, today, inline, sample):
    events = load_events(performers, today)
    if sample:  # `sample` is the dict of overrides
        for e in events:
            if e["id"] in SAMPLE:
                e.update(SAMPLE[e["id"]])
    wk_start, wk_end, nx_end = windows(today)
    for e in events:
        s = d(e["start_date"])
        e["_day"] = max(s, wk_start) if s < wk_start else s
        e["_key"] = (e["_day"], sort_minutes(e), tier_rank(e), e["title"].lower())
    confirmed = sorted((e for e in events if e["status"] == "verified"), key=lambda e: e["_key"])
    unconf = sorted((e for e in events if e["status"] == "unconfirmed"), key=lambda e: e["_key"])
    this_w = [e for e in confirmed if e["_day"] <= wk_end]
    next_w = [e for e in confirmed if wk_end < e["_day"] <= nx_end]
    far = [e for e in confirmed if e["_day"] > nx_end]

    def span(a, b):
        return f"{fmt(a)} – {fmt(b)}"

    secs = [
        ("thisweek", sec_title("thisweek", "This Week"), span(wk_start, wk_end), sec_title("thisweek", "This Week"), None, 1, this_w),
        ("nextweek", sec_title("nextweek", "Next Week"), span(wk_end + dt.timedelta(days=1), nx_end), sec_title("nextweek", "Next Week"), None, 2, next_w),
        ("furtherout", sec_title("furtherout", "Further Out"), "", sec_title("furtherout", "Further Out"), None, 3, far),
        ("unconfirmed", sec_title("unconfirmed", "Unconfirmed"), "Dates or details still pending", sec_title("unconfirmed", "Unconfirmed"),
         "These may happen, but we do not have full details yet. Check with the producer before you plan around them.", 3, unconf),
    ]
    after = nx_end + dt.timedelta(days=1)
    secs[2] = ("furtherout", sec_title("furtherout", "Further Out"), f"From {fmt(after)}", sec_title("furtherout", "Further Out"), None, 3, far)

    body, chips = [], []
    for sid, chip, eyebrow, title, lead, cols, items in secs:
        if not items:
            continue
        chips.append(f'<a href="#{sid}">{chip}</a>')
        body.append(section(sid, eyebrow, title, lead, cols, items, today, inline))
    chips.append('<a href="#about">About &amp; Submit</a>')

    head = HEAD
    if performers:
        head = head.replace("<title>Dynamic El Dorado's Guide to Live Comedy in Atlanta",
                            "<title>For Performers · Dynamic El Dorado's Guide to Live Comedy in Atlanta")
        head = head.replace('href="https://guide.dynamiceldorado.com/"', f'href="{GUIDE}performers/"')
        head = head.replace('content="https://guide.dynamiceldorado.com/"', f'content="{GUIDE}performers/"')
        head = re.sub(r'(<meta name="description" content=")[^"]*', r"\1For performers: classes, workshops, festival deadlines, auditions and out-of-town festivals, plus every show in Atlanta comedy. Curated by Dynamic El Dorado.", head)
        head = re.sub(r'(<meta property="og:description" content=")[^"]*', r"\1For performers: classes, workshops, festival deadlines, auditions and out-of-town festivals, plus every show in Atlanta comedy. Curated by Dynamic El Dorado.", head)
        head = head.replace('<meta property="og:title" content="Dynamic El Dorado\'s Guide to Live Comedy in Atlanta">',
                            '<meta property="og:title" content="For Performers · Dynamic El Dorado\'s Guide to Live Comedy in Atlanta">')
    else:
        head = re.sub(r'(<meta name="description" content=")[^"]*', r"\1What's on in Atlanta comedy this week and beyond: independent and established shows, improv, stand-up, sketch and clown, plus festivals. Curated by Dynamic El Dorado.", head)
        head = re.sub(r'(<meta property="og:description" content=")[^"]*', r"\1What's on in Atlanta comedy this week and beyond: independent and established shows, improv, stand-up, sketch and clown, plus festivals. Curated by Dynamic El Dorado.", head)
    head = head.replace("</head>", "")
    head += "<style>\n" + LAYOUT_CSS + "\n</style>\n"

    logo = "data:image/png;base64," + base64.b64encode((ROOT / "parts" / "logo.png").read_bytes()).decode()
    if performers:
        mode_link = '<a class="perf" href="/">← Public guide</a>'
        intro = ('<div class="perfnote"><b>For performers.</b> Everything in the public guide, plus classes, workshops, '
                 'festival deadlines, auditions and festivals outside Atlanta. '
                 'Looking for a night out? <a href="/">Go to the public guide</a>.</div>')
    else:
        mode_link = '<a class="perf" href="/performers/">For performers →</a>'
        intro = ""
    issue = f"This week: {span(wk_start, wk_end)}, {wk_end.year}"
    page = (head + "\n" + TOOLBAR + '\n<article class="sheet">\n'
            + TOPNAV.format(logo=logo, mode_link=mode_link)
            + MAST.format(issue=issue)
            + '  <div class="content">\n    <nav class="toc" aria-label="Sections">' + "".join(chips) + "</nav>\n"
            + intro + LEGEND + "\n".join(body) + ABOUT + "  </div>\n"
            + FOOTER.format(logo=logo, updated=f"{MONS[today.month - 1]} {today.day}, {today.year}") + "</article>\n\n</body></html>\n")
    return page, (len(this_w), len(next_w), len(far), len(unconf))


HEAD = (ROOT / "parts" / "head.html").read_text(encoding="utf8")

TOOLBAR = ""

TOPNAV = """  <nav class="topnav" aria-label="Dynamic El Dorado sites"><a class="home" href="https://dynamiceldorado.com/" aria-label="Dynamic El Dorado"><img src="{logo}" alt="Dynamic El Dorado"></a><div class="navright"><div class="navlinks">{mode_link}<a class="first" href="https://directory.dynamiceldorado.com/">Directory</a><a href="%s" target="_blank" rel="noopener">Submit your info</a></div></div></nav>
""" % FORM

MAST = """  <header class="mast">
    <h1>Live Comedy <em>(cheap!)</em></h1>
    <p class="sub">A guide to Atlanta comedy for smart, sexy people who don’t like to think. We picked out the best shows, classes, and festivals so your beautiful, empty head doesn't have to. Brought to you by Dynamic El Dorado and some random people who gave us random drugs. If you're ugly, please stop reading this. If you're dumb, we would love some comp tickets to your show.</p>
    <div class="issue"><span>{issue}</span></div>
  </header>
"""

LEGEND = """    <div class="legend" aria-label="Key">
      <span><i class="sq clown"></i>Clown</span><span><i class="sq stand"></i>Stand-up</span><span><i class="sq impro"></i>Improv</span><span><i class="sq sketch"></i>Sketch</span><span><i class="sq var"></i>Variety</span>
      <span><span class="tier ded">Dynamic El Dorado</span> produced or co-presented by us</span>
      <span><i class="key-feat"></i>Gold frame: a featured pick</span>
    </div>

"""

ABOUT = """
    <section id="about">
      <p class="eyebrow">About this guide</p>
      <h2>About</h2>
      <div class="about">
        <div><h4>What we're about</h4><p>We're all about supporting the independent shows and venues. Atlanta doesn't get enough recognition nor support for the fantastic comedic talent that it has. We're here to change that.</p></div>
        <div><h4>Where listings come from</h4><p>Listings here come from web searches, gossipy neighbors, word of mouth, the rumor mill, crystal balls, and many other sources.</p></div>
        <div><h4>More resources</h4><p><a href="https://directory.dynamiceldorado.com/">Atlanta Comedy Directory</a> of venues, troupes, open mics, classes and festivals.</p></div>
      </div>
      <div id="submit" style="margin-top:28px">
      <h3>Submit Your Thing</h3>
      <p class="lead">Running a show, class, workshop, open mic or festival in metro Atlanta or the Southeast? Send it in. Listings are free, and every one is reviewed before it goes up.</p>
      <a class="cta" href="%s" target="_blank" rel="noopener" style="display:inline-block;background:var(--green);color:var(--on-green);text-decoration:none;font-weight:700;padding:12px 20px;border-radius:6px">Submit Your Thing →</a>
      <p class="quiet" style="margin-top:12px">Takes about three minutes.</p></div>
    </section>
""" % FORM

FOOTER = """  <footer class="foot">
    <a class="foot-logo" href="https://dynamiceldorado.com/" aria-label="Dynamic El Dorado"><img src="{logo}" alt="Dynamic El Dorado"></a>
    <p>Published by: Dynamic El Dorado, Atlanta's Comedy Incubator</p>
    <div class="row">
      <a href="https://directory.dynamiceldorado.com/">Atlanta Comedy Directory</a>
      <a href="https://www.crowdwork.com/v/dynamiceldorado/shows">Shows</a>
      <a href="https://www.crowdwork.com/v/dynamiceldorado/classes">Classes</a>
      <a href="https://www.instagram.com/dynamiceldorado/">Instagram</a>
      <a href="https://www.facebook.com/DynamicElDorado">Facebook</a>
    </div>
    <p class="legal">We build this Guide from venue and ticketing pages and community submissions, and we do our best to keep it current. We still get things wrong and leave things out. Dates, times, prices, lineups and ticket links change without notice, so confirm with the venue or ticket seller before you go. The Guide is provided as is. Dynamic El Dorado is not responsible for errors, omissions, cancellations or changes, or for the content, policies or conduct of third-party venues, producers or sites we link to. A listing is not an endorsement, and a missing one is not a snub. Spot a mistake? <a href="%s">Tell us here</a>.</p>
    <p class="updated">Last updated {updated}</p>
  </footer>
""" % FORM

LAYOUT_CSS = (ROOT / "parts" / "layout.css").read_text(encoding="utf8")

# Sample featured cells for the preview only (placeholder squares, invented text). Never published.
SAMPLE = {}


# Window titles come from sections.json (synced from the Comedy Database sheet).
# Order is not editable here: the windows always run in calendar order.
def load_section_titles():
    path = pathlib.Path(__file__).parent / "sections.json"
    if not path.exists():
        return {}
    return {r["key"]: r["title"] for r in json.loads(path.read_text(encoding="utf-8")) if r.get("active", True)}


SECTION_TITLES = load_section_titles()


def sec_title(key, default):
    return SECTION_TITLES.get(key, default)


def main():
    global SAMPLE
    ap = argparse.ArgumentParser()
    ap.add_argument("--today")
    ap.add_argument("--out", default=str(ROOT))
    ap.add_argument("--inline", action="store_true")
    ap.add_argument("--sample", metavar="FILE", help="JSON of sample featured cells (preview only, never publish)")
    a = ap.parse_args()
    today = d(a.today) if a.today else today_et()
    out = pathlib.Path(a.out)
    if a.sample:
        SAMPLE = json.loads(pathlib.Path(a.sample).read_text(encoding="utf8"))
    for performers, rel in ((False, "index.html"), (True, "performers/index.html")):
        page, counts = build(performers, today, a.inline, bool(a.sample))
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf8")
        print(f"{rel}: this week {counts[0]} · next week {counts[1]} · further out {counts[2]} · unconfirmed {counts[3]}")


if __name__ == "__main__":
    main()
