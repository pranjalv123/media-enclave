# menclave/aenclave/control.py

"""Music player control functions."""

import logging

import Pyro.core

from menclave import settings
from menclave.aenclave.models import Channel, Song

#=============================================================================#

class ControlError(Exception):

    """The exception class for music control-related errors."""

    pass

def delegate_rpc(method):
    """Delegate a method to the instance player proxy, and then call it."""
    def new_method(self, *args, **kwargs):
        try:
            retval = getattr(self.player, method.__name__)(*args, **kwargs)
        except Exception, e:
            # This will be a pyro remote error.  Log the remote trace.
            logging.exception('RPC raised exception; remote traceback:\n' +
                              ''.join(Pyro.util.getPyroTraceback(e)))
            raise ControlError(e.message)
        else:
            kwargs['rpc_retval'] = retval
            return method(self, *args, **kwargs)
    return new_method

#=============================================================================#

class Controller(object):

    """
    Class for remotely controlling the playback of a channel.

    channel -- The id of the controlled channel.
    player -- The Pyro remote player object.

    This class wraps a RemotePlayer object does extra client-side steps as
    necessary.  All multi-step player logic belongs in the base GstPlayer object
    to avoid multiple RPCs.  The player is also synchronized, so we avoid race
    conditions by doing computation in the player.
    """

    def __init__(self, channel=None):
        """
        Create a controller for the given channel or the default channel, 1.
        """
        if channel is None: channel = Channel.default()
        self.channel = channel
        # TODO(rnk): Change the naming to make one remote object per channel.
        #subs = (settings.HOST_NAME, settings.GST_PLAYER_PORT, channel.id)
        #uri = "PYROLOC://%s:%i/gst_player/%i" % subs
        uri = "PYROLOC://%s:%i/gst_player" % (settings.GST_PLAYER_HOST,
                                              settings.GST_PLAYER_PORT)
        self.player = Pyro.core.getProxyForURI(uri)

    #---------------------------- STATUS METHODS -----------------------------#

    def _refresh_songs(self, songs):
        """
        Refresh song models, preserving the player-added attributes.

        We do this so that we can have the most up-to-date tags if the user
        editted the tags while the song was on the queue.
        """
        pks = [song.pk for song in songs]
        fresh_dict = Song.objects.in_bulk(pks)
        fresh_songs = []
        for song in songs:
            fresh_song = fresh_dict[song.pk]
            fresh_song.noise = song.noise
            fresh_song.playid = song.playid
            fresh_songs.append(fresh_song)
        return fresh_songs

    @delegate_rpc
    def get_channel_snapshot(self, rpc_retval=None):
        """Return a snapshot of the current channel state."""
        rpc_retval.song_queue = self._refresh_songs(rpc_retval.song_queue)
        rpc_retval.song_history = self._refresh_songs(rpc_retval.song_history)
        return rpc_retval

    #--------------------------- PLAYBACK CONTROL ----------------------------#

    @delegate_rpc
    def stop(self, rpc_retval=None):
        """Stops the music and clears the queue."""
        self.channel.touch()

    @delegate_rpc
    def pause(self, rpc_retval=None):
        """Pause the music."""
        self.channel.touch()

    @delegate_rpc
    def unpause(self, rpc_retval=None):
        """Unpause the music."""
        self.channel.touch()

    @delegate_rpc
    def skip(self, rpc_retval=None):
        """Skip the current song and play a dequeue noise."""
        self.channel.touch()

    #----------------------------- QUEUE CONTROL -----------------------------#

    def add_song(self, song, rpc_retval=None):
        """Add a song to the queue."""
        self.add_songs([song])

    @delegate_rpc
    def add_songs(self, songs, rpc_retval=None):
        """Add some songs to the queue."""
        self.channel.touch()

    def remove_song(self, playid, rpc_retval=None):
        """Remove the song with playid from the queue."""
        self.remove_songs([playid])

    @delegate_rpc
    def remove_songs(self, playids, rpc_retval=None):
        """Remove the songs with playids in playids from the queue."""
        self.channel.touch()

    @delegate_rpc
    def move_song(self, playid, after_playid, rpc_retval=None):
        """Move the first song to after the second song in the queue."""
        self.channel.touch()

    @delegate_rpc
    def shuffle(self, rpc_retval=None):
        """Shuffle the songs in the queue."""
        self.channel.touch()

#=============================================================================#
