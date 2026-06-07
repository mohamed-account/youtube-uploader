from flask import Flask, request, jsonify
import google.auth.transport.requests as google_auth
import google.oauth2.credentials
import googleapiclient.discovery
import googleapiclient.http
import requests
import os
import uuid

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True

YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
YOUTUBE_REFRESH_TOKEN = os.environ.get('YOUTUBE_REFRESH_TOKEN')

def get_authenticated_youtube_service():
    print("DEBUG: Getting authenticated YouTube service...")
    creds = google.oauth2.credentials.Credentials(
        None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET
    )
    auth_request = google_auth.Request()
    creds.refresh(auth_request)
    print("DEBUG: YouTube authentication successful")
    return googleapiclient.discovery.build('youtube', 'v3', credentials=creds)

def download_video_from_drive(file_id):
    print(f"DEBUG: Downloading video from Drive with file_id {file_id}")
    # Utiliser l'API Drive avec OAuth
    creds = google.oauth2.credentials.Credentials(
        None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET
    )
    auth_request = google_auth.Request()
    creds.refresh(auth_request)
    access_token = creds.token
    download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {'Authorization': f'Bearer {access_token}'}
    print(f"DEBUG: Requesting {download_url}")
    response = requests.get(download_url, headers=headers, stream=True)
    print(f"DEBUG: Drive API response status: {response.status_code}")
    response.raise_for_status()
    tmp_filename = f"/tmp/{uuid.uuid4()}.mp4"
    with open(tmp_filename, 'wb') as f:
        total = 0
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            total += len(chunk)
        print(f"DEBUG: Downloaded {total} bytes to {tmp_filename}")
    return tmp_filename

@app.route('/upload', methods=['POST'])
def upload():
    print("DEBUG: Received request to /upload")
    try:
        data = request.get_json()
        if not data:
            print("DEBUG: No JSON body")
            return jsonify({'error': 'No JSON body'}), 400
    except Exception as e:
        print(f"DEBUG: JSON parse error: {str(e)}")
        return jsonify({'error': f'Invalid JSON: {str(e)}'}), 400

    video_url = data.get('video_url')
    title = data.get('title')
    description = data.get('description', '')
    file_id = data.get('file_id')
    print(f"DEBUG: file_id={file_id}, title={title}")

    if not file_id:
        print("DEBUG: Missing file_id")
        return jsonify({'error': 'Missing file_id'}), 400
    if not title:
        print("DEBUG: Missing title")
        return jsonify({'error': 'Missing title'}), 400

    try:
        tmp_file = download_video_from_drive(file_id)
        print(f"DEBUG: Downloaded to {tmp_file}")
    except Exception as e:
        print(f"DEBUG: Download error: {str(e)}")
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
        media = googleapiclient.http.MediaFileUpload(tmp_file, chunksize=1024*1024, resumable=True)
        print("DEBUG: Starting YouTube upload...")
        request_youtube = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        response = request_youtube.execute()
        video_id = response['id']
        print(f"DEBUG: YouTube upload successful, video_id={video_id}")
    except Exception as e:
        print(f"DEBUG: YouTube upload error: {str(e)}")
        return jsonify({'error': f'YouTube upload error: {str(e)}'}), 500
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
            print(f"DEBUG: Removed temporary file {tmp_file}")

    return jsonify({'video_id': video_id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)
