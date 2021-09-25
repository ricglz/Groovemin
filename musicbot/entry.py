'''Main module for managing entries'''
from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING
import asyncio
import logging
import os
import re
import sys
import traceback

from .constructs import Serializable
from .exceptions import ExtractionError
from .utils import get_header, md5sum

if TYPE_CHECKING:
    from .playlist import Playlist

log = logging.getLogger(__name__)

class BasePlaylistEntry(Serializable):
    '''Abstract class to specify properties of an entry'''
    filename: Optional[str] = None
    _is_downloading = False
    _waiting_futures: List[asyncio.Future] = []

    def __init__(self, playlist: Playlist, url: str, title: str, duration: float, **meta):
        self.playlist = playlist
        self.url = url
        self.title = title
        self.duration = duration
        self.meta = meta

    @property
    def is_downloaded(self):
        '''Property to now if the entry has already been downloaded'''
        return not (self._is_downloading or self.filename is None)

    async def _download(self):
        raise NotImplementedError

    def get_ready_future(self):
        """
        Returns a future that will fire when the song is ready to be played.
        The future will either fire with the result (being the entry) or an
        exception as to why the song download failed.
        """
        future = asyncio.Future()
        if self.is_downloaded:
            # In the event that we're downloaded, we're already ready for playback.
            future.set_result(self)

        else:
            # If we request a ready future, let's ensure that it'll actually resolve at one point.
            self._waiting_futures.append(future)
            asyncio.ensure_future(self._download())

        log.debug('Created future for %s', self.filename)
        return future

    def _for_each_future(self, callback):
        """
        Calls `callback` for each future that is not cancelled. Absorbs and
        logs any errors that may have occurred.
        """
        futures = self._waiting_futures
        self._waiting_futures = []

        for future in futures:
            if future.cancelled():
                continue
            try:
                callback(future)
            except:
                traceback.print_exc()

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)

    @classmethod
    def _get_meta(cls, data: dict, playlist: Playlist):
        meta = {}
        # TODO: Better [name] fallbacks
        if 'channel' in data['meta']:
            channel = playlist.bot.get_channel(data['meta']['channel']['id'])
            meta['channel'] = channel or data['meta']['channel']['name']
        if 'author' in data['meta']:
            meta['author'] = meta['channel'].guild.get_member(data['meta']['author']['id'])
        return meta

