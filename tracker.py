import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

OUT_FILE = "pinknews.json"
STATE_FILE = "pink_state.json"

LOOKBACK_YEARS = 5
MAX_ITEMS = 250
MAX_ITEMS_PER_QUERY = 60

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

AREA_NAMES = [
    "Ashford", "Broadstairs", "Canterbury", "Chatham", "Dartford", "Deal", "Dover",
    "Faversham", "Folkestone", "Gillingham", "Gravesend", "Herne Bay", "Hythe",
    "Isle of Sheppey", "Maidstone", "Margate", "Medway", "Ramsgate", "Rochester",
    "Sevenoaks", "Sheerness", "Sheppey", "Sittingbourne", "Swale", "Thanet",
    "Tonbridge", "Tunbridge Wells", "Whitstable",
]

AREA_PATTERNS = [
    (name, re.compile(r"\b" + re.escape(name.lower()) + r"\b", re.I))
    for name in AREA_NAMES
] + [
    ("Herne Bay", re.compile(r"\bherne\s+bay\b", re.I)),
    ("Tunbridge Wells", re.compile(r"\btunbridge\s+wells\b", re.I)),
    ("Isle of Sheppey", re.compile(r"\bisle\s+of\s+sheppey\b", re.I)),
]

BLOCK_TERMS = [
    "kent state",
    "kent state university",
    "kent, ohio",
    "ohio",
    "usa",
    "u.s.",
    "united states",
]

TOPIC_TERMS = [
    "lgbt", "lgbtq", "lgbtq+", "lgbtqia", "lgbtqia+",
    "gay", "lesbian", "bisexual", "trans", "transgender",
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
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code >= 400:
            print("RSS fetch failed", r.status_code, "for query:", q)
            return None
        return r.text
    except Exception as e:
        print("RSS fetch error", str(e), "for query:", q)
        return None

def rss_items(xml_text: str):
    out = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out

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
            "summary": desc[:500] if desc else "",
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

def looks_like_kent(text: str) -> bool:
    t = (text or "").lower()
    if any(b in t for b in BLOCK_TERMS):
        return False
    if "kent" in t:
        return True
    if find_area(t):
        return True
    return False

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
    neg = '-"Kent State" -Ohio -USA -"United States"'
    topic_blob = '(lgbt OR lgbtq OR gay OR lesbian OR bisexual OR trans OR transgender OR "non-binary" OR homophobic OR transphobic OR "hate crime" OR pride)'
    court_blob = '(court OR "crown court" OR magistrates OR sentenced OR "pleaded guilty" OR convicted OR charged)'
    hate_blob = '(homophobic OR transphobic OR "hate crime" OR hatecrime)'

    queries = []

    queries.append(f'kent uk {topic_blob} {neg}')
    queries.append(f'kent uk {hate_blob} {neg}')
    queries.append(f'kent uk {court_blob} {hate_blob} {neg}')
    queries.append(f'kent uk pride lgbt {neg}')

    for area in AREA_NAMES:
        a = f'"{area}"'
        queries.append(f'{a} kent uk {topic_blob} {neg}')
        queries.append(f'{a} kent uk {hate_blob} {neg}')
        queries.append(f'{a} kent uk {court_blob} {neg}')

    seen = set()
    out = []
    for q in queries:
        if q not in seen:
            out.append(q)
            seen.add(q)
    return out

def main() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_YEARS)

    state = load_json(STATE_FILE, {"seen_urls": []})
    seen_urls = set(state.get("seen_urls", []))

    queries = build_queries()
    collected = []
    scanned = 0

    for q in queries:
        xml_text = fetch_rss(q)
        if not xml_text:
            continue

        items = rss_items(xml_text)[:MAX_ITEMS_PER_QUERY]
        scanned += len(items)

        for it in items:
            url = it.get("url") or ""
            if not url:
                continue
            if url in seen_urls:
                continue

            combined = f'{it.get("title","")} {it.get("summary","")} {it.get("source","")} {it.get("source_url","")} {it.get("url","")}'
            if not looks_like_kent(combined):
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

    dedup = {}
    for it in collected:
        dedup[it["url"]] = it

    out = list(dedup.values())
    out.sort(key=lambda x: x.get("published") or "0000-00-00", reverse=True)
    out = out[:MAX_ITEMS]

    state["seen_urls"] = list(seen_urls)[:60000]
    save_json(STATE_FILE, state)
    save_json(OUT_FILE, out)

    print("Queries:", len(queries))
    print("Scanned items:", scanned)
    print("Saved items:", len(out))

if __name__ == "__main__":
    main()
