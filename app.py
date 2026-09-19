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
    data = request.get_json(silent=True) or {}
    query = data.get('query')
    if not query:
        return jsonify({'error': 'Missing query'}), 400
    try:
        results = crawler.search_movies(query)
        return jsonify(results)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/downloads', methods=['POST'])
def downloads():
    data = request.get_json(silent=True) or {}
    url = data.get('url')
    mode = data.get('mode')  # 'complete' or 'episodes'
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    try:
        options = crawler.get_download_options(url, mode)
        return jsonify(options)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/resolve', methods=['POST'])
def resolve():
    data = request.get_json(silent=True) or {}
    short_url = data.get('short_url')
    if not short_url:
        return jsonify({'error': 'Missing short_url'}), 400
    try:
        final = crawler.resolve_wrapper(short_url)
        return jsonify(final)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
