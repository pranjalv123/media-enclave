# menclave/aenclave/views.py

import datetime
import itertools
from math import ceil as ceiling
import os
import re
import tempfile
import zipfile
import time

from django.conf import settings
from django.contrib import auth
from django.core.urlresolvers import reverse
from django.core.files import File
from django.core.mail import send_mail, mail_admins
from django.core.servers.basehttp import FileWrapper
from django.db.models.query import Q
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import render_to_response
from django.template import loader, RequestContext
from django.contrib.auth.decorators import login_required
from django.utils.http import urlquote

import cjson

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

from menclave.aenclave.models import Channel, Playlist, PlaylistEntry, Song
from menclave.aenclave.control import Controller, ControlError

from menclave import settings as enc_settings
from menclave.aenclave import processing

#================================= UTILITIES =================================#

def direct_to_template(request, template, extra_context=None, mimetype=None,
                       **kwargs):
    """Render a given template with extra template variables."""
    if extra_context is None: extra_context = {}
    dictionary = {'params': kwargs}

    for key, value in extra_context.items():
        if callable(value):
            dictionary[key] = value()
        else:
            dictionary[key] = value
    c = RequestContext(request, dictionary)
    t = loader.get_template(template)
    return HttpResponse(t.render(c), mimetype=mimetype)

def render_html_template(template, request, options=None, *args, **kwargs):
    """Render a template response with some extra parameters."""
    # {} is an unsafe default value, so use use None instead.
    if options is None:
        options = {}

    return render_to_response(template, options, *args, **kwargs)

def render_json_template(*args, **kwargs):
    """Renders a JSON template, and then calls render_json_response()."""
    data = loader.render_to_string(*args, **kwargs)
    return render_json_response(data)

def render_json_response(data):
    """Sends an HttpResponse with the X-JSON header and the right mimetype."""
    resp = HttpResponse(data, mimetype=("application/json; charset=" +
                                        settings.DEFAULT_CHARSET))
    return resp

def json_success(message=""):
    return render_json_response(cjson.encode({'success': message}))

def json_error(message):
    return render_json_response(cjson.encode({'error': message}))

def render_xml_to_response(*args, **kwargs):
    return HttpResponse(loader.render_to_string(*args, **kwargs),
                        mimetype=("text/xml; charset=" +
                                  settings.DEFAULT_CHARSET))

def simple_xml_response(tagname):
    """simple_xml_response(tagname) -> single-tag XML HTTP-response"""
    return HttpResponse('<%s/>' % tagname,
                        mimetype=("text/xml; charset=" +
                                  settings.DEFAULT_CHARSET))

def xml_error(message):
    return render_xml_to_response('error.xml', {'error_message':message})

def html_error(request, message=None, title=None):
    return render_html_template('error.html', request,
                                {'error_message':message, 'error_title':title},
                                context_instance=RequestContext(request))

def get_unicode(form, key, default=None):
    value = form.get(key, None)
    if value is None: return default
    elif isinstance(value, unicode): return value
    elif isinstance(value, str):
        return value.decode(settings.DEFAULT_CHARSET, 'replace')
    else: return unicode(value)

def get_integer(form, key, default=None):
    try: return int(str(form[key]))
    except Exception: return default

def get_int_list(form, key):
    ints = []
    for string in form.get(key, '').split():
        try: ints.append(int(str(string)))
        except Exception: pass
    return ints

def get_song_list(form, key='ids'):
    """Given a list of ids in a form, fetch a list of Songs from the db.

    This function preserves the order of the ids as given in the form.
    """
    ids = get_int_list(form, key)
    song_dict = Song.objects.in_bulk(ids)
    return [song_dict[i] for i in ids if i in song_dict]

def parse_integer(string):
    try: return int(str(string))
    except Exception: raise ValueError('invalid integer: %r' % string)

def parse_date(string):
    string = string.strip().lower()
    if string == 'today': return datetime.date.today()
    elif string == 'yesterday':
        return datetime.date.today() - datetime.timedelta(1)
    # TODO make this more robust
    year,month,day = string.split('-')
    return datetime.date(int(year),int(month),int(day))

def parse_time(string):
    parts = string.strip().split(':')
    if len(parts) > 3: raise ValueError
    # This function is purposely forgiving.
    mult, total = 1, 0
    for part in reversed(parts):
        total += int(part) * mult
        mult *= 60
    return total

def Qu(field, op, value):
    return Q(**{(str(field) + '__' + str(op)): str(value)})

def get_anon_user():
    username = enc_settings.ANONYMOUS_USER
    try:
        anon = auth.models.User.objects.get(username = username)
    except auth.models.User.DoesNotExist:
        anon = auth.models.User.objects.create_user(username, '', '')
        anon.set_unusable_password()
        anon.save()
    return anon


