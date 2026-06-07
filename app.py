from flask import Flask, request, jsonify
import google.auth.transport.requests as google_auth
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
import requests
import os
import uuid
import re

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True

# Variables d'environnement (à définir sur Render)
YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
YOUTUBE_REFRESH_TOKEN = os.environ.get('YOUTUBE_REFRESH_TOKEN')

def get_authenticated_service():
    """Construit un service YouTube authentifié avec le refresh token."""
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
    """
    Télécharge une vidéo depuis Google Drive en contournant la page d'avertissement
    pour les fichiers volumineux.
    """
    session = requests.Session()
    # Premier appel pour obtenir la page d'avertissement
    resp = session.get(drive_url, allow_redirects=True)
    
    # Chercher le paramètre 'confirm' dans la page HTML
    confirm_match = re.search(r'confirm=([^&]+)', resp.text)
    if confirm_match:
        confirm = confirm_match.group(1)
        # Construire l'URL de téléchargement direct avec le confirm
        if file_id:
            download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm}"
        else:
            # Extraire l'ID depuis l'URL d'origine si non fourni
            match = re.search(r'id=([^&]+)', drive_url)
            if match:
                file_id = match.group(1)
                download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm}"
            else:
                raise Exception("Impossible d'extraire l'ID du fichier Drive")
    else:
        download_url = drive_url

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
    file_id = data.get('file_id')  # Optionnel, mais aide pour Drive

    if not video_url or not title:
        return jsonify({'error': 'Missing video_url or title'}), 400

    # 2. Télécharger la vidéo (depuis Google Drive ou autre URL)
    try:
        if 'drive.google.com' in video_url or 'drive.usercontent' in video_url:
            tmp_file = download_video_from_drive(video_url, file_id)
        else:
            # Pour les autres URLs (Cloudinary, etc.), téléchargement simple
            tmp_file = f"/tmp/{uuid.uuid4()}.mp4"
            r = requests.get(video_url, stream=True)
            r.raise_for_status()
            with open(tmp_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
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
                'categoryId': '22'  # People & Blogs
            },
            'status': {
                'privacyStatus': 'public'
            }
        }
        media = googleapiclient.http.MediaFileUpload(tmp_file, chunksize=-1, resumable=True)
        request_youtube = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        result = request_youtube.execute()
        video_id = result['id']
    except Exception as e:
        return jsonify({'error': f'YouTube upload error: {str(e)}'}), 500
    finally:
        # Nettoyer le fichier temporaire
        if os.path.exists(tmp_file):
            os.remove(tmp_file)

    return jsonify({'video_id': video_id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)
