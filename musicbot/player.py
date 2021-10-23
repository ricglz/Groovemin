'''Class containing logic for Player Class'''
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

import asyncio
import logging
import os
import random
import string

from discord import Color, Embed, FFmpegPCMAudio, PCMVolumeTransformer
from youtube_dl import YoutubeDL

from .downloader import Downloader

log = logging.getLogger(__name__)

ytdl_format_options = {
    'audioquality': 5,
    'format': 'bestaudio',
    'outtmpl': '{}',
    'restrictfilenames': True,
    'flatplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    "extractaudio": True,
    "audioformat": "opus",
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    # bind to ipv4 since ipv6 addresses cause issues sometimes
    'source_address': '0.0.0.0'
}

def filename_generator():
    """
    Generate a unique file name for the song file to be named as
    """
    chars = string.ascii_letters + string.digits
    name = ''
    for _ in range(random.randint(9, 25)):
        name += random.choice(chars)

    return name

def random_color():
    '''Generates random color'''
    return Color.from_rgb(random.randint(1, 255), random.randint(1, 255), random.randint(1, 255))

class MusicPlayerState(Enum):
    '''Enum class representing the state that the MusicPlayer is currently at.'''
    STOPPED = 0  # When the player isn't playing anything
    PLAYING = 1  # The player is actively playing music.
    PAUSED = 2   # The player is paused on a song.
    WAITING = 3  # The player has finished its song but is still downloading the next one
    DEAD = 4     # The player has been killed.
    RESET = 5    # The player is playing but will play the same song when finished
    LOOP = 6     # The player is playing but will play the same song until go out of the loop

    def __str__(self):
        return self.name

@dataclass
class QueueElement:
    '''Represents an element of the music player queue'''
    title: str
    author: object

@dataclass
class MusicPlayer:
    '''Class in charge of all the music management'''
    loop: asyncio.AbstractEventLoop

    _queue: List[QueueElement] = []
    author: Optional[object] = None
    current_title: Optional[Downloader] = None
    filename: Optional[str] = None
    state: MusicPlayerState = MusicPlayerState.STOPPED
    volume: float = 0.5

    def _add_to_queue(self, title, msg):
        self._queue.append(QueueElement(title, msg))

    def _queue_playlist(self, data, msg):
        """THIS FUNCTION IS FOR WHEN YOUTUBE LINK IS A PLAYLIST."""
        for title in data['queue']:
            self._queue.append(QueueElement(title, msg))

    @property
    def has_queue(self):
        '''Property to check if the player has remaining queue'''
        return len(self._queue) > 0

    async def queue(self, song_query, msg):
        '''Appends to the queue the data created by the downloader'''
        title, data = Downloader.get_info(song_query)
        if data['queue']:
            self._queue_playlist(data, msg)
            return await msg.send(f"Added playlist {data['title']} to queue")
        self._add_to_queue(title, msg)
        return await msg.send(f"**{title} added to queue**".title())

    def _clear_data(self):
        """Clear the local dict data"""
        os.remove(self.filename)

    async def _voice_check(self, msg: object):
        '''Bot leave voice channel if music not being played for longer than 2 minutes,'''
        if msg.voice_client is None:
            return
        await asyncio.sleep(120)
        is_still = msg.voice_client.is_playing() is False and msg.voice_client.is_paused() is False
        if is_still:
            await msg.voice_client.disconnect()

    def _create_yt_dl(self):
        new_opts = ytdl_format_options.copy()
        audio_name = filename_generator()
        new_opts['outtmpl'] = new_opts['outtmpl'].format(audio_name)
        self.filename = audio_name
        return YoutubeDL(new_opts)

    @staticmethod
    def _create_now_playing_emb(download: Downloader, msg):
        emb = Embed(colour=random_color(), title='Now Playing',
                    description=download.title, url=download.url)
        emb.set_thumbnail(url=download.thumbnail)
        emb.set_footer(
            text=f'Requested by {msg.author.display_name}', icon_url=msg.author.avatar_url)
        return emb

    async def start_song(self, song_query, msg):
        '''Starts the given song'''
        yt_dl = self._create_yt_dl()

        download, data = await Downloader.video_url(song_query, yt_dl, loop=self.loop)
        loop = asyncio.get_event_loop()

        if data['queue']:
            await self._queue_playlist(data, msg)

        emb = self._create_now_playing_emb(download, msg)
        msg_id = await msg.send(embed=emb).id
        self.current_title = download
        self.author = msg
        msg.voice_client.play(
            download, after=lambda a: loop.create_task(self._done(msg, msg_id)))

        # if str(msg.guild.id) in self.music: #NOTE adds user's default volume if in database
        #     msg.voice_client.source.volume=self.music[str(msg.guild.id)]['vol']/100
        msg.voice_client.source.volume = self.volume
        return msg.voice_client

    async def _done(self, msg: object, msg_id: Optional[int]=None):
        '''Function to run once song completes.'''
        if msg_id:
            message = await msg.channel.fetch_message(msg_id)
            await message.delete()

        if self.state == MusicPlayerState.RESET:
            self.state = MusicPlayerState.PLAYING
            return await self._loop_song(msg)

        if self.state == MusicPlayerState.LOOP:
            return await self._loop_song(msg)

        await self._clear_data()

        if self._queue:
            next_element = self._queue.pop(0)
            return await self.start_song(next_element.author, next_element.title)
        await self._voice_check(msg)

    def _loop_song(self, msg: object):
        """
        Loop the currently playing song by replaying the same audio file via
        `discord.PCMVolumeTransformer()`.
        """
        source = PCMVolumeTransformer(FFmpegPCMAudio(self.filename))
        loop = asyncio.get_event_loop()
        msg.voice_client.play(source, after=lambda a: loop.create_task(self._done(msg)))
        msg.voice_client.source.volume = self.volume
