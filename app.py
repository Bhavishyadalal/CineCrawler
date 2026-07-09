# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import cinecrawler_optimized as crawler

app = Flask(__name__)
CORS(app)

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get('query')
    if not query:
        return jsonify({'error': 'Missing query'}), 400
    results = crawler.search_movies(query)
    return jsonify(results)

@app.route('/downloads', methods=['POST'])
def downloads():
    data = request.get_json()
    url = data.get('url')
    mode = data.get('mode')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    options = crawler.get_download_options(url, mode)
    return jsonify(options)

@app.route('/resolve', methods=['POST'])
def resolve():
    data = request.get_json()
    short_url = data.get('short_url')
    if not short_url:
        return jsonify({'error': 'Missing short_url'}), 400
    final_links = crawler.resolve_wrapper(short_url)
    return jsonify(final_links)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
