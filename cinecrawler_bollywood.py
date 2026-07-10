# cinecrawler_bollywood.py
# Full scraper using FlareSolverr to bypass Cloudflare

import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin, urlparse
from functools import lru_cache

# ---------- FlareSolverr Configuration ----------
# Replace this with your actual FlareSolverr URL after deployment
FLARESOLVERR_URL = "https://flaresolverr.onrender.com/v1"  # <-- UPDATE THIS

# ---------- Domain resolver ----------
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

def extract_redirect_from_js(html):
    patterns = [
        r'window\.location\s*=\s*["\']([^"\']+)["\']',
        r'location\.href\s*=\s*["\']([^"\']+)["\']',
        r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
        r'window\.location\.replace\s*\(\s*["\']([^"\']+)["\']\s*\)'
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return m.group(1)
    return None

def fetch_via_flaresolverr(url):
    """Send request through FlareSolverr and return HTML."""
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 60000
    }
    resp = requests.post(FLARESOLVERR_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "ok":
        return data.get("solution", {}).get("response", "")
    else:
        raise Exception(f"FlareSolverr error: {data}")

def find_working_domain():
    for domain in ROGMOVIES_DOMAINS:
        try:
            url = f"https://{domain}/"
            html = fetch_via_flaresolverr(url)
            if is_valid_html(html):
                if 'Redirecting' in html or 'redirect' in html.lower():
                    real_url = extract_redirect_from_js(html)
                    if real_url:
                        parsed = urlparse(real_url)
                        if parsed.netloc:
                            return parsed.netloc
                else:
                    return domain
        except:
            continue
    return None

WORKING_DOMAIN = None

def get_working_domain():
    global WORKING_DOMAIN
    if WORKING_DOMAIN:
        return WORKING_DOMAIN
    try:
        html = fetch_via_flaresolverr("https://vglist.nl/")
        match = re.search(r'https?://rogmovies\.[a-z]+', html)
        if match:
            domain = match.group(0).replace('https://', '').replace('http://', '')
            test_html = fetch_via_flaresolverr(f"https://{domain}/")
            if is_valid_html(test_html):
                if 'Redirecting' in test_html:
                    real_url = extract_redirect_from_js(test_html)
                    if real_url:
                        parsed = urlparse(real_url)
                        if parsed.netloc:
                            WORKING_DOMAIN = parsed.netloc
                            return WORKING_DOMAIN
                else:
                    WORKING_DOMAIN = domain
                    return domain
    except:
        pass
    domain = find_working_domain()
    if domain:
        WORKING_DOMAIN = domain
        return domain
    WORKING_DOMAIN = "rogmovies.rest"
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
        domain = get_working_domain()
        search_url = f"https://{domain}/search.html?q={quote(query)}"
        html = fetch_via_flaresolverr(search_url)

        if not is_valid_html(html):
            result = {'error': 'Invalid HTML from FlareSolverr', 'domain': domain}
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
        domain = get_working_domain()
        if not detail_url.startswith('http'):
            detail_url = f"https://{domain}{detail_url if detail_url.startswith('/') else '/' + detail_url}"
        html = fetch_via_flaresolverr(detail_url)

        if not is_valid_html(html):
            return {'error': 'Invalid HTML from FlareSolverr'}

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
        return {'error': str(e), 'trace': 'get_download_options'}

# ---------- 3. Resolve shortlink ----------
@lru_cache(maxsize=50)
def resolve_shortlink_cached(short_url):
    return resolve_shortlink(short_url)

def resolve_shortlink(short_url):
    try:
        html = fetch_via_flaresolverr(short_url)
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

        html2 = fetch_via_flaresolverr(vcloud_url)
        soup2 = BeautifulSoup(html2, 'lxml')

        generate_btn = soup2.select_one('a#download, .btn-download, .generate-btn')
        if generate_btn:
            generate_url = generate_btn.get('href')
            if generate_url:
                if not generate_url.startswith('http'):
                    generate_url = urljoin(vcloud_url, generate_url)
                html3 = fetch_via_flaresolverr(generate_url)
                final_html = html3
            else:
                final_html = html2
        else:
            for a in soup2.find_all('a'):
                if 'Generate' in a.get_text(strip=True):
                    gen_url = a.get('href')
                    if gen_url:
                        if not gen_url.startswith('http'):
                            gen_url = urljoin(vcloud_url, gen_url)
                        html3 = fetch_via_flaresolverr(gen_url)
                        final_html = html3
                        break
            else:
                final_html = html2

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
