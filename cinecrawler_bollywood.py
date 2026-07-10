# cinecrawler_bollywood.py
# Uses curl_cffi to impersonate Chrome and bypass Cloudflare

import re
import time
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin, urlparse
from functools import lru_cache

try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False
    print("⚠️ curl_cffi not installed, falling back to standard requests (will fail)")

# ---------- Domain list ----------
ROGMOVIES_DOMAINS = [
    "rogmovies.rest", "rogmovies.one", "rogmovies.work",
    "rogmovies.life", "rogmovies.gay", "rogmovies.how",
    "rogmovies.click", "rogmovies.nu", "rogmovies.top",
    "rogmovies.fun", "rogmovies.online", "rogmovies.pro",
    "rogmovies.vip", "rogmovies.biz", "rogmovies.xyz",
    "rogmovies.lol"
]

def is_valid_html(content):
    content_lower = content.lower()
    if '<html' in content_lower or '<body' in content_lower or '<title' in content_lower:
        return True
    if content_lower.strip().startswith('<!doctype'):
        return True
    if 'cf-chl' in content_lower or 'cf-browser' in content_lower:
        return False
    return False

def get_session():
    if USE_CURL_CFFI:
        # Impersonate Chrome 120 – this mimics the TLS fingerprint[reference:5]
        session = requests.Session(impersonate="chrome120")
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        return session
    else:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        return session

def get_working_domain():
    session = get_session()
    # First try vglist.nl
    try:
        resp = session.get("https://vglist.nl/", timeout=10)
        if resp.status_code == 200:
            match = re.search(r'https?://rogmovies\.[a-z]+', resp.text)
            if match:
                domain = match.group(0).replace('https://', '').replace('http://', '')
                test = session.get(f"https://{domain}/", timeout=10)
                if test.status_code == 200 and is_valid_html(test.text):
                    return domain
    except:
        pass
    # Try all domains
    for domain in ROGMOVIES_DOMAINS:
        try:
            test = session.get(f"https://{domain}/", timeout=10)
            if test.status_code == 200 and is_valid_html(test.text):
                return domain
        except:
            continue
    return "rogmovies.rest"

WORKING_DOMAIN = None

def get_working_domain_cached():
    global WORKING_DOMAIN
    if WORKING_DOMAIN:
        return WORKING_DOMAIN
    WORKING_DOMAIN = get_working_domain()
    return WORKING_DOMAIN

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
        domain = get_working_domain_cached()
        session = get_session()
        search_url = f"https://{domain}/search.html?q={quote(query)}"
        resp = session.get(search_url, timeout=15)
        html = resp.text

        if not is_valid_html(html):
            result = {'error': 'Invalid HTML (Cloudflare)', 'domain': domain}
            set_cache(cache_key, result)
            return result

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
                full_url = href if href.startswith('http') else urljoin(f"https://{domain}", href)
                results.append({'title': title, 'detailUrl': full_url})

        if not results:
            result = {
                'error': 'No movie links found',
                'domain': domain,
                'search_url': search_url,
                'html_preview': html[:800]
            }
            set_cache(cache_key, result)
            return result

        seen = set()
        unique = []
        for r in results:
            if r['detailUrl'] not in seen:
                seen.add(r['detailUrl'])
                unique.append(r)

        set_cache(cache_key, unique)
        return unique
    except Exception as e:
        return {'error': str(e), 'trace': 'search_movies'}

# ---------- 2. Download options ----------
def get_download_options(detail_url, mode=None):
    cache_key = f"bollywood_options_{detail_url}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        domain = get_working_domain_cached()
        if not detail_url.startswith('http'):
            detail_url = f"https://{domain}{detail_url if detail_url.startswith('/') else '/' + detail_url}"
        session = get_session()
        resp = session.get(detail_url, timeout=15)
        html = resp.text
        if not is_valid_html(html):
            return {'error': 'Invalid HTML'}
        soup = BeautifulSoup(html, 'lxml')
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
            options.append({'quality': quality, 'url': a['href']})
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
        return {'error': str(e), 'trace': 'get_download_options'}

# ---------- 3. Resolve shortlink ----------
@lru_cache(maxsize=50)
def resolve_shortlink_cached(short_url):
    return resolve_shortlink(short_url)

def resolve_shortlink(short_url):
    try:
        session = get_session()
        resp = session.get(short_url, timeout=10)
        html = resp.text
        soup = BeautifulSoup(html, 'lxml')
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
        soup2 = BeautifulSoup(resp2.text, 'lxml')
        generate_btn = soup2.select_one('a#download, .btn-download, .generate-btn')
        if generate_btn:
            generate_url = generate_btn.get('href')
            if generate_url:
                if not generate_url.startswith('http'):
                    generate_url = urljoin(vcloud_url, generate_url)
                resp3 = session.get(generate_url, timeout=10)
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
                        final_html = resp3.text
                        break
            else:
                final_html = resp2.text
        return extract_final_links(final_html)
    except Exception as e:
        return {'error': str(e), 'trace': 'resolve_shortlink'}

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
