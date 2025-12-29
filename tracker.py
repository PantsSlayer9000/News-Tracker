import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

OUT_FILE = "pinknews.json"
STATE_FILE = "pink_state.json"

BBC_TOPIC_URL = "https://www.bbc.co.uk/news/topics/cp7r8vgln2wt"

LOOKBACK_YEARS = 5
MAX_ITEMS_TOTAL = 300
MAX_ITEMS_PER_FEED = 120

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}

PINKNEWS_DOMAIN = "pinknews.co.uk"
BBC_DOMAIN = "www.bbc.co.uk"

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

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

def iso_date(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.date().isoformat()

def within_lookback(published_iso: str | None, cutoff: datetime) -> bool:
    if not published_iso:
        return True
    try:
        dt = datetime.strptime(published_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except Exception:
        return True

def has_topic_signal(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in TOPIC_TERMS)

def build_google_news_rss_url(q: str) -> str:
    params = {"q": q, "hl": "en-GB", "gl": "GB", "ceid": "GB:en"}
    return GOOGLE_NEWS_RSS + "?" + urlencode(params)

def fetch_text(url: str, timeout: int = 25) -> str:
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text

def parse_google_news_rss(xml_text: str):
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
        out.append({
            "title": title,
            "url": link,
            "published": iso_date(dt),
            "source": source_name if source_name else "PinkNews",
            "source_url": source_url if source_url else "https://www.pinknews.co.uk",
            "summary": desc[:650] if desc else "",
        })

    return out

def fetch_pinknews_only(cutoff: datetime):
    queries = [
        f"site:{PINKNEWS_DOMAIN} (lgbt OR lgbtq OR gay OR lesbian OR bisexual OR trans OR transgender OR queer OR pride OR homophobic OR transphobic OR \"hate crime\")",
        f"site:{PINKNEWS_DOMAIN} (kent OR canterbury OR maidstone OR medway OR thanet OR swale OR sheerness OR sittingbourne OR rochester OR chatham OR dartford OR gravesend OR ashford OR folkestone OR dover) (lgbt OR lgbtq OR gay OR lesbian OR trans OR transgender OR queer OR pride OR homophobic OR transphobic OR \"hate crime\")",
        f"site:{PINKNEWS_DOMAIN} (court OR \"crown court\" OR magistrates OR sentenced OR convicted OR charged) (homophobic OR transphobic OR \"hate crime\")",
    ]

    items = []
    for q in queries:
        url = build_google_news_rss_url(q)
        try:
            xml_text = fetch_text(url, timeout=25)
            batch = parse_google_news_rss(xml_text)
        except Exception as e:
            print("PinkNews query failed:", str(e), flush=True)
            continue

        for it in batch[:MAX_ITEMS_PER_FEED]:
            if PINKNEWS_DOMAIN not in (it.get("url") or ""):
                continue
            combined = f'{it.get("title","")} {it.get("summary","")}'
            if not has_topic_signal(combined):
                continue
            if not within_lookback(it.get("published"), cutoff):
                continue

            it["source"] = "PinkNews"
            it["source_url"] = "https://www.pinknews.co.uk"
            it["label"] = "PinkNews"
            items.append(it)

    return items

def parse_bbc_topic_jsonld(html: str):
    scripts = re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, flags=re.I | re.S)
    candidates = []

    for s in scripts:
        s = s.strip()
        if not s:
            continue
        try:
            data = json.loads(s)
        except Exception:
            continue

        stack = [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                if "itemListElement" in obj and isinstance(obj["itemListElement"], list):
                    for el in obj["itemListElement"]:
                        if isinstance(el, dict):
                            item = el.get("item")
                            if isinstance(item, dict):
                                url = item.get("url") or ""
                                name = item.get("name") or ""
                                date_published = item.get("datePublished") or item.get("dateCreated") or item.get("dateModified") or ""
                                candidates.append((url, name, date_published))
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(obj, list):
                for v in obj:
                    if isinstance(v, (dict, list)):
                        stack.append(v)

    return candidates

def normalise_bbc_date(s: str) -> str | None:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except Exception:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
        if m:
            return m.group(1)
    return None

def fetch_bbc_topic_only(cutoff: datetime):
    try:
        html = fetch_text(BBC_TOPIC_URL, timeout=30)
    except Exception as e:
        print("BBC topic fetch failed:", str(e), flush=True)
        return []

    items = []
    seen = set()

    for url, name, date_published in parse_bbc_topic_jsonld(html):
        if not url or url in seen:
            continue
        seen.add(url)

        if not url.startswith("http"):
            continue
        if (BBC_DOMAIN + "/news/") not in url:
            continue

        published = normalise_bbc_date(date_published)
        if not within_lookback(published, cutoff):
            continue

        title = strip_html(name) if name else "BBC News"
        combined = title.lower()
        if not has_topic_signal(combined):
            pass

        items.append({
            "title": title,
            "url": url,
            "published": published,
            "source": "BBC News",
            "source_url": "https://www.bbc.co.uk/news",
            "summary": "",
            "label": "BBC topic",
        })

        if len(items) >= MAX_ITEMS_PER_FEED:
            break

    if items:
        return items

    hrefs = set(re.findall(r'href="(/news/[^"]+)"', html, flags=re.I))
    for h in list(hrefs)[:200]:
        if h.startswith("/news/topics/"):
            continue
        url = "https://www.bbc.co.uk" + h
        if url in seen:
            continue
        seen.add(url)
        items.append({
            "title": "BBC News",
            "url": url,
            "published": None,
            "source": "BBC News",
            "source_url": "https://www.bbc.co.uk/news",
            "summary": "",
            "label": "BBC topic",
        })
        if len(items) >= 80:
            break

    return items

def dedup_sort(items):
    by_url = {}
    for it in items:
        u = (it.get("url") or "").strip()
        if not u:
            continue
        by_url[u] = it

    out = list(by_url.values())
    out.sort(key=lambda x: x.get("published") or "0000-00-00", reverse=True)
    return out[:MAX_ITEMS_TOTAL]

def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_YEARS)

    state = load_json(STATE_FILE, {"seen_urls": []})
    seen_urls = set(state.get("seen_urls", []))

    start = time.time()

    items = []
    items += fetch_pinknews_only(cutoff)
    items += fetch_bbc_topic_only(cutoff)

    cleaned = []
    for it in items:
        url = it.get("url") or ""
        if not url:
            continue

        if PINKNEWS_DOMAIN in url:
            pass
        elif url.startswith("https://www.bbc.co.uk/news/"):
            pass
        else:
            continue

        if url in seen_urls:
            continue

        it["found_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        cleaned.append(it)
        seen_urls.add(url)

    out = dedup_sort(cleaned)

    state["seen_urls"] = list(seen_urls)[:100000]
    save_json(STATE_FILE, state)
    save_json(OUT_FILE, out)

    print("Saved items:", len(out), flush=True)
    print("Run seconds:", int(time.time() - start), flush=True)

if __name__ == "__main__":
    main()
