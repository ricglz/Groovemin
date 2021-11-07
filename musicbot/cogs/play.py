'''Play Cog module'''
from dataclasses import dataclass
import random
from typing import Optional
import logging
import re
import time

from discord import Guild, Member, VoiceClient
from discord.ext.commands import Context
from dislash import command, Option, OptionType

from ..exceptions import CommandError, SpotifyError
from ..permissions import Permissions
from ..player import MusicPlayer
from ..spotify import Spotify
from ..utils import fixg
from .custom_cog import CustomCog

log = logging.getLogger(__name__)

LINKS_REGEX = '((http(s)*:[/][/]|www.)([a-z]|[A-Z]|[0-9]|[/.]|[~])*)'
PLAYLIST_REGEX = r'watch\?v=.+&(list=[^&]+)'

def is_link(value: str):
    '''Checks if the value is a link'''
    return re.compile(LINKS_REGEX).match(value) is not None

def parse_song_url(song_query: str):
    '''Given a song query it sanitizes it, in case that is a url'''
    song_url = song_query.strip('<>')
    if not is_link(song_url):
        return song_url.replace('/', '%2F')

    # Rewrite YouTube playlist URLs if the wrong URL type is given
    matches = re.search(PLAYLIST_REGEX, song_url)
    if matches is None:
        return song_url
    return f'https://www.youtube.com/playlist?{matches.groups()[0]}'

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

    async def _handle_entries(self, play_req: PlayRequirements, info):
        pass

    async def _handle_entry(self, play_req: PlayRequirements, info):
        pass

    async def _send_playlist_gathering_msg(self, num_songs: int, wait_per_song: float, channel):
        eta = fixg(num_songs * wait_per_song)
        eta_msg = self.str.get('cmd-play-playlist-gathering-2', ', ETA: {0} seconds').format(eta) \
                  if num_songs >= 10 else '.'
        safe_msg = self.str.get(
            'cmd-play-playlist-gathering-1',
            'Gathering playlist information for {0} songs{1}'
        ).format(num_songs, eta_msg)
        return await self.safe_send_message(channel, safe_msg)

    async def _handle_spotify_track(
        self, _: PlayRequirements, context: Context, parts: list
    ):
        res = await self.spotify.get_track(parts[-1])
        query = res['artists'][0]['name'] + ' ' + res['name']
        await self._play(context, query)

    async def _handle_spotify_album(
        self, play_req: PlayRequirements, context: Context, parts: list
    ):
        res = await self.spotify.get_album(parts[-1])

        procmsg = self.str.get(
            'cmd-play-spotify-album-process', 'Processing album `{0}` (`{1}`)'
        ).format(res["name"], play_req.song_url)
        procmsg = await self.safe_send_message(context, procmsg)

        items = res['tracks']['items']
        if play_req.shuffle:
            random.shuffle(items)

        for i in items:
            song_query = i['name'] + ' ' + i['artists'][0]['name']
            log.debug('Processing %s', song_query)
            await self._play(context, song_query)
        await self.safe_delete_message(procmsg)

        return self.str.get(
            'cmd-play-spotify-album-queued', "Enqueued `{0}` with **{1}** songs."
        ).format(res['name'], len(res['tracks']['items']))

    async def _handle_spotify_playlist(
        self, play_req: PlayRequirements, context: Context, parts: list
    ):
        r = await self.spotify.get_playlist_tracks(parts[-1])
        res = r['items']
        while r['next'] is not None:
            r = await self.spotify.make_spotify_req(r['next'])
            res.extend(r['items'])
        procmsg = self.str.get(
            'cmd-play-spotify-playlist-process',
            'Processing playlist `{0}` (`{1}`)'
        ).format(parts[-1], play_req.song_url)
        procmsg = await self.safe_send_message(context, procmsg)

        if play_req.shuffle:
            random.shuffle(res)

        for i in res:
            song_query = i['track']['name'] + ' ' + i['track']['artists'][0]['name']
            log.debug('Processing %s', song_query)
            try:
                await self._play(context, song_query)
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
        song_query: str,
        shuffle: bool = False,
    ):
        song_query = parser_song_url_spotify(song_query)
        if not is_link(song_query):
            song_query = f'ytsearch:{song_query}'
        player = await self._get_player(context)
        play_req = PlayRequirements(
            context.author,
            context.channel,
            self.permissions,
            player,
            shuffle,
            song_query
        )

        if self.config._spotify and song_query.startswith('spotify:'):
            return await self._handle_spotify(play_req, context)

        voice_client = self._get_voice_client(context.guild)
        if voice_client.is_playing() or player.has_queue:
            return await player.queue(song_query, context)

        return await player.start_song(song_query, context, voice_client)

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
                'If the query is the url of a playlist, then shuffle the playlist order prior to '
                'adding',
                OptionType.BOOLEAN,
            )
        ]
    )
    async def play(self, context: Context, query: str, shuffle: Optional[bool] = False):
        await self.before_play(context)
        song_query = parse_song_url(query)
        await self._play(context, song_query, shuffle)

    def _get_voice_client(self, guild: Guild) -> Optional[VoiceClient]:
        '''Returns the voice client of the guild'''
        for voice_client in self.voice_clients:
            if voice_client.guild == guild:
                return voice_client
        return None

    async def before_play(self, msg: Context):
        """
        Check voice_client
            - User voice = None:
                please join a voice channel
            - bot voice == None:
                joins the user's voice channel
            - user and bot voice NOT SAME:
                - music NOT Playing AND queue EMPTY
                    join user's voice channel
                - items in queue:
                    please join the same voice channel as the bot to add song to queue
        """

        if msg.author.voice is None:
            raise CommandError(
                '**Please join a voice channel to play music**'.title(),
                expire_in=15
            )

        voice_client = self._get_voice_client(msg.guild)
        if voice_client is None:
            return await msg.author.voice.channel.connect()

        if voice_client.channel == msg.author.voice.channel:
            return

        player = await self._get_player(msg)
        # NOTE: Check player and queue
        if not voice_client.is_playing() and not player.has_queue:
            return await voice_client.move_to(msg.author.voice.channel)
            # NOTE: move bot to user's voice channel if queue does not exist

        if player.has_queue:
            # NOTE: user must join same voice channel if queue exist
            raise CommandError(
                'Please join the same voice channel as the bot to add song to queue',
                expire_in=15
            )
