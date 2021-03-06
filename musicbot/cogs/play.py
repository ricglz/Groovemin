'''Play Cog module'''
from dataclasses import dataclass
from random import shuffle
from typing import Optional
import asyncio
import logging
import re
import time
import traceback

import discord
from discord import Member
from discord.ext.commands import Context
from dislash import command, Option, OptionType

from ..exceptions import CommandError, PermissionsError, SpotifyError
from ..permissions import Permissions
from ..player import MusicPlayer
from ..spotify import Spotify
from ..utils import _func_, fixg, ftimedelta
from .custom_cog import CustomCog

log = logging.getLogger(__name__)

LINKS_REGEX = '((http(s)*:[/][/]|www.)([a-z]|[A-Z]|[0-9]|[/.]|[~])*)'
PLAYLIST_REGEX = r'watch\?v=.+&(list=[^&]+)'

def parse_song_url(song_query: str):
    '''Given a song query it sanitizes it, in case that is a url'''
    song_url = song_query.strip('<>')
    # Make sure forward slashes work properly in search queries
    pattern = re.compile(LINKS_REGEX)
    match_url = pattern.match(song_url)
    song_url = song_url.replace('/', '%2F') if match_url is None else song_url

    # Rewrite YouTube playlist URLs if the wrong URL type is given
    matches = re.search(PLAYLIST_REGEX, song_url)
    groups = matches.groups() if matches is not None else []
    song_url = "https://www.youtube.com/playlist?" + groups[0] if len(groups) > 0 else song_url
    return song_url

def parser_song_url_spotify(song_url: str):
    '''Sanitizes a song url to be used in the case that is a spotify url'''
    if 'open.spotify.com' in song_url:
        regex_result = re.sub(r'(http[s]?:\/\/)?(open.spotify.com)\/', '', song_url)
        regex_result = regex_result.replace('/', ':')
        song_url = 'spotify:' + regex_result
        song_url = re.sub(r'\?.*', '', song_url)
    return song_url

@dataclass
class PlayRequirements:
    '''Helper class to contain the required arguments for play functions'''
    author: Member
    channel: object
    permissions: Permissions
    player: MusicPlayer
    shuffle: bool
    song_url: str

