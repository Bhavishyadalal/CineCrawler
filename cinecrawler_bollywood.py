# cinecrawler_bollywood.py – MINIMAL TEST VERSION
from flask import jsonify

def search_movies(query):
    return [{"title": "Test Movie", "detailUrl": "https://test.com"}]

def get_download_options(detail_url, mode=None):
    return [{"quality": "Test 1080p", "url": "https://test.com"}]

def resolve_wrapper(short_url):
    return [{"server": "Test", "label": "Download", "url": "https://test.com"}]
