# cinecrawler_bollywood.py
# HTTP scraper for Bollywood (RogMovies) – no Playwright

import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from functools import lru_cache
import time

# ---------- Domain resolver ----------
DEFAULT_BOLLYWOOD_DOMAIN = "rogmovies.rest"

def get_bollywood_domain():
    """Fetch current RogMovies domain from vglist.top or fallback."""
    try:
        resp = requests.get("https://vglist.top/", timeout=10)
        if resp.status_code == 200:
            match = re.search(r'https?://rogmovies\.[a-z]+', resp.text)
            if match:
                domain = match.group(0).replace('https://', '').replace('http://', '')
                return domain
    except Exception:
        pass
    return DEFAULT_BOLLYWOOD_DOMAIN

BOLLYWOOD_DOMAIN = get_bollywood_domain()

# ---------- Session ----------
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# ---------- Cache ----------
cache = {}
CACHE_TTL = 3600

def get_cache(key):
    if key in cache and time.time() - cache[key]['time'] < CACHE_TTL:
        return cache[key]['data']
    return None

def set_cache(key, data):
    cache[key] = {'data': data, 'time': time.time()}

# ---------- 1. Search ----------
def search_movies(query):
    cache_key = f"bollywood_search_{query}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        domain = get_bollywood_domain()
        resp = session.get(f"https://{domain}/search.html?q={quote(query)}", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        results = []
        # Find all links containing /download-
        for a in soup.select('a[href*="/download-"]'):
            title = a.get_text(strip=True)
            if not title or len(title) < 3:
                parent = a.find_parent()
                if parent:
                    title = parent.get_text(strip=True)
            if title and a.get('href'):
                results.append({
                    'title': re.sub(r'\s+', ' ', title),
                    'detailUrl': a['href']
                })
        # Deduplicate by URL
        seen = set()
        unique = []
        for r in results:
            if r['detailUrl'] not in seen:
                seen.add(r['detailUrl'])
                unique.append(r)
        set_cache(cache_key, unique)
        return unique
    except Exception as e:
        return {'error': str(e)}

# ---------- 2. Download options ----------
def get_download_options(detail_url, mode=None):
    # mode is ignored for Bollywood (no series mode)
    cache_key = f"bollywood_options_{detail_url}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        if not detail_url.startswith('http'):
            domain = get_bollywood_domain()
            detail_url = f"https://{domain}{detail_url if detail_url.startswith('/') else '/' + detail_url}"
        resp = session.get(detail_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        options = []
        # Find all nexdrive links
        for a in soup.select('a[href*="nexdrive"]'):
            # Get parent <p>
            p = a.parent
            if not p or p.name != 'p':
                p = a.find_parent('p')
            if not p:
                continue
            # Get previous sibling <h5>
            quality_el = p.find_previous_sibling('h5')
            if not quality_el:
                quality_el = p.parent.find('h5') if p.parent else None
            quality = ''
            if quality_el:
                text = quality_el.get_text(strip=True)
                # Extract resolution and size
                match = re.search(r'(\d{3,4}p\s*(?:4K)?)\s*(x264|x265|H\.?264|H\.?265)?\s*\[?([\d.]+\s*(?:GB|MB))?\]?', text, re.I)
                if match:
                    parts = []
                    if match.group(1):
                        parts.append(match.group(1))
                    if match.group(2):
                        parts.append(match.group(2))
                    if match.group(3):
                        parts.append(match.group(3))
                    quality = ' '.join(parts)
                else:
                    # fallback: take first 40 chars
                    quality = text[:40]
            if not quality:
                quality = 'Unknown'
            options.append({
                'quality': quality,
                'url': a['href']
            })
        # Deduplicate by quality
        seen_quality = set()
        unique = []
        for opt in options:
            q = opt['quality']
            if q not in seen_quality:
                seen_quality.add(q)
                unique.append(opt)
        set_cache(cache_key, unique)
        return unique
    except Exception as e:
        return {'error': str(e)}

# ---------- 3. Resolve shortlink (nexdrive -> vcloud -> final) ----------
@lru_cache(maxsize=50)
def resolve_shortlink_cached(short_url):
    return resolve_shortlink(short_url)

def resolve_shortlink(short_url):
    try:
        # Step 1: Get nexdrive page and find vcloud link
        resp = session.get(short_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        # Look for a[href*="vcloud.zip"] or text "V-Cloud"
        vcloud_a = soup.select_one('a[href*="vcloud.zip"]')
        if not vcloud_a:
            # fallback: find by text
            for a in soup.find_all('a'):
                if 'V-Cloud' in a.get_text(strip=True):
                    vcloud_a = a
                    break
        if not vcloud_a:
            return {'error': 'V-Cloud link not found'}
        vcloud_url = vcloud_a['href']
        if not vcloud_url.startswith('http'):
            # relative URL
            vcloud_url = urljoin(short_url, vcloud_url)
        # Step 2: Go to vcloud page
        resp2 = session.get(vcloud_url, timeout=10)
        resp2.raise_for_status()
        soup2 = BeautifulSoup(resp2.text, 'lxml')
        # Step 3: Find generate button and simulate click (maybe a POST or redirect)
        generate_btn = soup2.select_one('a#download, .btn-download, .generate-btn')
        if generate_btn:
            generate_url = generate_btn.get('href')
            if generate_url:
                if not generate_url.startswith('http'):
                    generate_url = urljoin(vcloud_url, generate_url)
                # Follow generate link
                resp3 = session.get(generate_url, timeout=10)
                resp3.raise_for_status()
                final_html = resp3.text
            else:
                final_html = resp2.text
        else:
            # Try to find any link with "Generate" text
            for a in soup2.find_all('a'):
                if 'Generate' in a.get_text(strip=True):
                    gen_url = a.get('href')
                    if gen_url:
                        if not gen_url.startswith('http'):
                            gen_url = urljoin(vcloud_url, gen_url)
                        resp3 = session.get(gen_url, timeout=10)
                        resp3.raise_for_status()
                        final_html = resp3.text
                        break
            else:
                final_html = resp2.text
        # Step 4: Extract final download links
        return extract_final_links(final_html)
    except Exception as e:
        return {'error': str(e)}

def extract_final_links(html):
    soup = BeautifulSoup(html, 'lxml')
    links = []
    for a in soup.select('a[href]'):
        href = a.get('href')
        text = a.get_text(strip=True)
        if re.search(r'login|signin|telegram|t\.me|tinyurl|tutorial', href, re.I):
            continue
        if 'Download' in text or 'download' in text.lower():
            # Determine server
            server = 'Unknown'
            if 'FSLv2' in text:
                server = 'FSLv2'
            elif 'FSL' in text:
                server = 'FSL'
            elif 'Pixel' in text:
                server = 'PixelServer'
            elif 'Gofile' in text:
                server = 'Gofile'
            elif '10Gbps' in text:
                server = '10Gbps'
            elif 'Server : 1' in text:
                server = 'Server 1'
            elif 'Server' in text:
                server = 'Direct'
            # Exclude PixelServer if desired (we can add a flag)
            if server != 'PixelServer':
                links.append({'server': server, 'label': text, 'url': href})
    # Deduplicate by URL
    seen = set()
    unique = []
    for link in links:
        if link['url'] not in seen:
            seen.add(link['url'])
            unique.append(link)
    return unique

def resolve_wrapper(short_url):
    return resolve_shortlink_cached(short_url)
