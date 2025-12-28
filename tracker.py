import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

OUT_FILE = "pinknews.json"
STATE_FILE = "pink_state.json"

LOOKBACK_YEARS = 5
MAX_ITEMS = 300
MAX_ITEMS_PER_QUERY = 80

MAX_QUERIES_PER_RUN = int(os.getenv("MAX_QUERIES_PER_RUN", "40"))
TIME_BUDGET_SECONDS = int(os.getenv("TIME_BUDGET_SECONDS", "120"))

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

AREA_NAMES = [
    "Ashford", "Broadstairs", "Canterbury", "Chatham", "Dartford", "Deal", "Dover",
    "Faversham", "Folkestone", "Gillingham", "Gravesend", "Herne Bay", "Hythe",
    "Isle of Sheppey", "Maidstone", "Margate", "Medway", "Ramsgate", "Rochester",
    "Sevenoaks", "Sheerness", "Sheppey", "Sittingbourne", "Swale", "Thanet",
    "Tonbridge", "Tunbridge Wells", "Whitstable",
]

AREA_PATTERNS = []
for n in AREA_NAMES:
    AREA_PATTERNS.append((n, re.compile(r"\b" + re.escape(n.lower()) + r"\b", re.I)))
AREA_PATTERNS += [
    ("Herne Bay", re.compile(r"\bherne\s+bay\b", re.I)),
    ("Tunbridge Wells", re.compile(r"\btunbridge\s+wells\b", re.I)),
    ("Isle of Sheppey", re.compile(r"\bisle\s+of\s+sheppey\b", re.I)),
]

TOPIC_TERMS = [
    "lgbt", "lgbtq", "lgbtq+", "lgbtqia", "lgbtqia+",
    "queer",
    "gay", "lesbian", "bisexual",
    "trans", "transgender",
    "non-binary", "non binary", "nonbinary",
    "homophobic", "homophobia",
    "transphobic", "transphobia",
    "biphobic", "biphobia",
    "hate crime", "hate-crime", "hatecrime",
    "sexual orientation", "gender identity",
    "pride",
]

COURT_TERMS = [
    "court", "crown court", "magistrates", "sentenced", "sentence",
    "pleaded guilty", "pleaded", "charged", "convicted", "judge",
    "hearing", "trial", "appeal", "prosecuted",
]

HATE_TERMS = [
    "hate crime", "hate-crime", "hatecrime",
    "homophobic", "homophobia",
    "transphobic", "transphobia",
    "biphobic", "biphobia",
]

BAD_LOCATION_PATTERNS = [
    re.compile(r"\bkent state\b", re.I),
    re.compile(r"\bkent state university\b", re.I),
    re.compile(r"\bkent,\s*ohio\b", re.I),
    re.compile(r"\bohio\b", re.I),
    re.compile(r"\bkent,\s*wa\b", re.I),
    re.compile(r"\bkent\s+wa\b", re.I),
    re.compile(r"\bkent,\s*washington\b", re.I),
    re.compile(r"\bwashington state\b", re.I),
    re.compile(r"\bkentucky\b", re.I),
    re.compile(r"\busa\b", re.I),
    re.compile(r"\bunited states\b", re.I),
]