def permission_required(perm, action, erf=html_error, perm_fail_erf=None):
    """
    Requre the user to have a permission or display an error message.

    perm - Permission to check.
    action - the type of action attempted
    erf - Error return function, takes request, text, title.
    perm_fail_erf - define this to use a different erf for permissions
    failures.
    """
    if perm_fail_erf is None:
        perm_fail_erf = erf

    def decorator(real_handler):
        def request_handler(request, *args, **kwargs):
            if not request.user.is_authenticated():
                # Check if the anonymous user has access.
                anon = get_anon_user()
                if anon.has_perm(perm):
                    return real_handler(request, *args, **kwargs)
                # Otherwise, show error message.
                error_text = ('You must <a href="%s">log in</a> to do that.' %
                              reverse('aenclave-login'))
                return erf(request, error_text, action)
            elif not request.user.has_perm(perm):
                # Check if the anonymous user has access.
                anon = get_anon_user()
                if anon.has_perm(perm):
                    return real_handler(request, *args, **kwargs)
                # Otherwise, show error message.
                error_text = ('You need more permissions to do that.')
                return perm_fail_erf(request, error_text, action)
            else:
                return real_handler(request, *args, **kwargs)
        return request_handler
    return decorator

def permission_required_redirect(perm, redirect_field_name):
    """
    Mimicks functionality of django.contrib.auth.permission_required
    """
    def erf(request, error_text, action):
        path = urlquote(request.get_full_path())
        tup = enc_settings.LOGIN_URL, redirect_field_name, path
        return HttpResponseRedirect('%s?%s=%s' % tup)
    return permission_required(perm, '', erf, html_error)
                                        
def permission_required_xml(perm):
    return permission_required(perm, '', lambda r,text,act: xml_error(text))

def permission_required_json(perm):
    return permission_required(perm, '', lambda r,text,act: json_error(text))



#=================================== VIEWS ===================================#

#------------------------------- Login/Logout --------------------------------#

# push to a settings file, encourage end user to change it
SSL_AUTH_PASSWORD = 'password'

def user_debug(request):
    return render_html_template('user_debug.html', request,
                                context_instance=RequestContext(request))

def login(request):
    form = request.POST

    # First try SSL Authentication

    user = auth.authenticate(request=request)

    # Otherwise, treat this like a text login and show the login page if
    # necessary.
    if user is None:
        # If the user isn't trying to log in, then just display the login page.
        if not form.get('login', False):
            goto = request.GET.get('goto', None)
            context = RequestContext(request)
            return render_html_template('login.html', request,
                                        {'redirect_to': goto},
                                        context_instance=context)
        # Check if the username and password are correct.
        user = auth.authenticate(username=form.get('username', ''),
                                 password=form.get('password', ''))

    # If the username/password are invalid or SSL authentication failed tell
    # the user to try again.
    error_message = ''
    if user is None:
        error_message = 'Invalid username/password.'

    # If the user account is disabled, then no dice.
    elif not user.is_active:
        error_message = ('The user account for <tt>%s</tt> has been disabled.' %
                         user.username)
    if error_message:
        return render_html_template('login.html', request,
                                    {'error_message': error_message,
                                     'redirect_to': form.get('goto', None)},
                                    context_instance=RequestContext(request))

    # Otherwise, we're good to go, so log the user in.
    auth.login(request, user)

    # hack to try to pass them back to http land
    goto = request.REQUEST.get('goto',reverse('aenclave-home'))
    
    # hack to prevent infinite loop.
    if goto == '':
        goto = reverse('aenclave-home')

    if goto.startswith('https'):
        goto = goto.replace('^https','http')

    return HttpResponseRedirect(goto)

def logout(request):
    auth.logout(request)
    return HttpResponseRedirect(request.GET.get('goto',reverse('aenclave-home')))

#---------------------------------- Queuing ----------------------------------#

@permission_required('aenclave.can_queue', 'Queue Song')
def queue_songs(request):
    form = request.REQUEST
    # Get the selected songs.
    songs = get_song_list(form)
    # Queue the songs.
    Controller().add_songs(songs)
    if 'getupdate' in form:
        # Send back an updated playlist status.
        return json_control_update(request)
    else:
        # Redirect to the channels page.
        return HttpResponseRedirect(reverse('aenclave-default-channel'))

@permission_required('aenclave.can_queue', 'Dequeue Song')
def dequeue_songs(request):
    form = request.POST
    # Get the selected indices.
    indices = get_int_list(form, 'indices')
    # Dequeue the songs.
    Controller().remove_songs(indices)
    # Redirect to the channels page.
    return HttpResponseRedirect(reverse('aenclave-default-channel'))

#------------------------------- Normal Search -------------------------------#

def normal_search(request):
    form = request.GET
    # Get the query.
    query_string = form.get('q','')
    query_words = query_string.split()
    # If no query was provided, then yield no results.
    if not query_words: queryset,query_string = (),''
    # Otherwise, get matching songs.
    else:
        full_query = Q()
        for word in query_words:
            word_query = Q()
            for field in ('title', 'album', 'artist'):
                # WTF Each word may appear in any field, so we use OR here.
                word_query |= Qu(field, 'icontains', word)
            # WTF Each match must contain every word, so we use AND here.
            full_query &= word_query
        queryset = Song.visibles.filter(full_query)
    # If we're feeling lucky, queue a random result.
    if form.get('lucky', False):
        if queryset is ():
            queryset = Song.visibles
        song = queryset.order_by('?')[0]
        Controller().add_song(song)
        # Redirect to the channels page.
        return HttpResponseRedirect(reverse('aenclave-default-channel'))
    # Otherwise, display the search results.
    return render_html_template('search_results.html', request,
                                {'song_list':queryset,
                                 'search_query':query_string},
                                context_instance=RequestContext(request))

#------------------------------- Filter Search -------------------------------#

