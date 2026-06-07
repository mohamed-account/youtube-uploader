from flask import Flask, request, jsonify
import google.auth.transport.requests as google_auth
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
import gdown
import os
import uuid

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

    if not file_id or not title:
        return jsonify({'error': 'Missing file_id or title'}), 400

    # Télécharger la vidéo depuis Drive avec gdown
    drive_url = f'https://drive.google.com/uc?id={file_id}'
    tmp_file = f'/tmp/{uuid.uuid4()}.mp4'
    
    try:
        gdown.download(drive_url, tmp_file, quiet=False)
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

    # Upload vers YouTube
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
        media = googleapiclient.http.MediaFileUpload(tmp_file, chunksize=1024*1024, resumable=True)
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
