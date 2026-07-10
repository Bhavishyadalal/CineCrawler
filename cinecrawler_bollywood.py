# cinecrawler_bollywood.py
# Debug version – shows what Render is getting

import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from functools import lru_cache
import time

# ---------- Get domain from vglist.nl ----------
def get_bollywood_domain():
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        resp = session.get("https://vglist.nl/", timeout=10)
        if resp.status_code == 200:
            match = re.search(r'https?://rogmovies\.[a-z]+', resp.text)
            if match:
                return match.group(0).replace('https://', '').replace('http://', '')
    except Exception:
        pass
    return "rogmovies.rest"

DOMAIN = get_bollywood_domain()
print(f"🌐 Using domain: {DOMAIN}")

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
})

cache = {}
CACHE_TTL = 3600

def get_cache(key):
    if key in cache and time.time() - cache[key]['time'] < CACHE_TTL:
        return cache[key]['data']
    return None

def set_cache(key, data):
    cache[key] = {'data': data, 'time': time.time()}

# ---------- 1. Search with debug ----------
def search_movies(query):
    cache_key = f"bollywood_search_{query}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        search_url = f"https://{DOMAIN}/search.html?q={quote(query)}"
        resp = session.get(search_url, timeout=15)
        status = resp.status_code
        html = resp.text
        soup = BeautifulSoup(html, 'lxml')

        results = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/download-' not in href:
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 3:
                parent = a.find_parent()
                if parent:
                    title = parent.get_text(strip=True)
                if not title or len(title) < 3:
                    heading = a.find_previous(['h1', 'h2', 'h3', 'h4'])
                    if heading:
                        title = heading.get_text(strip=True)
            if title:
                title = re.sub(r'\s+', ' ', title)
                full_url = href if href.startswith('http') else urljoin(f"https://{DOMAIN}", href)
                results.append({'title': title, 'detailUrl': full_url})

        if not results:
            # Return debug info
            return {
                'error': 'No results found',
                'domain': DOMAIN,
                'search_url': search_url,
                'status_code': status,
                'html_preview': html[:500]  # first 500 chars
            }

        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            if r['detailUrl'] not in seen:
                seen.add(r['detailUrl'])
                unique.append(r)

        set_cache(cache_key, unique)
        return unique

    except Exception as e:
        return {'error': str(e), 'domain': DOMAIN, 'search_url': search_url}

# ---------- 2. Download options (unchanged) ----------
def get_download_options(detail_url, mode=None):
    # same as before – omitted for brevity, but keep your existing function
    # (copy from previous version)
    pass

# ---------- 3. Resolve shortlink ----------
def resolve_shortlink(short_url):
    # same as before
    pass

def resolve_wrapper(short_url):
    return resolve_shortlink(short_url)
