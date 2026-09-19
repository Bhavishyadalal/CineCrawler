# cinecrawler_optimized.py
# Hollywood backend for 4khdhub.one — uses Playwright for the resolve chain

import re
import time
import threading
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

DOMAIN = "4khdhub.one"

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': f'https://{DOMAIN}/'
})

# ---------- In-memory cache ----------
_cache = {}
CACHE_TTL = 3600  # 1 hour

def _get_cache(key):
    entry = _cache.get(key)
    if entry and time.time() - entry['t'] < CACHE_TTL:
        return entry['d']
    return None

def _set_cache(key, data):
    _cache[key] = {'d': data, 't': time.time()}


# ---------- Global Playwright browser (launched once at startup) ----------
_pw = None
_browser = None
_browser_lock = threading.Lock()
_playwright_lock = threading.Lock()  # serialize all Playwright calls

def _get_browser():
    global _pw, _browser
    with _browser_lock:
        if _browser is None or not _browser.is_connected():
            try:
                if _pw:
                    _pw.stop()
            except Exception:
                pass
            _pw = sync_playwright().start()
            _browser = _pw.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-background-networking',
                    '--disable-features=site-per-process',
                    '--single-process',
                ]
            )
        return _browser


# ---------- 1. Search ----------
def search_movies(query):
    key = f"search_{query}"
    cached = _get_cache(key)
    if cached is not None:
        return cached
    try:
        resp = session.get(f"https://{DOMAIN}/?s={quote(query)}", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        results = []
        for card in soup.select('a.movie-card'):
            title_el = card.select_one('.movie-card-title')
            meta_el = card.select_one('.movie-card-meta')
            img_el = card.select_one('img')
            if not (title_el and card.get('href')):
                continue
            title = title_el.text.strip()
            ym = re.search(r'(\d{4})', meta_el.text if meta_el else '')
            year = ym.group(1) if ym else ''
            poster = img_el.get('src', '') if img_el else ''
            href = card['href']
            if href.startswith('/'):
                href = f"https://{DOMAIN}{href}"
            results.append({
                'title': f"{title} ({year})" if year else title,
                'detailUrl': href,
                'poster': poster,
            })
        # Deduplicate
        seen, unique = set(), []
        for r in results:
            if r['detailUrl'] not in seen:
                seen.add(r['detailUrl'])
                unique.append(r)
        _set_cache(key, unique)
        return unique
    except Exception as e:
        return {'error': str(e)}


# ---------- 2. Download options ----------
def get_download_options(detail_url, mode=None):
    key = f"opt_{detail_url}_{mode}"
    cached = _get_cache(key)
    if cached is not None:
        return cached

    try:
        resp = session.get(detail_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        options = []

        is_series = '-series-' in detail_url or '/series-' in detail_url

        if is_series:
            if mode == 'episodes':
                # Individual episodes
                for ep_item in soup.select('.season-item.episode-item'):
                    header = ep_item.select_one('.episode-header')
                    if not header:
                        continue
                    ep_num_el = header.select_one('.episode-number')
                    ep_num = ep_num_el.get_text(strip=True) if ep_num_el else ''
                    ep_title_el = header.select_one('.episode-title')
                    ep_title = ' '.join(ep_title_el.get_text(strip=True).split()) if ep_title_el else ''
                    # Season info for context
                    season_el = ep_item.select_one('.season-number, .episode-season')
                    season = season_el.get_text(strip=True) if season_el else ''

                    content = ep_item.select_one('.episode-content')
                    if not content:
                        continue
                    for dl_item in content.select('.episode-download-item'):
                        file_title_el = dl_item.select_one('.episode-file-title')
                        file_title = ' '.join(file_title_el.get_text(strip=True).split()) if file_title_el else ''
                        size = ''
                        for b in dl_item.select('.badge, .badge-size'):
                            t = b.get_text(strip=True)
                            if 'GB' in t or 'MB' in t:
                                size = t
                                break
                        link_el = dl_item.select_one('a[href*="greenmotors.club"]')
                        if link_el and link_el.get('href'):
                            label = f"{season} {ep_num}".strip()
                            if ep_title:
                                label += f" | {ep_title}"
                            if size:
                                label += f" [{size}]"
                            options.append({'quality': label, 'url': link_el['href']})
            else:
                # Complete season packs (default mode)
                for item in soup.select('.download-item'):
                    header = item.select_one('.download-header')
                    if not header:
                        continue
                    season_el = item.select_one('.episode-number, .season-number')
                    season = season_el.get_text(strip=True) if season_el else ''
                    title_line = header.select_one('.download-title-text, .download-title-line')
                    quality = ' '.join(title_line.get_text(strip=True).split()) if title_line else ''
                    size = audio = ''
                    for badge in header.select('.badge'):
                        t = badge.get_text(strip=True)
                        if re.search(r'\d+(\.\d+)?\s*(GB|MB)', t, re.I):
                            size = t
                        elif any(l in t for l in ['Hindi', 'English', 'Tamil', 'Telugu', 'Dual', 'Multi']):
                            audio = t
                    file_id = header.get('data-file-id', '')
                    content = None
                    if file_id:
                        content = soup.select_one(f'#content-{file_id}')
                    if not content:
                        content = header.find_next_sibling()
                    link_el = None
                    if content:
                        link_el = content.select_one('a[href*="greenmotors.club"]')
                    if not link_el:
                        link_el = item.select_one('a[href*="greenmotors.club"]')
                    if link_el and link_el.get('href'):
                        label = f"{season} | {quality}" if season else quality
                        if size:
                            label += f" ({size}"
                            if audio:
                                label += f", {audio}"
                            label += ")"
                        options.append({'quality': label, 'url': link_el['href']})
        else:
            # Movie
            for header in soup.select('.download-header[data-file-id]'):
                file_id = header.get('data-file-id', '')
                title_el = header.select_one('.download-title-text')
                title = title_el.get_text(strip=True) if title_el else ''
                size = audio = ''
                for badge in header.select('.badge'):
                    t = badge.get_text(strip=True)
                    if re.search(r'\d+(\.\d+)?\s*(GB|MB)', t, re.I):
                        size = t
                    elif any(l in t for l in ['Hindi', 'English', 'Tamil', 'Telugu', 'Dual', 'Multi']):
                        audio = t
                content = soup.select_one(f'#content-{file_id}')
                if not content:
                    continue
                link_el = content.select_one(
                    'a[href*="greenmotors.club"], a[href*="hubcloud"], a[href*="hubdrive"]'
                )
                if link_el and link_el.get('href'):
                    label = title or 'Download'
                    if size:
                        label += f"  [{size}]"
                    if audio:
                        label += f"  ({audio})"
                    options.append({'quality': label, 'url': link_el['href']})

        _set_cache(key, options)
        return options
    except Exception as e:
        return {'error': str(e)}


# ---------- 3. Resolve chain using Playwright ----------
def _resolve_with_playwright(short_url):
    browser = _get_browser()
    context = browser.new_context(
        user_agent=session.headers['User-Agent'],
        viewport={'width': 1280, 'height': 720},
    )

    try:
        # Step 1: Load greenmotors entry
        page = context.new_page()
        try:
            page.goto(short_url, wait_until='commit', timeout=60000)
        except Exception:
            pass
        page.wait_for_timeout(5000)

        # Step 2: Wait for #verify_btn to appear
        for _ in range(10):
            if page.locator('#verify_btn').count() > 0:
                break
            page.wait_for_timeout(1000)

        if page.locator('#verify_btn').count() == 0:
            try:
                page.wait_for_selector('#verify_btn', timeout=20000)
            except PWTimeout:
                return []

        # Step 3: Click CLICK TO CONTINUE if needed
        btn_state = page.evaluate("""() => {
            const btn = document.getElementById('verify_btn');
            if (!btn) return null;
            return {
                text: btn.innerText.trim(),
                href: btn.getAttribute('href') || '',
                disabled: btn.classList.contains('disabled')
            };
        }""")

        if btn_state and ('CLICK TO CONTINUE' in btn_state['text'].upper()
                          or 'javascript' in btn_state['href']):
            try:
                page.locator('#verify_btn').click(timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(2000)
            # Close stray popups
            for p in context.pages:
                if p is not page:
                    try:
                        p.close()
                    except Exception:
                        pass

        # Step 4: Poll for timer to finish
        max_wait = 90
        start = time.time()
        activated = False
        while True:
            elapsed = time.time() - start
            if elapsed > max_wait:
                return []

            state = page.evaluate("""() => {
                const btn = document.getElementById('verify_btn');
                if (!btn) return { status: 'NO_BUTTON' };
                const href = btn.getAttribute('href') || '';
                const disabled = btn.classList.contains('disabled');
                const text = btn.innerText.trim();
                const isClickable = text.toUpperCase().includes('CLICK TO CONTINUE');
                return {
                    disabled: disabled,
                    href: href,
                    text: text.substring(0, 30),
                    valid: !disabled && href.startsWith('http') && !isClickable
                };
            }""")

            if state.get('valid'):
                activated = True
                break

            # Re-click if still stuck on CLICK TO CONTINUE
            if (state.get('text', '').upper().startswith('CLICK TO CONTINUE')
                    and int(elapsed) > 0 and int(elapsed) % 5 == 0):
                try:
                    page.locator('#verify_btn').click(timeout=3000)
                except Exception:
                    pass

            page.wait_for_timeout(1000)

        if not activated:
            return []

        hubcloud_url = page.get_attribute('a#verify_btn', 'href')
        if not hubcloud_url or 'javascript' in hubcloud_url:
            return []

        # Step 5: Load hubcloud drive
        hc_page = context.new_page()
        try:
            hc_page.goto(hubcloud_url, wait_until='commit', timeout=30000)
        except Exception:
            pass
        hc_page.wait_for_timeout(5000)

        # Step 6: Poll for gamerxyt link
        gamerxyt_url = None
        start = time.time()
        while time.time() - start < 30:
            gamerxyt_url = hc_page.evaluate("""() => {
                const btn = document.querySelector('a#download');
                return btn ? btn.getAttribute('href') : null;
            }""")
            if gamerxyt_url and 'gamerxyt' in gamerxyt_url:
                break
            hc_page.wait_for_timeout(1000)

        if not gamerxyt_url or 'gamerxyt' not in gamerxyt_url:
            return []

        # Step 7: Load gamerxyt final page
        gx_page = context.new_page()
        try:
            gx_page.goto(gamerxyt_url, wait_until='commit', timeout=30000)
        except Exception:
            pass
        gx_page.wait_for_timeout(5000)

        # Step 8: Extract final links
        final_links = gx_page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href || '';
                const text = (a.innerText || '').trim();
                if (href.includes('tinyurl') || href.includes('t.me')
                    || href.includes('telegram') || href.includes('login')
                    || href.includes('google.com') || href.startsWith('javascript')) return;
                const classes = a.className || '';
                if (classes.includes('btn-danger') || classes.includes('btn-success')) {
                    let server = 'Direct';
                    if (text.includes('10Gbps')) server = '10Gbps';
                    else if (text.includes('FSL')) server = 'FSL';
                    else if (text.includes('ZipDisk')) server = 'ZipDisk';
                    results.push({ server, url: href, label: text || 'Download' });
                }
            });
            return results;
        }""")

        # Deduplicate
        seen, unique = set(), []
        for link in final_links:
            if link['url'] not in seen:
                seen.add(link['url'])
                unique.append(link)
        return unique

    finally:
        try:
            context.close()
        except Exception:
            pass


def resolve_wrapper(short_url):
    """Sync wrapper for Flask. Uses a lock because Playwright sync API is not thread-safe."""
    key = f"resolve_{short_url}"
    cached = _get_cache(key)
    if cached is not None:
        return cached

    with _playwright_lock:
        # Double-check after acquiring lock
        cached = _get_cache(key)
        if cached is not None:
            return cached
        try:
            result = _resolve_with_playwright(short_url)
            _set_cache(key, result)
            return result
        except Exception as e:
            return {'error': str(e)}
