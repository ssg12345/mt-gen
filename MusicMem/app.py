import spotipy
from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from spotipy.oauth2 import SpotifyOAuth
import json
import datetime
import os
import openai


app = Flask(__name__)
app.secret_key = os.urandom(24)

# SQLite setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///flask_session.db'
db = SQLAlchemy(app)



# Flask-Session config
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SESSION_SQLALCHEMY'] = db
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True

# Load environment variables from .env file
load_dotenv()

sp_oauth = SpotifyOAuth(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'),
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'),
    redirect_uri=os.getenv('SPOTIPY_REDIRECT_URI'),
    show_dialog=True,
    scope='playlist-modify-public user-library-read user-read-private'
)

openai.api_key = os.getenv('OPENAI_API_KEY')


@app.route('/')
def home():
    if 'spotify_user_displayname' in session:
        return render_template('home.html', username=session['spotify_user_displayname'])
    return render_template('home.html')

@app.route('/login')
def login():
    login_url = sp_oauth.get_authorize_url()
    return render_template('login.html', login_url=login_url)

@app.route('/logout')
def logout():
    session.clear()
    #login_url = sp_oauth.get_authorize_url()
    return render_template('home.html')
    #return render_template('login.html', login_url=login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_profile = sp.current_user()
    session['spotify_username'] = user_profile['id']
    session['spotify_user_displayname'] = user_profile['display_name']
    return redirect(url_for('home'))

@app.route('/get_user_info', methods=['GET', 'POST'])
def get_user_info():
    if 'token_info' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        senior_name = request.form.get('senior_name')
        mood = request.form.get('mood')
        age = request.form.get('age')
        genres = request.form.get('genres')
        artists = request.form.get('artists')
        language = request.form.get('language')

     
        #if not senior_name or not mood or not age or not genres or not artists or not language:
         #   return "Missing required fields!", 400

        if not senior_name or not age or not genres:
            return "Missing required fields!", 400

        session['senior_name'] = senior_name
        session['mood'] = mood
        session['age'] = age
        session['genres'] = genres
        session['artists'] = artists
        session['language'] = language
        return redirect(url_for('recommendations'))

    return render_template('get_user_info.html', username=session['spotify_user_displayname'])

@app.route('/recommendations', methods=['GET', 'POST'])
def recommendations():
    if 'token_info' not in session or 'senior_name' not in session:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=ensure_spotify_token())
 
    genres = session.get('genres')
    artists = session.get('artists')
    language = session.get('language')
    mood = session.get('mood', 'calming')
    age = int(session.get('age', 0))
    
    
    current_year = datetime.date.today().year
    start_year = current_year - age + 13
    end_year = start_year + 20
    
    if request.method == 'GET':
        track_list = generate_ai_playlist(genres, artists, start_year, end_year, mood,language)
       
    
    if request.method == 'POST':
        selected_tracks = request.form.getlist('tracks')
        playlist_name = request.form.get('playlist_name', 'My Playlist')

        senior_name = session['senior_name']
        playlist_name = f"mm_{senior_name}_{playlist_name}"

        if not selected_tracks:
            return render_template('recommendations.html', error="No tracks selected.", username=session['spotify_user_displayname'])

        valid_tracks = []
        for track_info in selected_tracks:
            parts = track_info.split(":")
            song_title = parts[0]
            artist_name = parts[1]
            track_id = get_track_id(sp, song_title, artist_name)
            if track_id:
                t_info = sp.track(track_id)  # Check if the track ID is valid
                if t_info:
                    valid_tracks.append(track_id)

        if valid_tracks:
            #Create a description that would include the inputs created
            playlist_description = f"{genres}_{mood}_{language}_{age}_{artists}"
            playlist = sp.user_playlist_create(user=sp.current_user()['id'], name=playlist_name, public=True, description=playlist_description)
            sp.user_playlist_add_tracks(user=sp.current_user()['id'], playlist_id=playlist['id'], tracks=valid_tracks)
            session['playlist_id'] = playlist['id']
            return redirect(url_for('show_playlist', playlist_id=playlist['id']))
        else:
            return render_template('recommendations.html', error="No valid tracks selected. Didn't create Playlist", tracks=track_list, username=session['spotify_user_displayname'])

    return render_template('recommendations.html', tracks=track_list, username=session['spotify_user_displayname'])