UK_SIGNAL_PATTERNS = [
    re.compile(r"\bkent\b", re.I),
    re.compile(r"\bengland\b", re.I),
    re.compile(r"\buk\b", re.I),
    re.compile(r"\bunited kingdom\b", re.I),
    re.compile(r"\bkent police\b", re.I),
    re.compile(r"\bkentonline\.co\.uk\b", re.I),
    re.compile(r"\bkentlive\.news\b", re.I),
]

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def load_json(path: str, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_rss_date(pub_date: str):
    if not pub_date:
        return None
    pub_date = pub_date.strip()
    fmts = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(pub_date, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None

def build_google_rss_url(q: str) -> str:
    params = {"q": q, "hl": "en-GB", "gl": "GB", "ceid": "GB:en"}
    return GOOGLE_NEWS_RSS + "?" + urlencode(params)

def fetch_rss(q: str):
    url = build_google_rss_url(q)
    r = SESSION.get(url, timeout=20)
    if r.status_code >= 400:
        raise RuntimeError("HTTP " + str(r.status_code))
    return r.text

def rss_items(xml_text: str):
    out = []
    root = ET.fromstring(xml_text)
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        desc = strip_html(item.findtext("description") or "")

        source_elem = item.find("source")
        source_name = ""
        source_url = ""
        if source_elem is not None:
            source_name = (source_elem.text or "").strip()
            source_url = (source_elem.attrib.get("url") or "").strip()

        dt = parse_rss_date(pub_date)
        published = dt.date().isoformat() if dt else None

        out.append({
            "title": title,
            "url": link,
            "published": published,
            "source": source_name if source_name else "Google News",
            "source_url": source_url,
            "summary": desc[:650] if desc else "",
        })
    return out

def find_area(text: str) -> str:
    t = (text or "").lower()
    if "sheppey" in t:
        if "isle of sheppey" in t:
            return "Isle of Sheppey"
        return "Sheppey"
    for name, pat in AREA_PATTERNS:
        if pat.search(t):
            return name
    return ""

def is_bad_location(text: str) -> bool:
    for pat in BAD_LOCATION_PATTERNS:
        if pat.search(text or ""):
            return True
    return False

def has_uk_signal(text: str) -> bool:
    for pat in UK_SIGNAL_PATTERNS:
        if pat.search(text or ""):
            return True
    return False

def looks_like_kent_uk(text: str) -> bool:
    if is_bad_location(text):
        return False
    if find_area(text):
        return True
    return has_uk_signal(text)

def has_topic_signal(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in TOPIC_TERMS)

def classify_label(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in HATE_TERMS):
        return "Hate crime update"
    if any(k in t for k in COURT_TERMS):
        return "Court update"
    if "pride" in t:
        return "Pride update"
    return "LGBT news"

def build_queries():
    neg = '-"Kent State" -Kentucky -Ohio -USA -"United States" -Washington -("Kent, WA") -("Kent WA")'
    queries = [
        f'kent england (lgbt OR lgbtq OR gay OR lesbian OR bisexual OR trans OR transgender OR "non-binary" OR queer OR pride) {neg}',
        f'kent england (homophobic OR transphobic OR "hate crime" OR hatecrime) {neg}',
        f'kent england (court OR "crown court" OR magistrates OR sentenced OR convicted OR charged) (homophobic OR transphobic OR "hate crime") {neg}',
        f'(Canterbury OR Maidstone OR Medway OR Thanet OR Swale OR Dartford OR Gravesend OR Dover OR Ashford OR Folkestone) (lgbt OR lgbtq OR gay OR lesbian OR trans OR transgender OR "non-binary" OR pride OR homophobic OR transphobic OR "hate crime") {neg}',
    ]

    for area in AREA_NAMES:
        queries.append(f'"{area}" kent (lgbt OR lgbtq OR gay OR lesbian OR trans OR transgender OR "non-binary" OR pride OR homophobic OR transphobic OR "hate crime") {neg}')

    out = []
    seen = set()
    for q in queries:
        if q not in seen:
            out.append(q)
            seen.add(q)
    return out

def main() -> None:
    start = time.time()
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_YEARS)

    state = load_json(STATE_FILE, {"seen_urls": []})
    seen_urls = set(state.get("seen_urls", []))

    queries = build_queries()
    collected = []
    scanned = 0
    kept = 0

    print("Queries total:", len(queries), flush=True)

    for idx, q in enumerate(queries, start=1):
        if idx > MAX_QUERIES_PER_RUN:
            print("Stop: query limit reached", flush=True)
            break
        if (time.time() - start) > TIME_BUDGET_SECONDS:
            print("Stop: time budget reached", flush=True)
            break

        try:
            xml_text = fetch_rss(q)
            items = rss_items(xml_text)[:MAX_ITEMS_PER_QUERY]
        except Exception as e:
            print("Query failed", idx, ":", str(e), flush=True)
            continue

        scanned += len(items)

        for it in items:
            url = it.get("url") or ""
            if not url or url in seen_urls:
                continue

            combined = f'{it.get("title","")} {it.get("summary","")} {it.get("source","")} {it.get("source_url","")} {it.get("url","")}'
            if not looks_like_kent_uk(combined):
                continue
            if not has_topic_signal(combined):
                continue

            if it.get("published"):
                try:
                    dt = datetime.strptime(it["published"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                except Exception:
                    pass

            it["area"] = find_area(combined)
            it["label"] = classify_label(combined)
            it["found_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

            collected.append(it)
            seen_urls.add(url)
            kept += 1

        print("Progress", idx, "/", len(queries), "scanned", scanned, "kept", kept, flush=True)

    dedup = {}
    for it in collected:
        dedup[it["url"]] = it

    out = list(dedup.values())
    out.sort(key=lambda x: x.get("published") or "0000-00-00", reverse=True)
    out = out[:MAX_ITEMS]

    state["seen_urls"] = list(seen_urls)[:90000]
    save_json(STATE_FILE, state)
    save_json(OUT_FILE, out)

    print("Saved items:", len(out), flush=True)

if __name__ == "__main__":
    main()
