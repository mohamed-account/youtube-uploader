from flask import Flask, request, jsonify
import google.auth.transport.requests
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
import yt_dlp
import os
import uuid

app = Flask(__name__)

YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'
CLIENT_SECRETS_FILE = 'client_secret.json' # On ajoutera ce fichier plus tard

# Les variables d'environnement sont définies dans Render
REFRESH_TOKEN = os.environ.get('YOUTUBE_REFRESH_TOKEN')
CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')

def get_authenticated_service():
    credentials = google.oauth2.credentials.Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return googleapiclient.discovery.build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials)

@app.route('/upload', methods=['POST'])
def upload():
    data = request.json
    video_url = data['video_url']
    title = data['title']
    description = data.get('description', '')

    # Télécharger la vidéo
    tmp_filename = f"/tmp/{uuid.uuid4()}.mp4"
    ydl_opts = {'outtmpl': tmp_filename}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    # Upload vers YouTube
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
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    response = request.execute()

    os.remove(tmp_filename)
    return jsonify({'video_id': response['id']})

if __name__ == '__main__':
    # Pour un débogage local, on active le mode debug
    app.run(host='0.0.0.0', port=10000, debug=True)

# Pour la production avec Gunicorn, on force la propagation des exceptions
# afin qu'elles soient visibles dans les logs Render.
app.config['PROPAGATE_EXCEPTIONS'] = True
