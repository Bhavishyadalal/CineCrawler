# app.py
# Hollywood-only backend – uses 4khdhub.one

from flask import Flask, request, jsonify
from flask_cors import CORS
import traceback
import cinecrawler_optimized as crawler

app = Flask(__name__)
CORS(app)


@app.route('/', methods=['GET'])
def home():
    return "CineCrawler API is alive (Hollywood only)", 200


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200


@app.route('/search', methods=['POST'])
def search():
    """Always returns a JSON array."""
    data = request.get_json(silent=True) or {}
    query = data.get('query')
    if not query:
        return jsonify([]), 200          # <-- array, not error object
    try:
        return jsonify(crawler.search_movies(query))
    except Exception as e:
        traceback.print_exc()
        return jsonify([]), 200          # <-- array, not 500


@app.route('/downloads', methods=['POST'])
def downloads():
    """Always returns a JSON array."""
    data = request.get_json(silent=True) or {}
    url = data.get('url')
    mode = data.get('mode')
    if not url:
        return jsonify([]), 200
    try:
        return jsonify(crawler.get_download_options(url, mode))
    except Exception as e:
        traceback.print_exc()
        return jsonify([]), 200


@app.route('/resolve', methods=['POST'])
def resolve():
    """Always returns a JSON array."""
    data = request.get_json(silent=True) or {}
    short_url = data.get('short_url')
    if not short_url:
        return jsonify([]), 200
    try:
        return jsonify(crawler.resolve_wrapper(short_url))
    except Exception as e:
        traceback.print_exc()
        return jsonify([]), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