def _build_filter_tree(form, prefix):
    """_build_filter_tree(form, prefix) -- returns (tree,total,errors)

    Builds the subtree rooted at the prefix from the form.
      tree -- filter tree structure
      total -- total number of criteria
      errors -- list of errors
    Returns (None,0,None) if there is no subtree rooted at the prefix.  Raises
    a KeyError if the tree is malformed."""
    try: kind = form[prefix]
    except KeyError: return None, 0, None
    if kind in ('or','and','nor','nand'):
        prefix += '_'
        subtrees, total, errors = [], 0, []
        for i in itertools.count():
            subprefix = prefix + str(i)
            subtree, subtotal, suberr = _build_filter_tree(form, subprefix)
            if subtree is None: break  # There are no more subtrees.
            elif subtotal == 0: continue  # Skip this empty subtree.
            subtrees.append(subtree)
            total += subtotal
            errors.extend(suberr)
        return ('sub', kind, subtrees), total, errors
    else:
        rule = form[prefix+'_r']
        if kind in ('title','album','artist'):
            string = get_unicode(form, prefix+'_f0')
            # If the kind is blank, then ignore the criterion.
            if not string: return (), 0, ()
            # Validate the rule.
            if rule not in ('in','notin','start','notstart','end','notend',
                            'is','notis'):
                raise KeyError('bad string rule: %r' % rule)
            return (kind, rule, string), 1, ()
        elif kind in ('time','track','play_count'):
            errors = []
            # Get f0 and, if needed, f1.
            try:
                if kind == 'time': f0 = parse_time(form[prefix+'_f0'])
                else: f0 = parse_integer(form[prefix+'_f0'])
            except ValueError, err: errors.append(str(err))
            if rule in ('inside','outside'):
                try:
                    if kind == 'time': f1 = parse_time(form[prefix+'_f1'])
                    else: f1 = parse_integer(form[prefix+'_f1'])
                except ValueError, err: errors.append(str(err))
            # Validate the rule.
            if errors: return (), 1, errors
            elif rule in ('inside', 'outside'):
                return (kind, rule, (f0, f1)), 1, ()
            elif rule in ('is','notis','lte','gte'):
                return (kind, rule, f0), 1, ()
            else: raise KeyError('bad integer rule: %r' % rule)
        elif kind in ('date_added','last_queued'):
            if rule in ('last','nolast'):
                # Validate the number.  This is human provided, so give an
                # error string if it's bad.
                try: number = parse_integer(form[prefix+'_f0'])
                except ValueError, err: return (), 1, (str(err),)
                # Validate the unit.  This is provided by the form, so raise
                # a KeyError if it's bad.
                unit = form[prefix+'_f1']
                if unit not in ('hour','day','week','month','year'):
                    raise KeyError('bad date unit: %r' % unit)
                return (kind, rule, (number, unit)), 1, ()
            else:
                errors = []
                # Get f0 and, if needed, f1.
                try: f0 = parse_date(form[prefix+'_f0'])
                except ValueError, err: errors.append(str(err))
                if rule in ('inside','outside'):
                    try: f1 = parse_date(form[prefix+'_f1'])
                    except ValueError, err: errors.append(str(err))
                # Validate the rule.
                if errors: return (), 1, errors
                elif rule in ('before','after'):
                    return (kind, rule, f0), 1, ()
                elif rule in ('inside','outside'):
                    return (kind, rule, (f0, f1)), 1, ()
                else: raise KeyError('bad date rule: %r' % rule)
        else: raise KeyError('bad kind: %r' % kind)

def _build_filter_query(tree):
    kind, rule, data = tree
    if kind == 'sub':
        is_or = rule in ('or','nor')
        query = Q()
        for subtree in data:
            subquery = _build_filter_query(subtree)
            if is_or: query |= subquery
            else: query &= subquery
        if rule in ('nor','nand'): query = ~Q(query)
        return query
    elif kind in ('title','album','artist'):
        negate = rule.startswith('not')
        if negate: rule = rule[3:]
        if rule == 'in': query = Qu(kind, 'icontains', data)
        elif rule == 'start': query = Qu(kind, 'istartswith', data)
        elif rule == 'end': query = Qu(kind, 'iendswith', data)
        elif rule == 'is': query = Qu(kind, 'iexact', data)
        if negate: return ~Q(query)
        else: return query
    elif kind in ('time','track','play_count'):
        if rule in ('lte','gte'): return Qu(kind, rule, data)
        elif rule == 'is': return Qu(kind, 'exact', data)
        elif rule == 'notis': return ~Q(Qu(kind, 'exact', data))
        elif rule == 'inside': return Qu(kind, 'range', data)
        elif rule == 'outside':
            return Qu(kind, 'lt', data[0]) | Qu(kind, 'gt', data[1])
    elif kind in ('date_added','last_queued'):
        if rule in ('last','nolast'):
            number, unit = data
            if unit == 'hour': delta = datetime.timedelta(0,3600)
            elif unit == 'day': delta = datetime.timedelta(1)
            elif unit == 'week': delta = datetime.timedelta(7)
            elif unit == 'month': delta = datetime.timedelta(30.43685)
            elif unit == 'year': delta = datetime.timedelta(365.24220)
            date = datetime.datetime.now() - number * delta
            if rule == 'last': return Qu(kind, 'gte', date)
            else: return Qu(kind, 'lt', date)
        else:
            if rule == 'before': return Qu(kind, 'lt', data)
            elif rule == 'after': return Qu(kind, 'gt', data)
            elif rule == 'inside': return Qu(kind, 'range', data)
            elif rule == 'outside':
                return Qu(kind, 'lt', data[0]) | Qu(kind, 'gt', data[1])

