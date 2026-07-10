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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
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

# ---------- 1. Search (Robust) ----------
def search_movies(query):
    cache_key = f"bollywood_search_{query}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        domain = get_bollywood_domain()
        search_url = f"https://{domain}/search.html?q={quote(query)}"
        resp = session.get(search_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        results = []

        # Method 1: Look for <a> with href containing "/download-"
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            # Skip empty or irrelevant links
            if not text or len(text) < 2:
                continue
            if 'search.html' in href or '#' in href:
                continue
            # Check if href contains "/download-" OR text contains query words
            if '/download-' in href or any(word in text.lower() for word in query.lower().split()):
                # Clean title
                title = re.sub(r'\s+', ' ', text)
                # Build full URL
                if href.startswith('http'):
                    full_url = href
                else:
                    full_url = urljoin(f"https://{domain}", href)
                results.append({
                    'title': title,
                    'detailUrl': full_url
                })

        # Method 2: If no results, look for containers like .movie-card, .result-item
        if not results:
            for card in soup.select('.movie-card, .result-item, .post-item, .grid-item'):
                # Get the first link inside that might be the movie link
                link = card.find('a', href=True)
                if link:
                    href = link['href']
                    if '/download-' not in href:
                        continue
                    text = card.get_text(strip=True)
                    title = re.sub(r'\s+', ' ', text)
                    full_url = href if href.startswith('http') else urljoin(f"https://{domain}", href)
                    results.append({
                        'title': title,
                        'detailUrl': full_url
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
        for a in soup.select('a[href*="nexdrive"]'):
            p = a.parent
            if not p or p.name != 'p':
                p = a.find_parent('p')
            if not p:
                continue
            quality_el = p.find_previous_sibling('h5')
            if not quality_el:
                quality_el = p.parent.find('h5') if p.parent else None
            quality = ''
            if quality_el:
                text = quality_el.get_text(strip=True)
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

# ---------- 3. Resolve shortlink ----------
@lru_cache(maxsize=50)
def resolve_shortlink_cached(short_url):
    return resolve_shortlink(short_url)

def resolve_shortlink(short_url):
    try:
        resp = session.get(short_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        vcloud_a = soup.select_one('a[href*="vcloud.zip"]')
        if not vcloud_a:
            for a in soup.find_all('a'):
                if 'V-Cloud' in a.get_text(strip=True):
                    vcloud_a = a
                    break
        if not vcloud_a:
            return {'error': 'V-Cloud link not found'}
        vcloud_url = vcloud_a['href']
        if not vcloud_url.startswith('http'):
            vcloud_url = urljoin(short_url, vcloud_url)
        resp2 = session.get(vcloud_url, timeout=10)
        resp2.raise_for_status()
        soup2 = BeautifulSoup(resp2.text, 'lxml')
        generate_btn = soup2.select_one('a#download, .btn-download, .generate-btn')
        if generate_btn:
            generate_url = generate_btn.get('href')
            if generate_url:
                if not generate_url.startswith('http'):
                    generate_url = urljoin(vcloud_url, generate_url)
                resp3 = session.get(generate_url, timeout=10)
                resp3.raise_for_status()
                final_html = resp3.text
            else:
                final_html = resp2.text
        else:
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
            if server != 'PixelServer':
                links.append({'server': server, 'label': text, 'url': href})
    seen = set()
    unique = []
    for link in links:
        if link['url'] not in seen:
            seen.add(link['url'])
            unique.append(link)
    return unique

def resolve_wrapper(short_url):
    return resolve_shortlink_cached(short_url)
