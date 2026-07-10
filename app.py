# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import cinecrawler_optimized as hollywood
import cinecrawler_bollywood as bollywood

app = Flask(__name__)
CORS(app)

# ---------- Health check ----------
@app.route('/', methods=['GET'])
def home():
    return "CineCrawler API is alive", 200

# ---------- Search ----------
@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get('query')
    source = data.get('source', 'hollywood')  # default hollywood
    if not query:
        return jsonify({'error': 'Missing query'}), 400

    if source == 'bollywood':
        results = bollywood.search_movies(query)
    else:
        results = hollywood.search_movies(query)

    return jsonify(results)

# ---------- Get download options ----------
@app.route('/downloads', methods=['POST'])
def downloads():
    data = request.get_json()
    url = data.get('url')
    mode = data.get('mode')
    source = data.get('source', 'hollywood')
    if not url:
        return jsonify({'error': 'Missing url'}), 400

    if source == 'bollywood':
        options = bollywood.get_download_options(url, mode)
    else:
        options = hollywood.get_download_options(url, mode)

    return jsonify(options)

# ---------- Resolve short link ----------
@app.route('/resolve', methods=['POST'])
def resolve():
    data = request.get_json()
    short_url = data.get('short_url')
    source = data.get('source', 'hollywood')
    if not short_url:
        return jsonify({'error': 'Missing short_url'}), 400

    if source == 'bollywood':
        final = bollywood.resolve_wrapper(short_url)
    else:
        final = hollywood.resolve_wrapper(short_url)

    return jsonify(final)

# ---------- Run ----------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