def filter_search(request):
    try: tree,total,errors = _build_filter_tree(request.GET, 'k')
    except KeyError, err: return html_error(request)
    if errors: raise Http404  # TODO error (human's fault)
    if total == 0: queryset = ()
    else: queryset = Song.visibles.filter(_build_filter_query(tree))
    return render_html_template('filter_results.html', request,
                                {'song_list':queryset,
                                 'criterion_count':total},
                              context_instance=RequestContext(request))

#--------------------------------- Browsing ----------------------------------#

def browse_index(request):
    # WTF Using .count() seems to get the wrong answer -- I think it's not
    #     playing nice with .distinct() (as of Django SVN revision 6000).  Not
    #     sure if that's Django's fault or SQLite's fault, but it'd be nice to
    #     figure it out, since using len() is the Wrong Thing here (much less
    #     memory efficient).
    total_albums = len(Song.visibles.values('album').distinct())
    total_artists = len(Song.visibles.values('artist').distinct())
    return render_html_template('browse_index.html', request,
                                {'total_albums': total_albums,
                                 'total_artists': total_artists},
                                context_instance=RequestContext(request))

def browse_albums(request, letter):
    if not letter.isalpha():
        letter = '#'
        matches = Song.visibles.filter(album__regex=r'^[^a-zA-Z]').order_by()
    else:
        letter = letter.upper()
        matches = Song.visibles.filter(album__istartswith=letter).order_by()
    albums = [item['album'] for item in matches.values('album').distinct()]
    return render_html_template('browse_albums.html', request,
                                {'letter': letter, 'albums': albums},
                                context_instance=RequestContext(request))

def browse_artists(request, letter):
    if not letter.isalpha():
        letter = '#'
        matches = Song.visibles.filter(artist__regex=r'^[^a-zA-Z]').order_by()
    else:
        letter = letter.upper()
        matches = Song.visibles.filter(artist__istartswith=letter).order_by()
    artists = [item['artist'] for item in matches.values('artist').distinct()]
    return render_html_template('browse_artists.html', request,
                                {'letter': letter, 'artists': artists},
                                context_instance=RequestContext(request))

def view_album(request, album_name):
    album_songs = Song.visibles.filter(album__iexact=album_name)
    return render_html_template('album_detail.html', request,
                                {'album_name': album_name,
                                 'song_list': album_songs},
                                context_instance=RequestContext(request))

def view_artist(request, artist_name):
    artist_songs = Song.visibles.filter(artist__iexact=artist_name)
    return render_html_template('artist_detail.html', request,
                                {'artist_name': artist_name,
                                 'song_list': artist_songs},
                                context_instance=RequestContext(request))

def list_songs(request):
    songs = get_song_list(request.REQUEST)
    return render_html_template('list_songs.html', request,
                                {'song_list': songs},
                                context_instance=RequestContext(request))

#--------------------------------- Channels ----------------------------------#

def channel_detail(request, channel_id=1):
    try: channel = Channel.objects.get(pk=channel_id)
    except Channel.DoesNotExist: raise Http404
    ctrl = channel.controller()
    current_song = ctrl.get_current_song()
    return render_html_template('channels.html', request,
                                {'channel': channel,
                                 'current_song': current_song,
                                 'song_list': ctrl.get_queue_songs(),
                                 'force_actions_bar': True,
                                 'elapsed_time': ctrl.get_elapsed_time(),
                                 'skipping': (current_song == 'DQ'),
                                 'playing': ctrl.is_playing(),
                                 'no_queuing': True},
                                context_instance=RequestContext(request))

def channel_reorder(request, channel_id=1):
    try: channel = Channel.objects.get(pk=channel_id)
    except Channel.DoesNotExist: raise Http404
    ctrl = channel.controller()
    form = request.POST
    songs = get_song_list(form)
    # FIXME(rnk): This is the stupidest, most non-threadsafe way possible to do
    #             this.  I should probably be shot for it.  Please, for the
    #             love of all that is holy, consider fixing this.
    ctrl.clear_queued_songs()
    ctrl.add_songs(songs)

#----------------------------- Playlist Viewing ------------------------------#

def all_playlists(request):
    return render_html_template('playlist_list.html', request,
                                {'playlist_list': Playlist.objects.all()},
                                context_instance=RequestContext(request))

def playlist_detail(request, playlist_id):
    try: playlist = Playlist.objects.get(pk=playlist_id)
    except Playlist.DoesNotExist: raise Http404
    can_cede = playlist.can_cede(request.user)
    # This order_by uses PlaylistEntry's Meta ordering, which is position.
    songs = playlist.songs.order_by('playlistentry')
    return render_html_template('playlist_detail.html', request,
                                {'playlist': playlist,
                                 'song_list': songs,
                                 'force_actions_bar': can_cede,
                                 'allow_cede': can_cede,
                                 'allow_edit': playlist.can_edit(request.user)},
                                context_instance=RequestContext(request))

