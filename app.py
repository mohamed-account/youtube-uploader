# À ajouter après les imports
def upload_to_facebook(video_path, description, access_token, page_id):
    url = f"https://graph-video.facebook.com/v19.0/{page_id}/videos"
    params = {'access_token': access_token}
    with open(video_path, 'rb') as f:
        files = {'source': f}
        data = {'description': description, 'published': 'true'}
        response = requests.post(url, params=params, files=files, data=data)
    return response.json()

def upload_to_instagram(video_path, caption, access_token, ig_user_id):
    # Instagram utilise l'API Facebook, avec un conteneur média puis publication
    # Pour simplifier, tu peux d'abord implémenter Facebook, puis Instagram plus tard
    pass

# Ensuite, dans la fonction /upload, ajoute un paramètre 'platform'
# et aiguille vers la bonne fonction