class PlayCog(CustomCog):
    '''Cog class in charge of the main play command'''
    def __init__(self, bot):
        super().__init__(bot)
        self.spotify = None
        if self.config._spotify:
            try:
                self.spotify = Spotify(
                    self.config.spotify_clientid,
                    self.config.spotify_clientsecret,
                    aiosession=self.bot.aiosession,
                    loop=self.bot.loop
                )
                if not self.spotify.token:
                    log.warning('Spotify did not provide us with a token. Disabling.')
                    self.config._spotify = False
                else:
                    log.info('Authenticated with Spotify successfully using client ID and secret.')
            except SpotifyError as err:
                log.warning(
                    'There was a problem initializing the connection to Spotify. Is your client '
                    'ID and secret correct? Details: %s. Continuing anyway in 5 seconds...',
                    err
                )
                self.config._spotify = False
                time.sleep(5)

    async def determine_type(self, player, song_url: str):
        '''Try to determine entry type, if _type is playlist then there should be entries'''
        while True:
            try:
                info = await self.downloader.extract_info(
                    player.playlist.loop,
                    song_url,
                    download=False,
                    process=False
                )

                # If there is an exception arise when processing we go on and
                # let extract_info down the line report it because info might
                # be a playlist and thing that's broke it might be individual
                # entry
                try:
                    info_process = await self.downloader.extract_info(
                        player.playlist.loop,
                        song_url,
                        download=False
                    )
                except:
                    info_process = None

                if info_process is None or info is None:
                    break

                is_not_playlist = info_process.get('_type', None) != 'playlist'
                has_entries = 'entries' in info
                is_search_url = info.get('url', '').startswith('ytsearch')
                if is_not_playlist or has_entries or is_search_url:
                    break
                use_url = info_process.get('webpage_url', None) or info_process.get('url', None)
                if use_url == song_url:
                    log.warning(
                        'Determined incorrect entry type, but suggested url is the same. Help.'
                    )
                    # If we break here it will break things down the line
                    # and give "This is a playlist" exception as a result
                    break

                log.debug(
                    'Assumed url "%s" was a single entry, was actually a playlist', song_url)
                log.debug('Using "%s" instead', use_url)
                song_url = use_url

            except Exception as e:
                if 'unknown url type' in str(e):
                    # It's probably not actually an extractor
                    song_url = song_url.replace(':', '')
                    info = await self.downloader.extract_info(
                        player.playlist.loop,
                        song_url,
                        download=False,
                        process=False
                    )
                else:
                    raise CommandError(e, expire_in=30) from e

        return info, song_url

    def _check_for_permissions(self, permissions, player, author):
        if permissions.max_songs and \
           player.playlist.count_for_user(author) >= permissions.max_songs:
            error_msg = self.str.get(
                'cmd-play-limit',
                'You have reached your enqueued song limit ({0})'
            ).format(permissions.max_songs)
            raise PermissionsError(error_msg, expire_in=30)

        if player.karaoke_mode and not permissions.bypass_karaoke_mode:
            error_msg = self.str.get(
                'karaoke-enabled',
                'Karaoke mode is enabled, please try again when its disabled!'
            )
            raise PermissionsError(error_msg, expire_in=30)

    def _check_valid_info(self, info, permissions):
        if not info:
            error_msg = self.str.get(
                'cmd-play-noinfo',
                'That video cannot be played. Try using the {0}stream command.'
            ).format(self.config.command_prefix)
            raise CommandError(error_msg, expire_in=30)

        if info.get('extractor', '') not in permissions.extractors and permissions.extractors:
            error_msg = self.str.get(
                'cmd-play-badextractor',
                'You do not have permission to play media from this service.'
            )
            raise PermissionsError(error_msg, expire_in=30)

    async def _search_song(self, player, song_url: str, channel):
        '''
        Abstract the search handling away from the user our ytdl options allow
        us to use search strings as input urls.
        '''
        info = await self.downloader.extract_info(
            player.playlist.loop,
            song_url,
            download=False,
            process=True,
            on_error=lambda e: asyncio.ensure_future(
                self.safe_send_message(channel, "```\n%s\n```" % e, expire_in=120),
                loop=self.bot.loop
            ),
            retry_on_error=True
        )

        if not info:
            raise CommandError(
                self.str.get(
                    'cmd-play-nodata',
                    'Error extracting info from search string, youtube-dl returned no data.'
                    'You may need to restart the bot if this continues to happen.'
                ),
                expire_in=30
            )

        if not all(info.get('entries', [])):
            log.debug("Got empty list, no data")
            return None, None

        # TODO: handle 'webpage_url' being 'ytsearch:...' or extractor type
        song_url = info['entries'][0]['webpage_url']
        info = await self.downloader.extract_info(
            player.playlist.loop, song_url, download=False, process=False
        )

        return song_url, info

    async def _send_playlist_gathering_msg(self, num_songs: int, wait_per_song: float, channel):
        eta = fixg(num_songs * wait_per_song)
        eta_msg = self.str.get('cmd-play-playlist-gathering-2', ', ETA: {0} seconds').format(eta) \
                  if num_songs >= 10 else '.'
        safe_msg = self.str.get(
            'cmd-play-playlist-gathering-1',
            'Gathering playlist information for {0} songs{1}'
        ).format(num_songs, eta_msg)
        return await self.safe_send_message(channel, safe_msg)

    async def _handle_entries(self, play_req: PlayRequirements, info):
        author = play_req.author
        channel = play_req.channel
        permissions = play_req.permissions
        player = play_req.player

        await self._do_playlist_checks(permissions, player, author, info['entries'])

        if info['extractor'].lower() in ['youtube:playlist', 'soundcloud:set', 'bandcamp:album']:
            try:
                return await self._cmd_play_playlist_async(
                    player,
                    channel,
                    author,
                    permissions,
                    play_req.song_url,
                    info['extractor']
                )
            except CommandError:
                raise
            except Exception as e:
                log.error("Error queuing playlist", exc_info=True)
                error_msg = self.str.get(
                    'cmd-play-playlist-error', 'Error queuing playlist:\n`{0}`'
                ).format(e)
                raise CommandError(error_msg, expire_in=30) from e

        t0 = time.time()

        # My test was 1.2 seconds per song, but we maybe should fudge
        # it a bit, unless we can monitor it and edit the message with
        # the estimated time, but that's some ADVANCED SHIT I don't
        # think we can hook into it anyways, so this will have to do.
        # It would probably be a thread to check a few playlists and
        # get the speed from that Different playlists might download at
        # different speeds though
        wait_per_song = 1.2
        num_songs = sum(1 for _ in info['entries'])

        procmesg = await self._send_playlist_gathering_msg(num_songs, wait_per_song, channel)

        # We don't have a pretty way of doing this yet. We need either a loop
        # that sends these every 10 seconds or a nice context manager.
        await self.send_typing(channel)

        # TODO: I can create an event emitter object instead, add event
        # functions, and every play list might be asyncified Also have
        # a "verify_entry" hook with the entry as an arg and returns
        # the entry if its ok
        entry_list, position = await player.playlist.import_from(
            play_req.song_url,
            channel=channel,
            author=author
        )

        tnow = time.time()
        ttime = tnow - t0
        listlen = len(entry_list)
        drop_count = 0

        if permissions.max_song_length:
            for e in entry_list.copy():
                # Im pretty sure there's no situation where this would ever
                # break Unless the first entry starts being played, which would
                # make this a race condition
                if e.duration > permissions.max_song_length:
                    player.playlist.entries.remove(e)
                    entry_list.remove(e)
                    drop_count += 1
            if drop_count:
                log.info("Dropped %s songs", drop_count)

        log.info("Processed {} songs in {} seconds at {:.2f}s/song, {:+.2g}/song from expected ({}s)".format(
            listlen,
            fixg(ttime),
            ttime / listlen if listlen else 0,
            ttime / listlen - wait_per_song if listlen - wait_per_song else 0,
            fixg(wait_per_song * num_songs))
        )

        await self.safe_delete_message(procmesg)

        if not listlen - drop_count:
            raise CommandError(
                self.str.get(
                    'cmd-play-playlist-maxduration',
                    "No songs were added, all songs were over max duration (%ss)"
                ) % permissions.max_song_length,
                expire_in=30
            )

        reply_text = self.str.get('cmd-play-playlist-reply', "Enqueued **%s** songs to be played. Position in queue: %s")
        btext = str(listlen - drop_count)

        return reply_text, btext, position

    async def _handle_entry(self, play_req: PlayRequirements, info):
        author = play_req.author
        channel = play_req.channel
        permissions = play_req.permissions
        player = play_req.player

        # youtube:playlist extractor but it's actually an entry
        if info.get('extractor', '').startswith('youtube:playlist'):
            try:
                info = await self.downloader.extract_info(
                    player.playlist.loop,
                    f'https://www.youtube.com/watch?v={info.get("url", "")}',
                    download=False,
                    process=False
                )
            except Exception as e:
                raise CommandError(e, expire_in=30) from e

        if permissions.max_song_length and info.get('duration', 0) > permissions.max_song_length:
            error_msg = self.str.get(
                'cmd-play-song-limit',
                f"Song duration exceeds limit ({info['duration']} > {permissions.max_song_length})")
            raise PermissionsError(error_msg, expire_in=30)

        entry, position = await player.playlist.add_entry(play_req.song_url, info, channel=channel, author=author)

        reply_text = self.str.get('cmd-play-song-reply', "Enqueued `%s` to be played. Position in queue: %s")
        btext = entry.title
        return reply_text, btext, position

    async def _handle_spotify_track(
        self, play_req: PlayRequirements, context: Context, parts: list
    ):
        res = await self.spotify.get_track(parts[-1])
        song_url = res['artists'][0]['name'] + ' ' + res['name']
        await self._play(context, song_url)

    async def _handle_spotify_album(
        self, play_req: PlayRequirements, context: Context, parts: list
    ):
        author = play_req.author
        channel = play_req.channel
        permissions = play_req.permissions
        player = play_req.player

        res = await self.spotify.get_album(parts[-1])

        await self._do_playlist_checks(permissions, player, author, res['tracks']['items'])
        procmsg = self.str.get(
            'cmd-play-spotify-album-process', 'Processing album `{0}` (`{1}`)'
        ).format(res["name"], play_req.song_url)
        procmsg = await self.safe_send_message(channel, procmsg)

        items = res['tracks']['items']
        if play_req.shuffle:
            shuffle(items)

        for i in items:
            song_url = i['name'] + ' ' + i['artists'][0]['name']
            log.debug('Processing %s', song_url)
            await self._play(context, song_url, spotify=True)
        await self.safe_delete_message(procmsg)

        return self.str.get(
            'cmd-play-spotify-album-queued', "Enqueued `{0}` with **{1}** songs."
        ).format(res['name'], len(res['tracks']['items']))

    async def _handle_spotify_playlist(
        self, play_req: PlayRequirements, context: Context, parts: list
    ):
        author = play_req.author
        channel = play_req.channel
        permissions = play_req.permissions
        player = play_req.player

        r = await self.spotify.get_playlist_tracks(parts[-1])
        res = r['items']
        while r['next'] is not None:
            r = await self.spotify.make_spotify_req(r['next'])
            res.extend(r['items'])
        await self._do_playlist_checks(permissions, player, author, res)
        procmsg = self.str.get(
            'cmd-play-spotify-playlist-process',
            'Processing playlist `{0}` (`{1}`)'
        ).format(parts[-1], play_req.song_url)
        procmsg = await self.safe_send_message(channel, procmsg)

        if play_req.shuffle:
            shuffle(res)

        for i in res:
            song_url = i['track']['name'] + ' ' + i['track']['artists'][0]['name']
            log.debug('Processing %s', song_url)
            try:
                await self._play(context, song_url, spotify=True)
            except CommandError:
                continue
        await self.safe_delete_message(procmsg)
        return self.str.get(
            'cmd-play-spotify-playlist-queued', "Enqueued `{0}` with **{1}** songs."
        ).format(parts[-1], len(res))

    async def _handle_spotify(self, play_req: PlayRequirements, context: Context):
        parts = play_req.song_url.split(":")
        try:
            if 'track' in parts:
                return await self._handle_spotify_track(play_req, context, parts)

            if 'album' in parts:
                response_msg = await self._handle_spotify_album(play_req, context, parts)

            elif 'playlist' in parts:
                response_msg = await self._handle_spotify_playlist(play_req, context, parts)

            else:
                error_msg = self.str.get(
                    'cmd-play-spotify-unsupported',
                    'That is not a supported Spotify URI.'
                )
                error_msg = f'{error_msg}: {play_req.song_url}'
                raise CommandError(error_msg, expire_in=30)

            await self.safe_send_message(play_req.channel, response_msg)
        except SpotifyError as error:
            error_msg = self.str.get(
                'cmd-play-spotify-invalid',
                'You either provided an invalid URI, or there was a problem.'
            )
            raise CommandError(error_msg) from error

    async def _play(
        self,
        context: Context,
        song_url: str,
        shuffle: bool = False,
        spotify: bool = False,
    ):
        author: Member = context.author
        channel = context.channel
        permissions = self.permissions.for_user(author)

        if author.voice is None:
            error_msg = self.str.get(
                'cmd-summon-novc',
                'You are not connected to voice. Try joining a voice channel!'
            )
            raise CommandError(error_msg)

        player = await self._get_player(author.voice.channel)

        song_url = parser_song_url_spotify(song_url)
        play_req = PlayRequirements(
            author, channel, permissions, player, shuffle, song_url,
        )
        if self.config._spotify and song_url.startswith('spotify:'):
            return await self._handle_spotify(play_req, context)

        async with self.aiolocks[_func_() + ':' + str(author.id)]:
            self._check_for_permissions(permissions, player, author)

            info, song_url = await self.determine_type(player, song_url)
            self._check_valid_info(info, permissions)

            if info.get('url', '').startswith('ytsearch'):
                song_url, info = await self._search_song(player, song_url, channel)
                if song_url is None:
                    return

            if 'entries' in info:
                reply_text, btext, position = await self._handle_entries(
                    play_req, info,
                )

            else:
                reply_text, btext, position = await self._handle_entry(
                    play_req, info,
                )

        if spotify:
            return

        if btext is not None:
            if position == 1 and player.is_stopped:
                position = self.str.get('cmd-play-next', 'Up next!')
                reply_text %= (btext, position)

            else:
                try:
                    time_until = await player.playlist.estimate_time_until(position, player)
                    eta_msg = self.str.get('cmd-play-eta', ' - estimated time until playing: %s')
                    reply_text += eta_msg
                except:
                    traceback.print_exc()
                    time_until = ''

                reply_text %= (btext, position, ftimedelta(time_until))

        await self.safe_send_message(context, reply_text, expire_in=30)

    @command(
        description='Plays given song',
        options=[
            Option(
                'query',
                'Words query or spotify/youtube url for a song, album or playlist',
                OptionType.STRING,
                required=True,
            ),
            Option(
                'shuffle',
                'If the query is the url of a playlist, then shuffle the playlist order prior to adding',
                OptionType.BOOLEAN,
            )
        ]
    )
    async def play(self, context: Context, query: str, shuffle: Optional[bool] = False):
        song_url = parse_song_url(query)
        await self._play(context, song_url, shuffle)

    async def _do_playlist_checks(self, permissions, player, author, testobj):
        num_songs = sum(1 for _ in testobj)

        # I have to do exe extra checks anyways because you can request an
        # arbitrary number of search results
        if not permissions.allow_playlists and num_songs > 1:
            raise PermissionsError(self.str.get('playlists-noperms', "You are not allowed to request playlists"), expire_in=30)

        if permissions.max_playlist_length and num_songs > permissions.max_playlist_length:
            raise PermissionsError(
                self.str.get('playlists-big', "Playlist has too many entries ({0} > {1})").format(num_songs, permissions.max_playlist_length),
                expire_in=30
            )

        # This is a little bit weird when it says (x + 0 > y), I might add the
        # other check back in
        if permissions.max_songs and player.playlist.count_for_user(author) + num_songs > permissions.max_songs:
            raise PermissionsError(
                self.str.get('playlists-limit', "Playlist entries + your already queued songs reached limit ({0} + {1} > {2})").format(
                    num_songs, player.playlist.count_for_user(author), permissions.max_songs),
                expire_in=30
            )
        return True

    async def _cmd_play_playlist_async(self, player, channel, author, permissions, playlist_url, extractor_type):
        """
        Secret handler to use the async wizardry to make playlist queuing non-"blocking"
        """

        await self.send_typing(channel)
        info = await self.downloader.extract_info(player.playlist.loop, playlist_url, download=False, process=False)

        if not info:
            raise CommandError(self.str.get('cmd-play-playlist-invalid', "That playlist cannot be played."))

        num_songs = sum(1 for _ in info['entries'])
        t0 = time.time()

        # TODO: From playlist_title
        busymsg = await self.safe_send_message(
            channel, self.str.get('cmd-play-playlist-process', "Processing {0} songs...").format(num_songs))
        await self.send_typing(channel)

        entries_added = 0
        if extractor_type == 'youtube:playlist':
            try:
                entries_added = await player.playlist.async_process_youtube_playlist(
                    playlist_url, channel=channel, author=author)
                # TODO: Add hook to be called after each song
                # TODO: Add permissions

            except Exception:
                log.error("Error processing playlist", exc_info=True)
                raise CommandError(self.str.get('cmd-play-playlist-queueerror', 'Error handling playlist {0} queuing.').format(playlist_url), expire_in=30)

        elif extractor_type.lower() in ['soundcloud:set', 'bandcamp:album']:
            try:
                entries_added = await player.playlist.async_process_sc_bc_playlist(
                    playlist_url, channel=channel, author=author)
                # TODO: Add hook to be called after each song
                # TODO: Add permissions

            except Exception:
                log.error("Error processing playlist", exc_info=True)
                raise CommandError(self.str.get('cmd-play-playlist-queueerror', 'Error handling playlist {0} queuing.').format(playlist_url), expire_in=30)


        songs_processed = len(entries_added)
        drop_count = 0
        skipped = False

        if permissions.max_song_length:
            for e in entries_added.copy():
                if e.duration > permissions.max_song_length:
                    try:
                        player.playlist.entries.remove(e)
                        entries_added.remove(e)
                        drop_count += 1
                    except:
                        pass

            if drop_count:
                log.debug('Dropped %s songs', drop_count)

            if player.current_entry and player.current_entry.duration > permissions.max_song_length:
                await self.safe_delete_message(self.server_specific_data[channel.guild]['last_np_msg'])
                self.server_specific_data[channel.guild]['last_np_msg'] = None
                skipped = True
                player.skip()
                entries_added.pop()

        await self.safe_delete_message(busymsg)

        songs_added = len(entries_added)
        tnow = time.time()
        ttime = tnow - t0
        wait_per_song = 1.2
        # TODO: actually calculate wait per song in the process function and return that too

        # This is technically inaccurate since bad songs are ignored but still take up time
        log.info("Processed {}/{} songs in {} seconds at {:.2f}s/song, {:+.2g}/song from expected ({}s)".format(
            songs_processed,
            num_songs,
            fixg(ttime),
            ttime / num_songs if num_songs else 0,
            ttime / num_songs - wait_per_song if num_songs - wait_per_song else 0,
            fixg(wait_per_song * num_songs))
        )

        if not songs_added:
            basetext = self.str.get('cmd-play-playlist-maxduration', "No songs were added, all songs were over max duration (%ss)") % permissions.max_song_length
            if skipped:
                basetext += self.str.get('cmd-play-playlist-skipped', "\nAdditionally, the current song was skipped for being too long.")

            raise CommandError(basetext, expire_in=30)

        default_msg = f'Enqueued {songs_added} songs to be played in {fixg(ttime, 1)} seconds'
        reply_text = self.str.get('cmd-play-playlist-reply-secs', default_msg)
        return reply_text, None

    async def send_typing(self, destination):
        try:
            return await destination.trigger_typing()
        except discord.Forbidden:
            log.warning('Could not send typing to %s, no permission', destination)