def user_playlists(request, username):
    plists = Playlist.objects.filter(owner__username=username)
    return render_html_template('playlist_list.html', request,
                                {'playlist_list': plists},
                                context_instance=RequestContext(request))

#----------------------------- Playlist Editing ------------------------------#

@permission_required('aenclave.add_playlist', 'Make Playlist')
def create_playlist(request):
    form = request.POST
    name = get_unicode(form, 'name')
    if not name:
        return html_error(request,'No name provided.')  # TODO better feedback
    # Make sure that we can create the playlist.
    # WTF In fact, we can't use playlist.songs until playlist has been saved.
    playlist = Playlist(name=name, owner=request.user)
    try:
        playlist.save()  # BTW This will fail if (name,owner) is not unique.
    except:
        return html_error(request, 'A playlist of that name already exists.')
    #    return error(request,'Nonunique name/owner.')  # TODO better feedback
    # Add the specified songs to the playlist.
    songs = get_song_list(form)
    playlist.set_songs(songs)
    playlist.save()
    # Redirect to the detail page for the newly created playlist.
    return HttpResponseRedirect(playlist.get_absolute_url())

@permission_required('aenclave.change_playlist', 'Add Songs')
def add_to_playlist(request):
    # Get the playlist to be added to.
    form = request.POST
    try: playlist = Playlist.objects.get(pk=get_integer(form, 'pid'))
    except Playlist.DoesNotExist:
        return html_error(request, 'That playlist does not exist.',
                          'Add Songs')
    # Make sure the user is allowed to edit this playlist.
    if not playlist.can_edit(request.user):
        return html_error(request, 'You lack permission to edit this'
                          ' playlist.', 'Add Songs')
    # Add the songs and redirect to the detail page for this playlist.
    songs = get_song_list(form)
    playlist.append_songs(songs)
    return HttpResponseRedirect(playlist.get_absolute_url())

@permission_required('aenclave.change_playlist', 'Remove Songs')
def remove_from_playlist(request):
    # Get the playlist to be removed from.
    form = request.POST
    try: playlist = Playlist.objects.get(pk=get_integer(form, 'pid'))
    except Playlist.DoesNotExist:
        return html_error(request, 'That playlist does not exist.',
                          'Remove Songs')
    # Make sure the user is allowed to edit this playlist.
    if not playlist.can_edit(request.user):
        return html_error(request, 'You lack permission to edit this'
                          ' playlist.', 'Remove Songs')
    # Remove the songs and redirect to the detail page for this playlist.
    songs = get_song_list(form)
    PlaylistEntry.objects.filter(song__in=songs).delete()
    return HttpResponseRedirect(playlist.get_absolute_url())

@permission_required('aenclave.delete_playlist', 'Delete Playlist')
def delete_playlist(request):
    # Get the playlist to be deleted.
    form = request.POST
    try: playlist = Playlist.objects.get(pk=get_integer(form, 'pid'))
    except Playlist.DoesNotExist:
        return html_error(request, 'That playlist does not exist.',
                          'Delete Playlist')
    # Make sure the user is allowed to delete the playlist.
    if not playlist.can_cede(request.user):
        return html_error(request, 'You may only delete your own playlists.',
                          'Delete Playlist')
    # Delete the playlist and redirect to the user's playlists page.
    playlist.delete()
    return HttpResponseRedirect(reverse('aenclave-user-playlist',
                                        args=[request.user.username]))

@permission_required('aenclave.change_playlist', 'Edit Playlist')
def edit_playlist(request, playlist_id):
    # Get the playlist.
    form = request.POST
    try: playlist = Playlist.objects.get(pk=playlist_id)
    except Playlist.DoesNotExist:
        return json_error('That playlist does not exist.')
    # Check that they can edit it.
    if not playlist.can_edit(request.user):
        return json_error('You are not authorized to edit this playlist.')
    songs = get_song_list(form)
    if songs:
        playlist.set_songs(songs)
        playlist.save()
    return json_success('Successfully edited "%s".' % playlist.name)

#---------------------------------- Upload -----------------------------------#

@permission_required_redirect('aenclave.add_song', 'goto')
def upload_http(request):
    # Nab the file and make sure it's legit.
    audio = request.FILES.get('audio', None)
    if audio is None:
        return html_error(request, 'No file was uploaded.', 'HTTP Upload')

    try:
        song, audio = processing.process_song(audio.name, audio)
    except processing.BadContent:
        return html_error(request, "You may only upload audio files.",
                          "HTTP Upload")

    return render_html_template('upload_http.html', request,
                                {'song_list': [song],
                                 'sketchy_upload': audio.info.sketchy},
                                context_instance=RequestContext(request))

@permission_required_redirect('aenclave.add_song', 'goto')
def upload_sftp(request):
    song_list = []
    sketchy = False
    sftp_upload_dir = enc_settings.AENCLAVE_SFTP_UPLOAD_DIR

    # Figure out available MP3's in SFTP upload DIR
    for root, dirs, files in os.walk(sftp_upload_dir):
        for filename in files:
            if processing.valid_song(filename):
                full_path = root + '/' + filename

                content = File(open(full_path, 'r'))
    
                song, audio = processing.process_song(full_path, content)
                
                song_list.append(song)

                if audio.info.sketchy:
                    sketchy = True

                #remove the file from the sftp-upload directory
                os.unlink(full_path)

    return render_html_template('upload_sftp.html', request,
                                {'song_list': song_list,
                                 'sketchy_upload': sketchy},
                                context_instance=RequestContext(request))

