# Media-Enclave #

Media-enclave is a collection of Django web applications to manage media in a community environment.  Our two major sub-projects are:

  * Audio-enclave, which allows a community to upload their music to a communal "jukebox" where it can be made into shared playlists and played back.
  * Video-enclave, which allows users to search their movie collections using metadata scraped from sites like IMDB, metacritic, and Rotten Tomatoes.

Currently, audio-enclave is our only functional application, but we are beginning work on video-enclave.

## Audio-Enclave ##

Audio-enclave is a web application that controls music player running in the background.  It allows users to upload songs, search for music, make playlists, and control playback.  We eventually intend to support separate channels of music which are piped to specific locations, but for now the player just outputs to the default device.  [InstallingAudioEnclave](InstallingAudioEnclave.md)

## Video-Enclave ##

Video-enclave is a web application that allows users to search their sometimes large movie collections with metadata scraped from IMDB and other web sites.  The goal is to make finding a movie to watch as easy as finding music with audio-enclave.  We want to allow the user to search for films with Sean Penn or directed by Quentin Tarantino without having to go to an external web site like IMDB and then check if they own that film.

## Speech Interface ##

During January 2009 we started writing a speech interface for audio-enclave with [WAMI](http://wami.csail.mit.edu/) from the CS and AI Lab at MIT.  Our goal is to be able to walk into the room where the sound system is set up, push a button on the wall, say "queue [song name](my.md)", and have the music start.  This would, of course, make a very nice demo.  :)