from flask import Flask, request, jsonify
import google.auth.transport.requests as google_auth
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
import requests
import os
import uuid
import re
import time

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True
app.config['REQUEST_TIMEOUT'] = 600  # 10 minutes

# Variables d'environnement
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

def download_video_from_drive(drive_url, file_id=None):
    session = requests.Session()
    # Premier appel pour obtenir la page d'avertissement ou la redirection
    resp = session.get(drive_url, allow_redirects=True, timeout=60)
    
    # Si on a déjà un fichier binaire (Content-Type video), on le sauvegarde directement
    if 'video' in resp.headers.get('Content-Type', ''):
        tmp = f"/tmp/{uuid.uuid4()}.mp4"
        with open(tmp, 'wb') as f:
            f.write(resp.content)
        return tmp
    
    # Sinon, chercher le paramètre confirm dans la page HTML
    confirm_match = re.search(r'confirm=([^&]+)', resp.text)
    if confirm_match:
        confirm = confirm_match.group(1)
        if file_id:
            download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm}"
        else:
            # extraire id de l'URL
            id_match = re.search(r'id=([^&]+)', drive_url)
            if id_match:
                file_id = id_match.group(1)
                download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm}"
            else:
                raise Exception("Impossible d'extraire l'ID")
    else:
        # Pas de page d'avertissement : l'URL est déjà directe
        download_url = drive_url

    # Téléchargement en streaming
    tmp_filename = f"/tmp/{uuid.uuid4()}.mp4"
    with session.get(download_url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return tmp_filename

@app.route('/upload', methods=['POST'])
def upload():
    start_time = time.time()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON body'}), 400
    except Exception as e:
        return jsonify({'error': f'Invalid JSON: {str(e)}'}), 400

    video_url = data.get('video_url')
    title = data.get('title')
    description = data.get('description', '')
    file_id = data.get('file_id')

    if not video_url or not title:
        return jsonify({'error': 'Missing video_url or title'}), 400

    try:
        # Télécharger la vidéo
        tmp_file = download_video_from_drive(video_url, file_id)
        print(f"Téléchargement terminé en {time.time()-start_time:.2f}s")
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

    # Upload vers YouTube
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
        media = googleapiclient.http.MediaFileUpload(tmp_file, chunksize=1024*1024, resumable=True)
        request_youtube = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        result = None
        while result is None:
            status, result = request_youtube.next_chunk()
            if status:
                print(f"Upload YouTube: {int(status.progress()*100)}%")
        video_id = result['id']
    except Exception as e:
        return jsonify({'error': f'YouTube upload error: {str(e)}'}), 500
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)

    return jsonify({'video_id': video_id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True, threaded=True)
