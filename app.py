from flask import Flask, request, jsonify
import google.auth.transport.requests as google_auth
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
from googleapiclient.http import MediaFileUpload
import requests
import os
import uuid
import re

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True

YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
YOUTUBE_REFRESH_TOKEN = os.environ.get('YOUTUBE_REFRESH_TOKEN')

def get_authenticated_youtube_service():
    creds = google.oauth2.credentials.Credentials(
        None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET
    )
    auth_request = google_auth.Request()
    creds.refresh(auth_request)
    return googleapiclient.discovery.build('youtube', 'v3', credentials=creds)

def download_video_from_drive(file_id):
    """
    Télécharge un fichier depuis Google Drive en contournant la page d'avertissement.
    """
    session = requests.Session()
    # Étape 1: Obtenir la page d'avertissement (ou le fichier directement)
    url = f"https://drive.google.com/uc?id={file_id}&export=download"
    resp = session.get(url, allow_redirects=True)
    
    # Chercher le paramètre confirm dans l'URL de redirection ou dans le HTML
    confirm_match = re.search(r'confirm=([^&]+)', resp.url)
    if not confirm_match:
        confirm_match = re.search(r'confirm=([^&]+)', resp.text)
    
    if confirm_match:
        confirm = confirm_match.group(1)
        download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm}"
    else:
        download_url = url
    
    # Télécharger le fichier
    tmp_filename = f"/tmp/{uuid.uuid4()}.mp4"
    with session.get(download_url, stream=True) as r:
        r.raise_for_status()
        with open(tmp_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return tmp_filename

@app.route('/upload', methods=['POST'])
def upload():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON body'}), 400
    except Exception as e:
        return jsonify({'error': f'Invalid JSON: {str(e)}'}), 400

    file_id = data.get('file_id')
    title = data.get('title')
    description = data.get('description', '')

    if not file_id:
        return jsonify({'error': 'Missing file_id'}), 400
    if not title:
        return jsonify({'error': 'Missing title'}), 400

    try:
        tmp_file = download_video_from_drive(file_id)
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

    try:
        youtube = get_authenticated_youtube_service()
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
        media = MediaFileUpload(tmp_file, chunksize=1024*1024, resumable=True)
        request_youtube = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        response = request_youtube.execute()
        video_id = response['id']
    except Exception as e:
        return jsonify({'error': f'YouTube upload error: {str(e)}'}), 500
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)

    return jsonify({'video_id': video_id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)
