'''Module containing the main downloader class'''
from concurrent.futures import ThreadPoolExecutor

import asyncio
import logging

from discord import FFmpegPCMAudio, PCMVolumeTransformer

from youtube_dl import YoutubeDL

log = logging.getLogger(__name__)

simulate = {
    'default_search': 'auto',
    'ignoreerrors': True,
    'quiet': True,
    'no_warnings': True,
    'simulate': True,  # do not keep the video files
    'nooverwrites': True,
    'keepvideo': False,
    'noplaylist': True,
    'skip_download': False,
    # bind to ipv4 since ipv6 addresses cause issues sometimes
    'source_address': '0.0.0.0'
}

ffmpeg_options = {'options': '-vn'}

executor = ThreadPoolExecutor()

class Downloader(PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.thumbnail = data.get('thumbnail')
        self.duration = data.get('duration')
        self.views = data.get('view_count')
        self.playlist = {}

    @staticmethod
    async def _get_data(
        loop: asyncio.AbstractEventLoop,
        yt_dl: YoutubeDL,
        query: str,
        download: bool
    ):
        return await loop.run_in_executor(
            executor,
            lambda: yt_dl.extract_info(query, download=download)
        )

    @classmethod
    async def video_url(cls, query: str, yt_dl: YoutubeDL, *, loop=None, stream: bool=False):
        """Download the song file and data."""
        loop = loop or asyncio.get_event_loop()
        data = await cls._get_data(loop, yt_dl, query, not stream)
        song_list = {'queue': []}
        if 'entries' in data:
            if len(data['entries']) > 1:
                playlist_titles = [title['title'] for title in data['entries']]
                song_list = {'queue': playlist_titles}
                song_list['queue'].pop(0)

            data = data['entries'][0]

        filename = data['url'] if stream else yt_dl.prepare_filename(data)
        return cls(FFmpegPCMAudio(filename, **ffmpeg_options), data=data), song_list

    @classmethod
    async def get_info(cls, query):
        """
        Get the info of the next song by not downloading the actual file but
        just the data of song/query.
        """
        data = await cls._get_data(asyncio.get_event_loop(), YoutubeDL(simulate), query, False)
        extra_data = {'queue': []}
        if 'entries' in data:
            if len(data['entries']) > 1:
                playlist_titles = [title['title'] for title in data['entries']]
                extra_data = {'title': data['title'], 'queue': playlist_titles}

            title = data['entries'][0]['title']
        else:
            title = data

        return title, extra_data