@permission_required_redirect('aenclave.add_song', 'goto')
def upload_http_fancy(request):

    # HTTPS is way slowed down..
    if request.is_secure():
        return HttpResponseRedirect("http://" + request.get_host() +
                                    reverse("aenclave-http-upload-fancy"))

    file_types = map(lambda s: "*.%s" % s, enc_settings.SUPPORTED_AUDIO)
    return render_html_template('upload_http_fancy.html', request,
                                {'song_list': [],
                                 'show_songlist': True,
                                 'file_types': file_types,
                                 'force_actions_bar':True},
                                context_instance=RequestContext(request))

def upload_http_fancy_receiver(request):

    # Centipedes, in my request headers?
    # Yes! This view receives its session key in the POST, because
    # the multiple-file-uploader uses Flash to send the request,
    # and the best Flash can do is grab our cookies from javascript
    # and send them in the POST.

    session_key = request.REQUEST.get(settings.SESSION_COOKIE_NAME,None)
    if not session_key:
        raise Http404()

    # This is how SessionMiddleware does it.
    session_engine = __import__(settings.SESSION_ENGINE, {}, {}, [''])
    try:
        request.session = session_engine.SessionStore(session_key)
    except Exception, e:
        return html_error(e)

    # SWFUpload will show an error to the user if this happens.
    if not request.user.is_authenticated():
        return HttpResponseForbidden()

    audio = None
    # The key is generally 'Filedata' but this is just easier.
    for k,f in request.FILES.items():
        audio = f

    # SWFUpload does not properly fill out the song's mimetype, so
    # just use the extension.
    if audio is None:
        return html_error(request, 'No file was uploaded.', 'HTTP Upload')
    elif not processing.valid_song(audio.name):
        return html_error(request, 'You may only upload MP3 files.',
                              'HTTP Upload')
    # Save the song into the database -- we'll fix the tags in a moment.
    song, audio = processing.process_song(audio.name, audio)
    
    return render_html_template('songlist_song_row.html', request,
                                {'song': song},
                                context_instance=RequestContext(request))

#-------------------------------- DL Requests --------------------------------#

def dl(request):
    """Serve songs to the user, either as a zip archive or a single file."""
    # Use REQUEST to allow GET and POST selections.
    songs = get_song_list(request.REQUEST)
    if not songs:
        # TODO(rnk): Better error handling.
        raise Exception("No ids were provided to dl.")
    elif len(songs) == 1:
        return send_song(songs[0])
    else:
        return send_songs(songs)

class StreamingHttpResponse(HttpResponse):

    """This class exists to bypass middleware that uses .content.

    See Django bug #6027: http://code.djangoproject.com/ticket/6027

    We override content to be a no-op, so that GzipMiddleware doesn't exhaust
    the FileWrapper generator, which reads the file incrementally.
    """

    def _get_content(self):
        return ""

    def _set_content(self, value):
        pass

    content = property(_get_content, _set_content)

def send_song(song):
    """Return an HttpResponse that will serve an MP3 from disk.

    This happens without reading the whole MP3 in as a string.
    """
    fd = file(song.audio.path)
    wrapper = FileWrapper(fd)
    response = StreamingHttpResponse(wrapper, content_type='audio/mpeg')
    # BTW nice_filename is guaranteed not to have any backslashes or quotes in
    #     it, so we don't need to escape anything.
    response['Content-Disposition'] = ('attachment; filename="%s"' %
                                       song.nice_filename())
    response['Content-Length'] = os.path.getsize(song.audio.path)
    return response

def send_songs(songs):
    """Serve a zip archive of the chosen songs."""
    # Make an archive name with a timestamp of the form YYYY-MM-DD_HH-MM-SS.
    timestamp = '%i-%i-%i_%i-%i-%i' % datetime.datetime.today().timetuple()[:6]
    archive_name = 'nr_dl_%s.zip' % timestamp
    filenames = []
    for song in songs:
        # WTF Use str() here because the filename apparently *cannot* be a
        #     unicode string, or zipfile flips out.
        filenames.append((song.audio.path, str(song.nice_filename())))
    return render_zip(archive_name, filenames)

