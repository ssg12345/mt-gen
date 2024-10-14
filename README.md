This is project for a Web app that is used to automatically generate a playlist based on user preference. The code can be used to deploy a Flask based webserver on any server. The webserver takes user inputs like age, mood of the songs, favorite artists, genre and language. 

This project uses openAI to get a list of potential songs. If the song is available on spotify, this is offered as an option to the user. The user can select the desired songs to create a playlist


The main web server flask code is in app.py
The html files and style sheets can be found in the templates and static folders respectively
This code requires user to login with spotify account. The Spotify and openAI credentials are loaded from environment variables



