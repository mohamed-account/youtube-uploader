from flask import Flask, request, jsonify
import google.auth.transport.requests as google_auth
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
import requests
import gdown
import os
import uuid
import time

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True
app.config['MAX_CONTENT_LENGTH'] = None  # Pas de limite de taille

# Variables d'environnement (à définir sur Render)
YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
YOUTUBE_REFRESH_TOKEN = os.environ.get('YOUTUBE_REFRESH_TOKEN')
FACEBOOK_ACCESS_TOKEN = os.environ.get('FACEBOOK_ACCESS_TOKEN')
PAGE_ID = os.environ.get('PAGE_ID')

# --------------------------------------------------------------
# Téléchargement depuis Google Drive (même >100 Mo)
# --------------------------------------------------------------
def download_video_from_drive(file_id):
    drive_url = f'https://drive.google.com/uc?id={file_id}'
    tmp_file = f'/tmp/{uuid.uuid4()}.mp4'
    print(f"Téléchargement de {drive_url} vers {tmp_file}")
    gdown.download(drive_url, tmp_file, quiet=False)
    if not os.path.exists(tmp_file):
        raise Exception(f"Échec du téléchargement : {tmp_file} non créé")
    return tmp_file

# --------------------------------------------------------------
# YouTube
# --------------------------------------------------------------
def get_youtube_service():
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

def upload_to_youtube(video_path, title, description):
    youtube = get_youtube_service()
    body = {
        'snippet': {
            'title': title[:100],
            'description': description[:5000],
            'categoryId': '22'
        },
        'status': {
            'privacyStatus': 'public'
        }
    }
    media = googleapiclient.http.MediaFileUpload(
        video_path,
        chunksize=1024*1024,  # 1 MB chunks pour économiser la RAM
        resumable=True
    )
    request_youtube = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )
    response = None
    while response is None:
        try:
            status, response = request_youtube.next_chunk()
            if status:
                print(f"YouTube progression: {int(status.progress() * 100)}%")
        except Exception as e:
            print(f"Erreur chunk YouTube: {e}")
            # On continue malgré les erreurs passagères
            pass
    return response

# --------------------------------------------------------------
# Facebook
# --------------------------------------------------------------
def upload_to_facebook(video_path, description):
    url = f"https://graph-video.facebook.com/v19.0/{PAGE_ID}/videos"
    params = {'access_token': FACEBOOK_ACCESS_TOKEN}
    with open(video_path, 'rb') as f:
        files = {'source': f}
        data = {'description': description[:2000], 'published': 'true'}
        response = requests.post(url, params=params, files=files, data=data)
    return response.json()

# --------------------------------------------------------------
# Point d'entrée unique
# --------------------------------------------------------------
@app.route('/upload', methods=['POST'])
def upload():
    start_time = time.time()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON body'}), 400

    platform = data.get('platform')      # "youtube", "facebook", ou "all"
    file_id = data.get('file_id')
    title = data.get('title', '')
    description = data.get('description', '')
    # Pour "all", on peut ignorer platform et publier sur tous
    if not platform and not file_id:
        return jsonify({'error': 'Missing platform or file_id'}), 400

    # Téléchargement (une seule fois)
    try:
        video_file = download_video_from_drive(file_id)
        print(f"Téléchargé: {video_file}, taille: {os.path.getsize(video_file)} octets")
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

    # Publier selon la plateforme
    try:
        if platform == 'youtube':
            result = upload_to_youtube(video_file, title, description)
            response_data = {'video_id': result['id']}
        elif platform == 'facebook':
            result = upload_to_facebook(video_file, description)
            response_data = {'post_id': result.get('id')}
        elif platform == 'all':
            # Publier sur YouTube ET Facebook
            results = {}
            try:
                results['youtube'] = upload_to_youtube(video_file, title, description)['id']
            except Exception as e:
                results['youtube'] = f"Erreur: {str(e)}"
            try:
                results['facebook'] = upload_to_facebook(video_file, description)['id']
            except Exception as e:
                results['facebook'] = f"Erreur: {str(e)}"
            response_data = results
        else:
            return jsonify({'error': f'Platform {platform} not implemented'}), 400
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500
    finally:
        if os.path.exists(video_file):
            os.remove(video_file)
            print("Fichier temporaire supprimé")

    elapsed = time.time() - start_time
    print(f"Traitement terminé en {elapsed:.2f}s")
    return jsonify(response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
