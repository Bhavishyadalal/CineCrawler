# cinecrawler_bollywood.py
# HTTP scraper for Bollywood – gets domain from vglist.nl

import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from functools import lru_cache
import time

# ---------- Get domain from vglist.nl ----------
def get_bollywood_domain():
    """Fetch the current RogMovies domain from vglist.nl."""
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        resp = session.get("https://vglist.nl/", timeout=10)
        if resp.status_code == 200:
            # Find the RogMovies link
            match = re.search(r'https?://rogmovies\.[a-z]+', resp.text)
            if match:
                domain = match.group(0).replace('https://', '').replace('http://', '')
                print(f"✅ Found domain from vglist.nl: {domain}")
                return domain
    except Exception as e:
        print(f"⚠️ Failed to fetch from vglist.nl: {e}")
    
    # Fallback domains if vglist.nl fails
    fallback_domains = [
        "rogmovies.rest",
        "rogmovies.one",
        "rogmovies.work",
        "rogmovies.life"
    ]
    for domain in fallback_domains:
        try:
            test_resp = requests.get(f"https://{domain}/", timeout=5)
            if test_resp.status_code == 200:
                print(f"✅ Using fallback domain: {domain}")
                return domain
        except:
            continue
    
    print("⚠️ Using default domain: rogmovies.rest")
    return "rogmovies.rest"

# ---------- Initialize domain ----------
DOMAIN = get_bollywood_domain()
print(f"🌐 Using domain: {DOMAIN}")

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

# ---------- 1. Search ----------
def search_movies(query):
    cache_key = f"bollywood_search_{query}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        search_url = f"https://{DOMAIN}/search.html?q={quote(query)}"
        resp = session.get(search_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
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
                results.append({
                    'title': title,
                    'detailUrl': full_url
                })

        # If no results, try any link containing query words
        if not results:
            for a in soup.find_all('a', href=True):
                text = a.get_text(strip=True)
                if text and any(word.lower() in text.lower() for word in query.split()):
                    href = a['href']
                    if '/download-' in href:
                        results.append({
                            'title': re.sub(r'\s+', ' ', text),
                            'detailUrl': href if href.startswith('http') else urljoin(f"https://{DOMAIN}", href)
                        })

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
        return {'error': str(e)}

# ---------- 2. Download options ----------
def get_download_options(detail_url, mode=None):
    cache_key = f"bollywood_options_{detail_url}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        if not detail_url.startswith('http'):
            detail_url = f"https://{DOMAIN}{detail_url if detail_url.startswith('/') else '/' + detail_url}"
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
