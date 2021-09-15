'''Module containing logic and class for the main interface of the MusicBot'''
from collections import defaultdict
import asyncio
import logging
import sys
import traceback

import aiohttp
import colorlog

from discord import Intents
from discord.ext.commands import Bot, CommandError, CommandInvokeError, Context
from dislash import InteractionClient

from .aliases import Aliases, AliasesDefault
from .config import Config, ConfigDefaults
from .constants import VERSION as BOTVERSION
from .downloader import Downloader
from .exceptions import MusicbotException, TerminateSignal
from .json import Json
from .opus_loader import load_opus_lib
from .permissions import Permissions, PermissionsDefaults
from .utils import load_file
from .cogs import COGS

# from . import exceptions
# from .entry import StreamPlaylistEntry
# from .constructs import SkipState, Response
# from .constants import DISCORD_MSG_CHAR_LIMIT, AUDIO_CACHE_PATH

load_opus_lib()

log = logging.getLogger(__name__)

class MusicBot(Bot):
    '''Main class for the music bot'''

    def __init__(self):
        sys.stdout.write("\x1b]2;MusicBot {}\x07\n".format(BOTVERSION))

        config_file = ConfigDefaults.options_file
        perms_file = PermissionsDefaults.perms_file
        aliases_file = AliasesDefault.aliases_file

        self.config = Config(config_file)

        super().__init__(
            command_prefix=self.config.command_prefix,
            intents=Intents.default()
        )

        self._setup_logging()

        self.permissions = Permissions(perms_file, grant_all=[self.config.owner_id])
        self.str = Json(self.config.i18n_file)

        if self.config.usealias:
            self.aliases = Aliases(aliases_file)

        self.blacklist = set(load_file(self.config.blacklist_file))
        self.autoplaylist = load_file(self.config.auto_playlist_file)

        self.aiolocks = defaultdict(asyncio.Lock)
        self.downloader = Downloader(download_folder='audio_cache')

        # TODO: Do these properly
        ssd_defaults = {
            'last_np_msg': None,
            'auto_paused': False,
            'availability_paused': False
        }
        self.server_specific_data = defaultdict(ssd_defaults.copy)

        self.aiosession = aiohttp.ClientSession(loop=self.loop)
        self.http.user_agent += ' MusicBot/%s' % BOTVERSION

        for cog_class in COGS:
            self.add_cog(cog_class(self))

        InteractionClient(self, test_guilds=list(self.config.servers))

    def _setup_logging(self):
        if len(logging.getLogger(__package__).handlers) > 1:
            log.debug("Skipping logger setup, already set up")
            return

        shandler = logging.StreamHandler(stream=sys.stdout)
        shandler.setFormatter(colorlog.LevelFormatter(
            fmt = {
                'DEBUG': '{log_color}[{levelname}:{module}] {message}',
                'INFO': '{log_color}{message}',
                'WARNING': '{log_color}{levelname}: {message}',
                'ERROR': '{log_color}[{levelname}:{module}] {message}',
                'CRITICAL': '{log_color}[{levelname}:{module}] {message}',

                'EVERYTHING': '{log_color}[{levelname}:{module}] {message}',
                'NOISY': '{log_color}[{levelname}:{module}] {message}',
                'VOICEDEBUG': '{log_color}[{levelname}:{module}][{relativeCreated:.9f}] {message}',
                'FFMPEG': '{log_color}[{levelname}:{module}][{relativeCreated:.9f}] {message}'
            },
            log_colors = {
                'DEBUG':    'cyan',
                'INFO':     'white',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'bold_red',

                'EVERYTHING': 'white',
                'NOISY':      'white',
                'FFMPEG':     'bold_purple',
                'VOICEDEBUG': 'purple',
        },
            style = '{',
            datefmt = ''
        ))
        shandler.setLevel(self.config.debug_level)
        logging.getLogger(__package__).addHandler(shandler)

        log.debug('Set logging level to %s', self.config.debug_level_str)

        if self.config.debug_mode:
            dlogger = logging.getLogger('discord')
            dlogger.setLevel(logging.DEBUG)
            dhandler = logging.FileHandler(filename='logs/discord.log', encoding='utf-8', mode='w')
            dhandler.setFormatter(
                logging.Formatter('{asctime}:{levelname}:{name}: {message}', style='{'))
            dlogger.addHandler(dhandler)

    async def on_command_error(self, context: Context, exception: CommandError):
        messenger_cog = self.get_cog('MessengerCog')
        if messenger_cog is None:
            raise ValueError('MessengerCog is missing')
        if isinstance(exception, CommandInvokeError):
            exception = exception.original
        expire_in = 0
        if isinstance(exception, (MusicbotException)):
            expire_in = exception.expire_in
        else:
            traceback.print_exception(
                type(exception),
                exception,
                exception.__traceback__,
                file=sys.stderr,
            )
        return await messenger_cog.safe_send_message(context, exception, expire_in=expire_in)

    def run(self):
        super().run(self.config._login_token)
