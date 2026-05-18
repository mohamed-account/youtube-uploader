from flask import Flask, request, jsonify
import google.auth.transport.requests as google_auth
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
import requests as req
import os
import uuid

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True

# Variables d'environnement (à définir sur Render)
YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
YOUTUBE_REFRESH_TOKEN = os.environ.get('YOUTUBE_REFRESH_TOKEN')

def get_authenticated_service():
    credentials = google.oauth2.credentials.Credentials(
        None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET
    )
    auth_request = google_auth.Request()
    credentials.refresh(auth_request)
    return googleapiclient.discovery.build('youtube', 'v3', credentials=credentials)

@app.route('/upload', methods=['POST'])
def upload():
    # 1. Récupérer les données JSON
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON body'}), 400
    except Exception as e:
        return jsonify({'error': f'Invalid JSON: {str(e)}'}), 400

    video_url = data.get('video_url')
    title = data.get('title')
    description = data.get('description', '')

    if not video_url or not title:
        return jsonify({'error': 'Missing video_url or title'}), 400

    # 2. Télécharger la vidéo depuis Cloudinary
    tmp_filename = f"/tmp/{uuid.uuid4()}.mp4"
    try:
        response = req.get(video_url, stream=True)
        if response.status_code != 200:
            return jsonify({'error': f'Failed to download video, HTTP {response.status_code}'}), 400
        with open(tmp_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

    # 3. Upload vers YouTube
    try:
        youtube = get_authenticated_service()
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'public'
            }
        }
        media = googleapiclient.http.MediaFileUpload(tmp_filename, chunksize=-1, resumable=True)
        youtube_request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        result = youtube_request.execute()
        video_id = result['id']
    except Exception as e:
        return jsonify({'error': f'YouTube upload error: {str(e)}'}), 500
    finally:
        if os.path.exists(tmp_filename):
            os.remove(tmp_filename)

    return jsonify({'video_id': video_id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)
