@app.route('/upload', methods=['POST'])
def upload():
    data = request.get_json()
    video_url = data.get('video_url')  # attend une URL Drive (format uc?id=...&export=download)
    title = data.get('title')
    description = data.get('description', '')

    # 1. Télécharger la vidéo depuis Drive en gérant la redirection et l'avertissement
    import requests
    session = requests.Session()
    # Premier appel pour obtenir la page d'avertissement
    resp = session.get(video_url, allow_redirects=True)
    # Extraire le paramètre confirm de la page si présent (pour les gros fichiers)
    import re
    confirm_match = re.search(r'confirm=([^&]+)', resp.text)
    if confirm_match:
        confirm = confirm_match.group(1)
        download_url = f"https://drive.google.com/uc?id={data.get('file_id')}&export=download&confirm={confirm}"
    else:
        download_url = video_url

    # Télécharger le fichier
    tmp_filename = f"/tmp/{uuid.uuid4()}.mp4"
    with session.get(download_url, stream=True) as r:
        r.raise_for_status()
        with open(tmp_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # 2. Upload vers YouTube (inchangé)
    youtube = get_authenticated_service()
    body = {
        'snippet': {'title': title, 'description': description, 'categoryId': '22'},
        'status': {'privacyStatus': 'public'}
    }
    media = googleapiclient.http.MediaFileUpload(tmp_filename, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    result = request.execute()

    os.remove(tmp_filename)
    return jsonify({'video_id': result['id']})