class URLPlaylistEntry(BasePlaylistEntry):
    '''Class for managing url entries'''
    aoptions = '-vn'

    def __init__(self, playlist, url, title, duration=0, expected_filename=None, **meta):
        super().__init__(playlist, url, title, duration, **meta)

        self.expected_filename = expected_filename
        self.download_folder = self.playlist.downloader.download_folder

    def __json__(self):
        return self._enclose_json({
            'version': 1,
            'url': self.url,
            'title': self.title,
            'duration': self.duration,
            'downloaded': self.is_downloaded,
            'expected_filename': self.expected_filename,
            'filename': self.filename,
            'full_filename': os.path.abspath(self.filename) if self.filename else self.filename,
            'meta': {
                name: {
                    'type': obj.__class__.__name__,
                    'id': obj.id,
                    'name': obj.name
                } for name, obj in self.meta.items() if obj
            },
            'aoptions': self.aoptions
        })

    @classmethod
    def _deserialize(cls, data, playlist: Optional[Playlist]=None):
        assert playlist is not None, cls._bad('playlist')

        try:
            # TODO: version check
            url = data['url']
            title = data['title']
            duration = data['duration']
            downloaded = data['downloaded'] if playlist.bot.config.save_videos else False
            filename = data['filename'] if downloaded else None
            expected_filename = data['expected_filename']
            meta = cls._get_meta(data, playlist)
            entry = cls(playlist, url, title, duration, expected_filename, **meta)
            entry.filename = filename
            return entry
        except Exception as e:
            log.error("Could not load %s", cls.__name__, exc_info=e)

    async def _download_generic_extractor(self):
        flistdir = [f.rsplit('-', 1)[0] for f in os.listdir(self.download_folder)]
        expected_fname_noex, fname_ex = os.path.basename(self.expected_filename).rsplit('.', 1)

        if expected_fname_noex in flistdir:
            try:
                rsize = int(await get_header(self.playlist.bot.aiosession, self.url, 'CONTENT-LENGTH'))
            except:
                rsize = 0

            lfile = os.path.join(
                self.download_folder,
                os.listdir(self.download_folder)[flistdir.index(expected_fname_noex)]
            )

            # print("Resolved %s to %s" % (self.expected_filename, lfile))
            lsize = os.path.getsize(lfile)
            # print("Remote size: %s Local size: %s" % (rsize, lsize))

            if lsize != rsize:
                await self._really_download(perform_hash=True)
            else:
                # print("[Download] Cached:", self.url)
                self.filename = lfile

        else:
            # print("File not found in cache (%s)" % expected_fname_noex)
            await self._really_download(perform_hash=True)

    async def _download_other_extractor(self):
        ldir = os.listdir(self.download_folder)
        flistdir = [f.rsplit('.', 1)[0] for f in ldir]
        expected_fname_base = os.path.basename(self.expected_filename)
        expected_fname_noex = expected_fname_base.rsplit('.', 1)[0]

        # idk wtf this is but its probably legacy code
        # or i have youtube to blame for changing shit again
        if expected_fname_base in ldir:
            log.info("Download cached: %s", self.url)
            self.filename = os.path.join(self.download_folder, expected_fname_base)
        elif expected_fname_noex in flistdir:
            log.info("Download cached (different extension): %s", self.url)
            self.filename = os.path.join(
                self.download_folder, ldir[flistdir.index(expected_fname_noex)]
            )
            log.debug(
                "Expected %s, got %s",
                self.expected_filename.rsplit('.', 1)[-1],
                self.filename.rsplit('.', 1)[-1]
            )
        else:
            await self._really_download()

    # noinspection PyTypeChecker
    async def _download(self):
        if self._is_downloading:
            return

        self._is_downloading = True
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)
        extractor = os.path.basename(self.expected_filename).split('-')[0]
        try:
            # the generic extractor requires special handling
            if extractor == 'generic':
                await self._download_generic_extractor()
            else:
                await self._download_other_extractor()

            if self.playlist.bot.config.use_experimental_equalization:
                try:
                    _, maximum = await self.get_mean_volume(self.filename)
                    aoptions = '-af "volume={}dB"'.format((maximum * -1))
                except Exception as e:
                    log.error('There as a problem with working out EQ, likely caused by a strange '
                              'installation of FFmpeg. This has not impacted the ability for the '
                              'bot to work, but will mean your tracks will not be equalised.')
                    aoptions = "-vn"
            else:
                aoptions = "-vn"

            self.aoptions = aoptions

            # Trigger ready callbacks.
            self._for_each_future(lambda future: future.set_result(self))

        except Exception as e:
            traceback.print_exc()
            self._for_each_future(lambda future: future.set_exception(e))

        finally:
            self._is_downloading = False

    async def run_command(self, cmd):
        '''Runs shell command asynchronously'''
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        log.debug('Starting asyncio subprocess (%s) with command: %s', process, cmd)
        stdout, stderr = await process.communicate()
        return stdout + stderr

    def get(self, program):
        '''Gets program binary filepath'''
        def is_exe(fpath):
            found = os.path.isfile(fpath) and os.access(fpath, os.X_OK)
            if not found and sys.platform == 'win32':
                fpath = fpath + ".exe"
                found = os.path.isfile(fpath) and os.access(fpath, os.X_OK)
            return found

        fpath, __ = os.path.split(program)
        if fpath:
            if is_exe(program):
                return program
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                path = path.strip('"')
                exe_file = os.path.join(path, program)
                if is_exe(exe_file):
                    return exe_file

        return None

    async def get_mean_volume(self, input_file: str):
        '''Gets the mean volume of the given audio file.'''
        log.debug('Calculating mean volume of %s', input_file)
        cmd = '"' + self.get('ffmpeg') + '" -i "' + input_file
        cmd += '" -af "volumedetect" -f null /dev/null'
        output = (await self.run_command(cmd)).decode("utf-8")

        mean_volume_matches = re.findall(r"mean_volume: ([\-\d\.]+) dB", output)
        mean_volume = float(mean_volume_matches[0] if mean_volume_matches else 0)
        max_volume_matches = re.findall(r"max_volume: ([\-\d\.]+) dB", output)
        max_volume = float(max_volume_matches[0] if max_volume_matches else 0)

        log.debug('Calculated mean volume as %s', mean_volume)
        return mean_volume, max_volume

    # noinspection PyShadowingBuiltins
    async def _really_download(self, *, perform_hash=False):
        log.info("Download started: %s", self.url)

        try:
            result = await self.playlist.downloader.extract_info(
                self.playlist.loop,
                self.url,
                download=True
            )
        except Exception as err:
            raise ExtractionError(err) from err

        log.info("Download complete: %s", self.url)

        if result is None:
            log.critical("YTDL has failed, everyone panic")
            raise ExtractionError("ytdl broke and hell if I know why")
            # What the fuck do I do now?

        self.filename = unhashed_fname = self.playlist.downloader.ytdl.prepare_filename(result)

        if perform_hash:
            # insert the 8 last characters of the file hash to the file name to ensure uniqueness
            self.filename = md5sum(unhashed_fname, 8).join('-.').join(unhashed_fname.rsplit('.', 1))
            if os.path.isfile(self.filename):
                # Oh bother it was actually there.
                os.unlink(unhashed_fname)
            else:
                # Move the temporary file to it's final location.
                os.rename(unhashed_fname, self.filename)

class StreamPlaylistEntry(BasePlaylistEntry):
    def __init__(self, playlist, url, title, *, destination=None, **meta):
        super().__init__(playlist, url, title, 0, **meta)
        self.destination = destination
        if self.destination:
            self.filename = self.destination

    def __json__(self):
        return self._enclose_json({
            'version': 1,
            'url': self.url,
            'filename': self.filename,
            'title': self.title,
            'destination': self.destination,
            'meta': {
                name: {
                    'type': obj.__class__.__name__,
                    'id': obj.id,
                    'name': obj.name
                } for name, obj in self.meta.items() if obj
            }
        })

    @classmethod
    def _deserialize(cls, data, playlist=None):
        assert playlist is not None, cls._bad('playlist')

        try:
            # TODO: version check
            url = data['url']
            title = data['title']
            destination = data['destination']
            filename = data['filename']
            meta = cls._get_meta(data, playlist)
            entry = cls(playlist, url, title, destination=destination, **meta)
            if not destination and filename:
                entry.filename = destination

            return entry
        except Exception as e:
            log.error("Could not load %s", cls.__name__, exc_info=e)

    # noinspection PyMethodOverriding
    async def _download(self, *, fallback=False):
        self._is_downloading = True

        url = self.destination if fallback else self.url

        try:
            result = await self.playlist.downloader.extract_info(self.playlist.loop, url, download=False)
        except Exception as e:
            if not fallback and self.destination:
                return await self._download(fallback=True)

            raise ExtractionError(e)
        else:
            self.filename = result['url']
            # I might need some sort of events or hooks or shit
            # for when ffmpeg inevitebly fucks up and i have to restart
            # although maybe that should be at a slightly lower level
        finally:
            self._is_downloading = False
