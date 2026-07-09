# cinecrawler_optimized.py
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from functools import lru_cache
import time

DOMAIN = "4khdhub.one"
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# ---------- Simple in-memory cache ----------
cache = {}
CACHE_TTL = 3600  # 1 hour

def get_cache(key):
    if key in cache and time.time() - cache[key]['time'] < CACHE_TTL:
        return cache[key]['data']
    return None

def set_cache(key, data):
    cache[key] = {'data': data, 'time': time.time()}

# ---------- 1. Search ----------
def search_movies(query):
    cache_key = f"search_{query}"
    cached = get_cache(cache_key)
    if cached:
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
            if title_el and card.get('href'):
                title = title_el.text.strip()
                year = re.search(r'(\d{4})', meta_el.text if meta_el else '')
                year = year.group(1) if year else ''
                poster = img_el.get('src', '') if img_el else ''
                results.append({
                    'title': f"{title} ({year})" if year else title,
                    'detailUrl': card['href'],
                    'poster': poster
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
    cache_key = f"options_{detail_url}_{mode}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        resp = session.get(detail_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        options = []

        if mode == 'complete' or mode is None:
            items = soup.select('#complete-pack .download-item, .download-item, .season-item')
            for item in items:
                header = item.select_one('.download-header, .header')
                if not header:
                    header = item
                quality = ''
                title_line = header.select_one('.download-title-line, .file-title')
                if title_line:
                    quality = ' '.join(title_line.get_text().split())
                else:
                    flex = header.select_one('.flex-1, .info')
                    if flex:
                        quality = ' '.join(flex.get_text().split())
                size = ''
                audio = ''
                for badge in header.select('.badge, .tag'):
                    txt = badge.get_text().strip()
                    if 'GB' in txt or 'MB' in txt:
                        size = txt
                    if 'Hindi' in txt or 'English' in txt:
                        audio = txt
                # url
                file_id = header.get('data-file-id', '')
                content = None
                if file_id:
                    content = soup.select_one(f'#content-file{file_id}')
                if not content:
                    next_sib = header.find_next_sibling()
                    while next_sib and not next_sib.select_one('a[href*="hub"]'):
                        next_sib = next_sib.find_next_sibling()
                    content = next_sib
                url = ''
                if content:
                    link_el = content.select_one('a[href*="hubcloud"], a[href*="hubdrive"]')
                    if link_el:
                        url = link_el['href']
                if url:
                    label = quality or 'Download'
                    if size:
                        label += f' ({size}'
                        if audio:
                            label += f', {audio}'
                        label += ')'
                    options.append({'quality': label, 'url': url})
        elif mode == 'episodes':
            episodes = soup.select('.season-item.episode-item, .episode-item')
            for ep in episodes:
                header = ep.select_one('.episode-header, .header')
                if not header:
                    continue
                ep_num = header.select_one('.episode-number, .ep-num')
                ep_num_text = ep_num.get_text().strip() if ep_num else ''
                ep_title = header.select_one('.episode-title, .ep-name')
                ep_title_text = ep_title.get_text().strip() if ep_title else ''
                content = ep.select_one('.episode-content')
                if content:
                    for item in content.select('.episode-download-item'):
                        file_title = item.select_one('.episode-file-title')
                        file_title_text = file_title.get_text().strip() if file_title else ''
                        link_el = item.select_one('a[href*="hubcloud"], a[href*="hubdrive"]')
                        if link_el:
                            label = f'Episode {ep_num_text}'
                            if ep_title_text:
                                label += f': {ep_title_text}'
                            if file_title_text:
                                label += f' - {file_title_text}'
                            options.append({'quality': label, 'url': link_el['href']})
        set_cache(cache_key, options)
        return options
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
        btn = soup.select_one('a#download, button:has-text("Generate"), a:has-text("Generate")')
        if not btn:
            return extract_final_links(resp.text)
        generate_url = btn.get('href')
        if not generate_url:
            return extract_final_links(resp.text)
        full_url = urljoin(short_url, generate_url)
        resp2 = session.get(full_url, timeout=10)
        resp2.raise_for_status()
        return extract_final_links(resp2.text)
    except Exception as e:
        return {'error': str(e)}

def extract_final_links(html):
    soup = BeautifulSoup(html, 'lxml')
    links = []
    patterns = [
        r'10Gbps|Server', r'ZipDisk|zip', r'fsl|cloudflare',
        r'storage\.googleapis\.com', r'Download'
    ]
    for a in soup.select('a[href]'):
        href = a.get('href')
        text = a.get_text().strip()
        if re.search(r'login|signin|telegram|t\.me|tinyurl|tutorial|hubcloud\.php|gamerxyt\.com', href, re.I):
            continue
        is_download = False
        server = 'Unknown'
        for p in patterns:
            if re.search(p, text, re.I) or re.search(p, href, re.I):
                is_download = True
                if '10Gbps' in text:
                    server = '10Gbps'
                elif 'ZipDisk' in text:
                    server = 'ZipDisk'
                elif 'FSL' in text:
                    server = 'FSL'
                elif 'storage.googleapis.com' in href:
                    server = 'ZipDisk'
                break
        if not is_download:
            if re.search(r'\.(zip|mkv|mp4)$', href) or 'storage.googleapis.com' in href:
                is_download = True
                server = 'Direct'
        if is_download and href:
            links.append({'server': server, 'label': text or 'Download', 'url': href})
    seen = set()
    unique = []
    for l in links:
        if l['url'] not in seen:
            seen.add(l['url'])
            unique.append(l)
    return unique

def resolve_wrapper(short_url):
    return resolve_shortlink_cached(short_url)
