# cinecrawler_bollywood.py
# Bollywood scraper – handles redirects and Cloudflare

import requests
import re
import time
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin, urlparse

# ---------- List of all known RogMovies domains ----------
ROGMOVIES_DOMAINS = [
    "rogmovies.rest",
    "rogmovies.one",
    "rogmovies.work",
    "rogmovies.life",
    "rogmovies.gay",
    "rogmovies.how",
    "rogmovies.click",
    "rogmovies.nu",
    "rogmovies.top",
    "rogmovies.fun",
    "rogmovies.online",
    "rogmovies.pro",
    "rogmovies.vip",
    "rogmovies.biz",
    "rogmovies.xyz",
    "rogmovies.lol",
]

# ---------- Helper: check if content is valid HTML ----------
def is_valid_html(content):
    content_lower = content.lower()
    if '<html' in content_lower or '<body' in content_lower or '<title' in content_lower:
        return True
    if content_lower.strip().startswith('<!doctype'):
        return True
    if 'cf-chl' in content_lower or 'cf-browser' in content_lower:
        return False
    return False

# ---------- Helper: extract redirect URL from JavaScript ----------
def extract_redirect_from_js(html):
    """Extract redirect URL from JavaScript redirect code."""
    # Look for window.location or location.href
    patterns = [
        r'window\.location\s*=\s*["\']([^"\']+)["\']',
        r'location\.href\s*=\s*["\']([^"\']+)["\']',
        r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
        r'window\.location\.replace\s*\(\s*["\']([^"\']+)["\']\s*\)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None

# ---------- Find working domain ----------
def find_working_domain():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    for domain in ROGMOVIES_DOMAINS:
        try:
            url = f"https://{domain}/"
            resp = session.get(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200 and is_valid_html(resp.text):
                # Check if it's a redirect page
                if 'Redirecting' in resp.text or 'redirect' in resp.text.lower():
                    # Try to extract the real URL
                    real_url = extract_redirect_from_js(resp.text)
                    if real_url:
                        print(f"✅ {domain} redirects to: {real_url}")
                        # Extract domain from the real URL
                        parsed = urlparse(real_url)
                        if parsed.netloc:
                            return parsed.netloc
                else:
                    print(f"✅ Working domain: {domain}")
                    return domain
        except Exception as e:
            print(f"❌ {domain} – error: {e}")
    return None

# ---------- Get domain (with cache) ----------
WORKING_DOMAIN = None

def get_working_domain():
    global WORKING_DOMAIN
    if WORKING_DOMAIN:
        return WORKING_DOMAIN
    # Try vglist.nl first
    try:
        resp = requests.get("https://vglist.nl/", timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            match = re.search(r'https?://rogmovies\.[a-z]+', resp.text)
            if match:
                domain = match.group(0).replace('https://', '').replace('http://', '')
                test_resp = requests.get(f"https://{domain}/", timeout=10, allow_redirects=True)
                if test_resp.status_code == 200 and is_valid_html(test_resp.text):
                    if 'Redirecting' in test_resp.text:
                        real_url = extract_redirect_from_js(test_resp.text)
                        if real_url:
                            parsed = urlparse(real_url)
                            if parsed.netloc:
                                WORKING_DOMAIN = parsed.netloc
                                print(f"✅ vglist.nl -> {WORKING_DOMAIN}")
                                return WORKING_DOMAIN
                    else:
                        WORKING_DOMAIN = domain
                        print(f"✅ vglist.nl -> {domain}")
                        return domain
    except Exception as e:
        print(f"⚠️ vglist.nl error: {e}")
    # If vglist fails, test all domains
    domain = find_working_domain()
    if domain:
        WORKING_DOMAIN = domain
        return domain
    # Ultimate fallback
    print("⚠️ No working domain found – using rogmovies.rest")
    WORKING_DOMAIN = "rogmovies.rest"
    return WORKING_DOMAIN

# ---------- Session ----------
def get_session():
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
        session = get_session()
        search_url = f"https://{domain}/search.html?q={quote(query)}"
        resp = session.get(search_url, timeout=15, allow_redirects=True)
        status = resp.status_code
        html = resp.text

        # Check if we got a redirect page
        if 'Redirecting' in html or '<title>Redirecting...</title>' in html:
            real_url = extract_redirect_from_js(html)
            if real_url:
                # Follow the redirect manually
                parsed = urlparse(real_url)
                if parsed.netloc:
                    domain = parsed.netloc
                    WORKING_DOMAIN = domain
                    search_url = f"https://{domain}/search.html?q={quote(query)}"
                    resp = session.get(search_url, timeout=15, allow_redirects=True)
                    html = resp.text

        # Check if HTML is valid
        if not is_valid_html(html):
            result = {
                'error': 'Invalid HTML (Cloudflare or garbage)',
                'domain_used': domain,
                'search_url': search_url,
                'status_code': status,
                'html_preview': html[:500],
                'tip': 'All domains are behind Cloudflare. Use Playwright or upgrade Render plan.'
            }
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
                results.append({
                    'title': title,
                    'detailUrl': full_url
                })

        # If no results, return debug
        if not results:
            result = {
                'error': 'No movie links found',
                'domain_used': domain,
                'search_url': search_url,
                'status_code': status,
                'html_preview': html[:500],
                'tip': 'The page loads but no /download- links were found.'
            }
            set_cache(cache_key, result)
            return result

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
        return {'error': str(e), 'domain': domain if 'domain' in locals() else 'unknown'}

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
        session = get_session()
        resp = session.get(detail_url, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        if not is_valid_html(html):
            return {'error': 'Invalid HTML response from domain'}
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
        session = get_session()
        resp = session.get(short_url, timeout=10, allow_redirects=True)
        resp.raise_for_status()
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
        resp2 = session.get(vcloud_url, timeout=10, allow_redirects=True)
        resp2.raise_for_status()
        soup2 = BeautifulSoup(resp2.text, 'lxml')
        generate_btn = soup2.select_one('a#download, .btn-download, .generate-btn')
        if generate_btn:
            generate_url = generate_btn.get('href')
            if generate_url:
                if not generate_url.startswith('http'):
                    generate_url = urljoin(vcloud_url, generate_url)
                resp3 = session.get(generate_url, timeout=10, allow_redirects=True)
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
                        resp3 = session.get(gen_url, timeout=10, allow_redirects=True)
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
