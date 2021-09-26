'''Module containing the logic for Playlist'''
from collections import deque
from itertools import islice
from random import shuffle
from typing import Callable, Deque, Union
import datetime
import logging
import os.path

from urllib.error import URLError
from youtube_dl.utils import DownloadError, UnsupportedError

from .bot import MusicBot
from .constructs import Serializable
from .entry import URLPlaylistEntry, StreamPlaylistEntry
from .exceptions import ExtractionError, WrongEntryTypeError
from .lib.event_emitter import EventEmitter
from .utils import get_header

log = logging.getLogger(__name__)

Entry = Union[URLPlaylistEntry, StreamPlaylistEntry]
Entries = Deque[Entry]

class Playlist(EventEmitter, Serializable):
    """A playlist is manages the list of songs that will be played."""

    def __init__(self, bot: MusicBot):
        super().__init__()
        self.bot = bot
        self.loop = bot.loop
        self.downloader = bot.downloader
        self.entries: Entries = deque()

    def __iter__(self):
        return iter(self.entries)

    def __len__(self):
        return len(self.entries)

    def shuffle(self):
        '''Shuffles the entries'''
        shuffle(self.entries)

    def clear(self):
        '''Clears the entries'''
        self.entries.clear()

    def get_entry_at_index(self, index: int):
        '''Gets entry at the given index'''
        self.entries.rotate(-index)
        entry = self.entries[0]
        self.entries.rotate(index)
        return entry

    def delete_entry_at_index(self, index: int):
        '''Deletes entry at the given index.'''
        self.entries.rotate(-index)
        entry = self.entries.popleft()
        self.entries.rotate(index)
        return entry

    async def _handle_generic_dropbox(self, song_url: str, info: dict, **meta):
        log.debug('Detected a generic extractor, or Dropbox')
        try:
            headers = await get_header(self.bot.aiosession, info['url'])
            content_type = headers.get('CONTENT-TYPE')
            log.debug("Got content type %s", content_type)
        except Exception as err:
            log.warning("Failed to get content type for url %s (%s)", song_url, err)
            content_type = None
        if content_type:
            if content_type.startswith(('application/', 'image/')):
                if not any(x in content_type for x in ('/ogg', '/octet-stream')):
                    # How does a server say `application/ogg` what the actual fuck
                    error_msg = f'Invalid content type "{content_type}" for url {song_url}'
                    raise ExtractionError(error_msg)
            elif content_type.startswith('text/html') and info['extractor'] == 'generic':
                log.warning("Got text/html for content-type, this might be a stream.")
                # TODO: Check for shoutcast/icecast
                return await self.add_stream_entry(song_url, info, **meta)
            elif not content_type.startswith(('audio/', 'video/')):
                log.warning('Questionable content-type "%s" for url %s', content_type, song_url)
        return None

    async def add_entry(self, song_url: str, info: dict, **meta):
        """
        Validates and adds a song_url to be played. This does not start the
        download of the song.

        Returns the entry & the position it is in the queue.

        :param song_url: The song url to add to the playlist.
        :param meta: Any additional metadata to add to the playlist entry.
        """

        if not info:
            raise ExtractionError('Could not extract information from %s' % song_url)

        # TODO: Sort out what happens next when this happens
        if info.get('_type', None) == 'playlist':
            raise WrongEntryTypeError(
                "This is a playlist.", True, info.get('webpage_url', None) or info.get('url', None)
            )

        if info.get('is_live', False):
            return await self.add_stream_entry(song_url, info, **meta)

        if info['extractor'] in ['generic', 'Dropbox']:
            result = await self._handle_generic_dropbox(song_url, info, **meta)
            if result is not None:
                return result, len(self.entries)

        entry = URLPlaylistEntry(
            self,
            song_url,
            info.get('title', 'Untitled'),
            info.get('duration', 0) or 0,
            self.downloader.ytdl.prepare_filename(info),
            **meta
        )
        self._add_entry(entry)
        return entry, len(self.entries)

    async def add_stream_entry(self, song_url, info=None, **meta):
        '''Adds an entry that is a stream.'''
        if info is None:
            info = {'title': song_url, 'extractor': None}

            try:
                info = await self.downloader.extract_info(self.loop, song_url, download=False)

            except DownloadError as err:
                # ytdl doesn't like it but its probably a stream
                if err.exc_info[0] == UnsupportedError:
                    log.debug("Assuming content is a direct stream")
                elif err.exc_info[0] == URLError:
                    exists_path = os.path.exists(os.path.abspath(song_url))
                    error_msg = "This is not a stream, this is a file path." if exists_path else \
                                "Invalid input: {0.exc_info[0]}: {0.exc_info[1].reason}".format(err)
                    raise ExtractionError(error_msg) from err
                else:
                    # traceback.print_exc()
                    raise ExtractionError("Unknown error: {}".format(err)) from err
            except Exception as err:
                log.error(
                    'Could not extract information from %s (%s), falling back to direct',
                    song_url,
                    err,
                    exc_info=True
                )

        # wew hacky
        if info.get('is_live') is None and info.get('extractor', None) != 'generic':
            raise ExtractionError("This is not a stream.")

        dest_url = song_url
        if info.get('extractor'):
            dest_url = info.get('url')

        if info.get('extractor', None) == 'twitch:stream':  # may need to add other twitch types
            title = info.get('description')
        else:
            title = info.get('title', 'Untitled')

        # TODO: A bit more validation, "~stream some_url" should not just say :ok_hand:

        entry = StreamPlaylistEntry(
            self,
            song_url,
            title,
            destination = dest_url,
            **meta
        )
        self._add_entry(entry)
        return entry, len(self.entries)

    async def import_from(self, playlist_url: str, **meta):
        """
        Imports the songs from `playlist_url` and queues them to be played.

        Returns a list of `entries` that have been enqueued.

        :param playlist_url: The playlist url to be cut into individual urls
                             and added to the playlist
        :param meta: Any additional metadata to add to the playlist entry
        """
        position = len(self.entries) + 1
        entry_list = []

        try:
            info = await self.downloader.safe_extract_info(self.loop, playlist_url, download=False)
        except Exception as err:
            error_msg = 'Could not extract information from {}\n\n{}'.format(playlist_url, err)
            raise ExtractionError(error_msg) from err

        if not info:
            raise ExtractionError('Could not extract information from %s' % playlist_url)

        # Once again, the generic extractor fucks things up.
        if info.get('extractor', None) == 'generic':
            url_field = 'url'
        else:
            url_field = 'webpage_url'

        baditems = 0
        for item in info['entries']:
            if item:
                try:
                    entry = URLPlaylistEntry(
                        self,
                        item[url_field],
                        item.get('title', 'Untitled'),
                        item.get('duration', 0) or 0,
                        self.downloader.ytdl.prepare_filename(item),
                        **meta
                    )

                    self._add_entry(entry)
                    entry_list.append(entry)
                except Exception as err:
                    baditems += 1
                    log.warning("Could not add item", exc_info=err)
                    log.debug("Item: %s", item, exc_info=True)
            else:
                baditems += 1

        if baditems:
            log.info("Skipped %s bad entries", baditems)

        return entry_list, position

    async def _safe_info_extraction(self, playlist_url: str):
        try:
            info = await self.downloader.safe_extract_info(
                self.loop,
                playlist_url,
                download=False,
                process=False
            )
        except Exception as err:
            error_msg = 'Could not extract information from {}\n\n{}'.format(playlist_url, err)
            raise ExtractionError(error_msg) from err

        if not info:
            raise ExtractionError('Could not extract information from %s' % playlist_url)

        return info


    async def _get_good_items(self, info: dict, get_song_url: Callable[[object], str], **meta):
        gooditems = []
        baditems = 0
        for entry_data in info['entries']:
            if entry_data:
                song_url = get_song_url(entry_data)
                try:
                    entry, _ = await self.add_entry(song_url, **meta)
                    gooditems.append(entry)
                except ExtractionError:
                    baditems += 1
                except Exception as err:
                    baditems += 1
                    log.error("Error adding entry %s", entry_data['id'], exc_info=err)
            else:
                baditems += 1
        if baditems:
            log.info("Skipped %s bad entries", baditems)

        return gooditems

    async def async_process_youtube_playlist(self, playlist_url: str, **meta):
        """
        Processes youtube playlists links from `playlist_url` in a questionable, async fashion.

        :param playlist_url: The playlist url to be cut into individual urls
                             and added to the playlist
        :param meta: Any additional metadata to add to the playlist entry
        """

        info = await self._safe_info_extraction(playlist_url)
        baseurl = info['webpage_url'].split('playlist?list=')[0]
        get_song_url = lambda entry_data: f"{baseurl}watch?v={entry_data['id']}"
        return await self._get_good_items(info, get_song_url, **meta)

    async def async_process_sc_bc_playlist(self, playlist_url: str, **meta):
        """
        Processes soundcloud set and bancdamp album links from `playlist_url`
        in a questionable, async fashion.

        :param playlist_url: The playlist url to be cut into individual urls
                             and added to the playlist
        :param meta: Any additional metadata to add to the playlist entry
        """

        info = await self._safe_info_extraction(playlist_url)
        return await self._get_good_items(info, lambda entry_data: entry_data['url'], **meta)

    def _add_entry(self, entry: Entry, *, head=False):
        if head:
            self.entries.appendleft(entry)
        else:
            self.entries.append(entry)

        self.emit('entry-added', playlist=self, entry=entry)

        if self.peek() is entry:
            entry.get_ready_future()

    async def get_next_entry(self, predownload_next=True):
        """
        A coroutine which will return the next song or None if no songs left to
        play.

        Additionally, if predownload_next is set to True, it will attempt to
        download the next song to be played - so that it's ready by the time we
        get to it.
        """
        if not self.entries:
            return None

        entry = self.entries.popleft()

        if predownload_next:
            next_entry = self.peek()
            if next_entry:
                next_entry.get_ready_future()

        return await entry.get_ready_future()

    def peek(self):
        """Returns the next entry that should be scheduled to be played."""
        return self.entries[0] if self.entries else None

    async def estimate_time_until(self, position, player):
        """
        (very) Roughly estimates the time till the queue will 'position'
        """
        estimated_time = sum(e.duration for e in islice(self.entries, position - 1))

        # When the player plays a song, it eats the first playlist item, so we
        # just have to add the time back
        if not player.is_stopped and player.current_entry:
            estimated_time += player.current_entry.duration - player.progress

        return datetime.timedelta(seconds=estimated_time)

    def count_for_user(self, user):
        return sum(1 for e in self.entries if e.meta.get('author', None) == user)


    def __json__(self):
        return self._enclose_json({
            'entries': list(self.entries)
        })

    @classmethod
    def _deserialize(cls, raw_json, bot=None):
        assert bot is not None, cls._bad('bot')
        # log.debug("Deserializing playlist")
        pl = cls(bot)

        for entry in raw_json['entries']:
            pl.entries.append(entry)

        # TODO: create a function to init downloading (since we don't do it here)?
        return pl