def render_zip(archive_name, filenames):
    """Serve a zip archive containing all of the named files.

    archive_name -- The name to give the zip archive when it is served.
    filenames -- A list of tuples of the form (path, newname).

    This creates a temporary zip archive on disk which is cleaned up after its
    references are garbage collected.

    TODO(rnk): What would be really hot (lapnap does this) would be to find a
               way to write the zip archive to the HTTP stream instead of a
               temp file.  This would prevent us from having a usable download
               progress bar, but the download would start right away.
    """
    # Make a temporary zip archive.
    tmp_file = tempfile.TemporaryFile(mode='w+b')
    # Use ZIP_STORED to disable compression because mp3s are already well
    # compressed.
    archive = zipfile.ZipFile(tmp_file, 'w', zipfile.ZIP_STORED)
    # Write songs to zip archive.
    for (path, newname) in filenames:
        archive.write(path, newname)
    archive.close()
    filesize = tmp_file.tell()
    # Serve zip archive.
    wrapper = FileWrapper(tmp_file)
    # Using StreamingHttpResponse tries to avoid gzip middleware from fucking
    # everything up.
    response = StreamingHttpResponse(wrapper, content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename=%s' % archive_name
    response['Content-Length'] = filesize
    tmp_file.seek(0)
    return response

#--------------------------------- Roulette ----------------------------------#

def roulette(request):
    # Choose six songs randomly.
    queryset = Song.visibles.order_by('?')[:6]
    return render_html_template('roulette.html', request,
                                {'song_list': queryset},
                                context_instance=RequestContext(request))

#------------------------------- Delete Requests -----------------------------#

@permission_required('aenclave.delete_song', 'Delete Song')
def delete_songs(request):
    form = request.POST

    # The person must be authenticated
    if not request.user.is_authenticated():
        raise Http404()

    if not request.user.is_staff:
        return submit_delete_requests(request)

    subject = 'Song Deletion by ' + request.user.username
    message = 'The following files were deleted by ' + request.user.username + ':\n'

    song_list = []

    songs = get_song_list(form)
    for song in songs:
        song_string = (' * %(id)s - %(artist)s - %(album)s - %(title)s\n' %
                       {'id': str(song.id),
                        'artist': song.artist,
                        'album': song.album,
                        'title': song.title})
        message += song_string
        song_list.append(song)

    mail_admins(subject,message,False)

    # Do the dirty deed.
    for song in songs:
        song.delete()

    return render_html_template('delete_performed.html', request,
                                {},
                                context_instance=RequestContext(request))

@permission_required('aenclave.request_delete_song', 'Request Delete')
def submit_delete_requests(request):
    form = request.POST
    # Add the songs and redirect to the detail page for this playlist.

    message = 'The following delete request(s) were filed'
    if request.user.is_authenticated():
        subject = 'Delete Request from ' + request.user.username
        message += ' by ' + request.user.username + ':\n'
    else:
        subject = 'Delete Request from Anonymous'
        message += ' by an unregistered user:\n'

    song_list = []

    songs = get_song_list(form)
    for song in songs:
        song_string = (' * %(id)s - %(artist)s - %(album)s - %(title)s\n' %
                       {'id': str(song.id),
                        'artist': song.artist,
                        'album': song.album,
                        'title': song.title})
        message += song_string
        song_list.append(song)

    uri = "%s?ids=%s" % (request.build_absolute_uri(reverse("aenclave-list")), '+'.join([str(song.id) for song in songs]))
    message += '\nView these songs here: %s\n' % uri

    mail_admins(subject,message,False)

    return render_html_template('delete_requested.html', request,
                                {'song_list': song_list},
                                context_instance=RequestContext(request))


#--------------------------------- XML Hooks ---------------------------------#

@permission_required_xml('aenclave.can_queue')
def xml_queue(request):
    form = request.POST
    # Get the selected songs.
    songs = get_song_list(form)
    # Queue the songs.
    try: Controller().add_songs(songs)
    except ControlError, err: return xml_error(str(err))
    else: return simple_xml_response('success')

@permission_required_xml('aenclave.can_queue')
def xml_dequeue(request):
    form = request.POST
    # Get the selected songs.
    indices = get_int_list(form, 'indices')
    # Dequeue the songs.
    try: Controller().remove_songs(indices)
    except ControlError, err: return xml_error(str(err))
    else: return simple_xml_response('success')

@permission_required_xml('aenclave.can_control')
def xml_control(request):
    form = request.POST
    action = form.get('action','')
    try:
        if action == 'play': Controller().unpause()
        elif action == 'pause': Controller().pause()
        elif action == 'skip': Controller().skip()
        elif action == 'shuffle': Controller().shuffle()
        else: return xml_error('invalid action: ' + action)
    except ControlError, err: return xml_error(str(err))
    else: return simple_xml_response('success')

def xml_update(request):
    form = request.POST
    channel_id = get_integer(form, 'channel', 1)
    try: channel = Channel.objects.get(pk=channel_id)
    except Channel.DoesNotExist:
        return xml_error('invalid channel id: ' + repr(channel_id))
    timestamp = get_integer(form, 'timestamp', None)
    if timestamp is None: return xml_error('invalid timestamp')
    elif timestamp >= channel.last_touched_timestamp():  # up-to-date timestamp
        try:
            ctrl = channel.controller()
            if not ctrl.is_playing: return simple_xml_response('continue')
            elapsed_time = ctrl.get_elapsed_time()
            total_time = ctrl.get_current_song().time
            return render_xml_to_response('update.xml',
                                          {'elapsed_time':elapsed_time,
                                           'total_time':total_time})
        except ControlError, err: return xml_error(str(err))
    else: return simple_xml_response('reload')  # old timestamp

@permission_required_xml('aenclave.change_song')
def xml_edit(request):
    if not request.user.is_authenticated():
        return xml_error('user not logged in')
    form = request.POST
    try: song = Song.objects.get(pk=int(form.get('id','')))
    except (ValueError, TypeError, Song.DoesNotExist), err:
        return xml_error(str(err))
    audio = MP3(song.audio.path, ID3=EasyID3)
    # Update title.
    title = get_unicode(form, 'title')
    if title:  # Disallow empty titles.
        song.title = title
        audio['title'] = title
    # Update album.
    album = get_unicode(form, 'album')
    if album is not None:
        song.album = album
        audio['album'] = album
    # Update artist.
    artist = get_unicode(form, 'artist')
    if artist is not None:
        song.artist = artist
        audio['artist'] = artist
    # Update track number.
    if form.get('track', None) == '': song.track = 0
    else:
        track = get_integer(form, 'track')
        if track is not None and 0 <= track < 999:
            song.track = track
            audio['tracknumber'] = unicode(track)
    # Save and report success.
    song.save()
    audio.save()
    return render_xml_to_response('done_editing.xml', {'song':song})

def xml_user_playlists(request):
    if request.user.is_authenticated():
        query = Q(owner=request.user) | Q(group__in=request.user.groups.all())
        playlists = Playlist.objects.filter(query)
    else: playlists = Playlist.objects.none()
    return render_xml_to_response('playlist_list.xml',
                                  {'playlist_list':playlists})

#-------------------------------- JSON Hooks ---------------------------------#

@permission_required_json('aenclave.can_control')
def json_control(request):
    action = request.POST.get('action','')
    try:
        if action == 'play': Controller().unpause()
        elif action == 'pause': Controller().pause()
        elif action == 'skip': Controller().skip()
        elif action == 'shuffle': Controller().shuffle()
        else: return json_error('invalid action: ' + action)
    except ControlError, err:
        return json_error(str(err))
    else:
        # Control succeeded, get the current playlist state and send that back.
        return json_control_update(request)

def playlist_info_json(channel_id=1):
    channel = Channel.objects.get(pk=channel_id)
    data = {}
    ctrl = channel.controller()
    songs = ctrl.get_queue_songs()
    current_song = ctrl.get_current_song()
    if current_song:
        songs.insert(0, current_song)
    # Provide data for the first three songs.
    data['songs'] = []
    for song in songs:
        if len(data['songs']) >= 3:
            break
        if song == 'DQ':
            # Skip dequeue noises.
            continue
        # Strip the metadata of extra spaces, or we'll truncate too much.
        info_str = '%s - %s' % (song.title.strip(), song.artist.strip())
        if len(info_str) > 30:
            info_str = info_str[:27] + '...'
        data['songs'].append(info_str)
    data['elapsed_time'] = ctrl.get_elapsed_time()
    data['song_duration'] = songs[0].time if songs and songs[0] != 'DQ' else 0
    data['playlist_length'] = len(songs)
    data['playlist_duration'] = ctrl.get_queue_duration()
    data['playing'] = ctrl.is_playing()
    return cjson.encode(data)

def json_control_update(request, channel_id=1):
    try:
        playlist_info = playlist_info_json(channel_id)
    except ControlError, err:
        return json_error(str(err))
    else:
        return render_json_response(playlist_info)

@permission_required_json('aenclave.change_song')
def json_edit(request):
    if not request.user.is_authenticated():
        return json_error('user not logged in')
    form = request.POST

    try: song = Song.objects.get(pk=int(form.get('id','')))
    except (ValueError, TypeError, Song.DoesNotExist), err:
        return json_error(str(err))
    audio = MP3(song.audio.path, ID3=EasyID3)
    # Update title.
    title = get_unicode(form, 'title')
    if title:  # Disallow empty titles.
        song.title = title
        audio['title'] = title
    # Update album.
    album = get_unicode(form, 'album')
    if album is not None:
        song.album = album
        audio['album'] = album
    # Update artist.
    artist = get_unicode(form, 'artist')
    if artist is not None:
        song.artist = artist
        audio['artist'] = artist
    # Update track number.
    if form.get('track', None) == '':
        song.track = 0
    else:
        track = get_integer(form, 'track')
        if track is not None and 0 <= track < 999:
            song.track = track
            audio['tracknumber'] = unicode(track)
    # Save and report success.
    song.save()
    audio.save()
    return render_json_template('done_editing.json', {'song':song})

def json_user_playlists(request):
    if request.user.is_authenticated():
        query = Q(owner=request.user) | Q(group__in=request.user.groups.all())
        playlists = Playlist.objects.filter(query)
    else: playlists = Playlist.objects.none()
    return render_json_template('playlist_list.json',
                                {'playlist_list':playlists})

def json_email_song_link(request):
    form = request.POST
    email_address = form.get('email', '')
    if not re.match("^[-_a-zA-Z0-9.]+@[-_a-zA-Z0-9.]+$", email_address):
        return json_error("Invalid email address.")
    songs = get_song_list(form)
    if songs:
        message = ["From: Audio Enclave <%s>\r\n" %
                   settings.DEFAULT_FROM_EMAIL,
                   "To: %s\r\n\r\n" % email_address,
                   "Someone sent you a link to the following "]
        if len(songs) == 1:
            message.append("song:\n\n")
            subject = songs[0].title
        else:
            message.append("songs:\n\n")
            subject = "%d songs" % len(songs)
        for song in songs:
            message.extend((song.title, "\n",
                            song.artist, "\n",
                            song.album, "\n",
                            settings.HOST_NAME +
                            song.get_absolute_url(), "\n\n"))
        # Ship it!
        send_mail("Link to " + subject, "".join(message),
                  settings.DEFAULT_FROM_EMAIL, (email_address,))
        return json_success("An email has been sent to %s." % email_address)
    else: return json_error("No matching songs were found.")

#=============================================================================#