@app.route('/show_playlist/<playlist_id>', methods=['GET', 'POST'])
def show_playlist(playlist_id):
    if 'token_info' not in session:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=session['token_info']['access_token'])
    try:
        playlist = sp.playlist(playlist_id)
    except spotipy.exceptions.SpotifyException as e:
        print(f"Failed to fetch playlist: {e}")
        return redirect(url_for('home'))

    if request.method == 'POST':
        track_to_remove = request.form.get('remove_tracks')
        if track_to_remove:
            sp.playlist_remove_all_occurrences_of_items(playlist_id, [track_to_remove])
            return redirect(url_for('show_playlist', playlist_id=playlist_id))

    return render_template('show_playlist.html', playlist=playlist, tracks=playlist['tracks']['items'], username=session['spotify_user_displayname'])

def generate_ai_playlist(in_genre, in_fav_artists, start_yr, end_yr, mood,language):
    user_content = f"Generate a playlist of songs in the genre: {in_genre}, mostly by artists: {in_fav_artists}, released between {start_yr} and {end_yr}, and matching the mood: {mood}. Should also be in the language {language}"
    playlist_example = """
        [
            {"song": "Hurt", "artist": "Johnny Cash"},
            {"song": "Yesterday", "artist": "The Beatles"},
            {"song": "Someone Like You", "artist": "Adele"}
        ]
        """
    gpt_playlist_prompt = [
        {"role": "system", "content": "You are an assistant helping the user create personalized music playlists using Spotify. Generate a list of songs and artists based on the user's preferences. Output the list as a JSON array like this: [{\"song\": <song_title>, \"artist\": <artist_name>}]. Do not return anything else than the JSON array."},
        {"role": "assistant", "content": playlist_example},
        {"role": "user", "content": user_content}
    ]

    try:
        completion = openai.chat.completions.create(
            model="gpt-4",
            messages=gpt_playlist_prompt,
            max_tokens=300
        )
        
        response_content = completion.choices[0].message.content.strip()
        tracks_result = json.loads(response_content)
        

        if not tracks_result or not isinstance(tracks_result, list):
            raise ValueError("Invalid response from OpenAI")
        
        sp = spotipy.Spotify(auth=ensure_spotify_token())

        valid_tracks = []
        for track in tracks_result:
            song_title = track.get('song', 'Unknown Song')
            artist_name = track.get('artist', 'Unknown Artist')

           
            track_id = get_track_id(sp, song_title, artist_name)
            if track_id:
                track['track_id'] = track_id
                
               
                track_data = sp.track(track_id)
                
                if track_data and 'preview_url' in track_data:
                    track['snippet'] = track_data['preview_url']
                else:
                    track['snippet'] = None  

                if track_data:
                    valid_tracks.append(track)
            else:
                track['snippet'] = None  

        return valid_tracks

    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response: {e}")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []


def get_track_id(sp_in, song_name, artist_name):
    try:
        query = f"track:{song_name.strip()}, artist:{artist_name.strip()}"
        result = sp_in.search(q=query, type='track', limit=1)
        
        if result['tracks']['items']:
            return result['tracks']['items'][0]['id']
        else:
            print(f"No track found for {song_name} by {artist_name}")
            return None
    except Exception as e:
        print(f"Spotify API error: {e}")
        return None

def ensure_spotify_token():
    token_info = session.get('token_info', None)
    
    if not token_info:
        raise ValueError("Spotify token not found")
    
    if sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info
    
    return token_info['access_token']

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
