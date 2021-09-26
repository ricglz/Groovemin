'''Module containing logic for config file.'''
from configparser import ConfigParser as BaseConfigParser
import codecs
import logging
import os
import shutil
import sys

from .exceptions import HelpfulError

log = logging.getLogger(__name__)

_CONFPREFACE = "An error has occurred reading the config:\n"
_CONFPREFACE2 = "An error has occurred validating the config:\n"

class ConfigParser(BaseConfigParser):
    '''Improved version of BaseConfigParser that can parse sets.'''
    @staticmethod
    def str_to_list(string_value):
        '''Parses a string of elements into a list.'''
        return string_value.replace(',', ' ').split()

    def get_set(self, section: str, option: str, *, raw=False, vars=None, fallback=None):
        '''Gets a set for the given section and option.'''
        option_value = self.get(section, option, raw=raw, vars=vars, fallback=fallback)
        if option_value is None:
            return set()
        return set(self.str_to_list(option_value))

    def get_int_set(self, section: str, option: str, *, raw=False, vars=None, fallback=None):
        '''
        Gets a set for the given section and option, the values of the set will be cast to int.
        '''
        option_set = self.get_set(section, option, raw=raw, vars=vars, fallback=fallback)
        try:
            return set(int(value) for value in option_set)
        except ValueError:
            log.warning('%s data is invalid, will ignore.', option)
            return set()

def check_confsections(config: ConfigParser):
    '''Checks that the known sections of the config file are indeed in it.'''
    confsections = {"Credentials", "Permissions", "Chat", "MusicBot"}.difference(config.sections())
    if confsections:
        raise HelpfulError(
            "One or more required config sections are missing.",
            "Fix your config.  Each [Section] should be on its own line with "
            "nothing else on it.  The following sections are missing: {}".format(
                ', '.join(['[%s]' % s for s in confsections])
            ),
            preface="An error has occurred parsing the config:\n"
        )

class SectionConfig:
    '''Abstract class for classes containing the values of specific sections.'''
    def run_checks(self):
        '''Checks that the values are valid.'''

    def async_validate(self, bot):
        '''Permons an async validation of the values.'''

class CredentialsConfig(SectionConfig):
    '''Class containing config data of the `Credentials` section'''
    auth = ()

    def __init__(self, config: ConfigParser):
        self._login_token = config.get('Credentials', 'Token', fallback=ConfigDefaults.token)
        self.spotify_clientid = config.get(
            'Credentials', 'Spotify_ClientID', fallback=ConfigDefaults.spotify_clientid
        )
        self.spotify_clientsecret = config.get(
            'Credentials', 'Spotify_ClientSecret', fallback=ConfigDefaults.spotify_clientsecret
        )
        self._spotify = self.spotify_clientid and self.spotify_clientsecret

    def run_checks(self):
        '''Checks that the values are valid.'''
        if not self._login_token:
            raise HelpfulError(
                "No bot token was specified in the config.",
                "As of v1.9.6_1, you are required to use a Discord bot account. "
                "See https://github.com/Just-Some-Bots/MusicBot/wiki/FAQ for info.",
                preface=_CONFPREFACE
            )
        self.auth = (self._login_token,)

class PlaylistsConfig(SectionConfig):
    '''Class containing config data of the `Playlists` section'''
    def __init__(self, config: ConfigParser):
        self.normie_playlist = config.get(
            'Playlists', 'NormiePlaylist', fallback=ConfigDefaults.normie_playlist
        )
        self.weeb_playlist = config.get(
            'Playlists', 'WeebPlaylist', fallback=ConfigDefaults.weeb_playlist
        )

class PermissionsConfig(SectionConfig):
    '''Class containing config data of the `Permissions` section'''
    def __init__(self, config: ConfigParser):
        self.owner_id = config.get('Permissions', 'OwnerID', fallback=ConfigDefaults.owner_id)
        self.dev_ids = config.get('Permissions', 'DevIDs', fallback=ConfigDefaults.dev_ids)
        self.bot_exception_ids = config.get_int_set(
            "Permissions", "BotExceptionIDs", fallback=ConfigDefaults.bot_exception_ids
        )

    def run_checks(self):
        '''Checks that the values are valid.'''
        if self.owner_id:
            self.owner_id = self.owner_id.lower()
            if self.owner_id.isdigit():
                if int(self.owner_id) < 10000:
                    raise HelpfulError(
                        "An invalid OwnerID was set: {}".format(self.owner_id),
                        "Correct your OwnerID. The ID should be just a number, approximately 18 "
                        "characters long, or 'auto'. If you don't know what your ID is, read the "
                        "instructions in the options or ask in the help server.",
                        preface=_CONFPREFACE
                    )
                self.owner_id = int(self.owner_id)
            elif self.owner_id == 'auto':
                pass # defer to async check
            else:
                self.owner_id = None
        if not self.owner_id:
            raise HelpfulError(
                "No OwnerID was set.",
                "Please set the OwnerID option in the config file",
                preface=_CONFPREFACE
            )

    def async_validate(self, bot):
        '''Permons an async validation of the values.'''
        if self.owner_id == 'auto':
            if not bot.user.bot:
                raise HelpfulError(
                    "Invalid parameter \"auto\" for OwnerID option.",

                    "Only bot accounts can use the \"auto\" option.  Please "
                    "set the OwnerID in the config.",

                    preface=_CONFPREFACE2
                )

            self.owner_id = bot.cached_app_info.owner.id
            log.debug("Acquired owner id via API")

        if self.owner_id == bot.user.id:
            raise HelpfulError(
                "Your OwnerID is incorrect or you've used the wrong credentials.",

                "The bot's user ID and the id for OwnerID is identical. "
                "This is wrong. The bot needs a bot account to function, "
                "meaning you cannot use your own account to run the bot on. "
                "The OwnerID is the id of the owner, not the bot. "
                "Figure out which one is which and use the correct information.",

                preface=_CONFPREFACE2
            )

class ChatConfig(SectionConfig):
    '''Class containing config data of the `Chat` section'''
    def __init__(self, config: ConfigParser):
        self.command_prefix = config.get(
            'Chat', 'CommandPrefix', fallback=ConfigDefaults.command_prefix
        )
        self.bound_channels = config.get_int_set(
            'Chat', 'BindToChannels', fallback=ConfigDefaults.bound_channels
        )
        self.servers = config.get_int_set(
            'Chat', 'Servers', fallback=ConfigDefaults.servers
        )
        self.unbound_servers = config.getboolean(
            'Chat', 'AllowUnboundServers', fallback=ConfigDefaults.unbound_servers
        )
        self.autojoin_channels =  config.get_int_set(
            'Chat', 'AutojoinChannels', fallback=ConfigDefaults.autojoin_channels
        )
        self.dm_nowplaying = config.getboolean(
            'Chat', 'DMNowPlaying', fallback=ConfigDefaults.dm_nowplaying
        )
        self.no_nowplaying_auto = config.getboolean(
            'Chat', 'DisableNowPlayingAutomatic', fallback=ConfigDefaults.no_nowplaying_auto
        )
        self.nowplaying_channels =  config.get_int_set(
            'Chat', 'NowPlayingChannels', fallback=ConfigDefaults.nowplaying_channels
        )
        self.delete_nowplaying = config.getboolean(
            'Chat', 'DeleteNowPlaying', fallback=ConfigDefaults.delete_nowplaying
        )

class MusicBotConfig(SectionConfig):
    '''Class containing config data of the `MusicBot` section'''
    debug_mode = False

    def __init__(self, config: ConfigParser):
        self.default_volume = config.getfloat(
            'MusicBot', 'DefaultVolume', fallback=ConfigDefaults.default_volume
        )
        self.skips_required = config.getint(
            'MusicBot', 'SkipsRequired', fallback=ConfigDefaults.skips_required
        )
        self.skip_ratio_required = config.getfloat(
            'MusicBot', 'SkipRatio', fallback=ConfigDefaults.skip_ratio_required
        )
        self.save_videos = config.getboolean(
            'MusicBot', 'SaveVideos', fallback=ConfigDefaults.save_videos
        )
        self.now_playing_mentions = config.getboolean(
            'MusicBot', 'NowPlayingMentions', fallback=ConfigDefaults.now_playing_mentions
        )
        self.auto_summon = config.getboolean(
            'MusicBot', 'AutoSummon', fallback=ConfigDefaults.auto_summon
        )
        self.auto_playlist = config.getboolean(
            'MusicBot', 'UseAutoPlaylist', fallback=ConfigDefaults.auto_playlist
        )
        self.auto_playlist_random = config.getboolean(
            'MusicBot', 'AutoPlaylistRandom', fallback=ConfigDefaults.auto_playlist_random
        )
        self.auto_pause = config.getboolean(
            'MusicBot', 'AutoPause', fallback=ConfigDefaults.auto_pause
        )
        self.delete_messages = config.getboolean(
            'MusicBot', 'DeleteMessages', fallback=ConfigDefaults.delete_messages
        )
        self.delete_invoking = config.getboolean(
            'MusicBot', 'DeleteInvoking', fallback=ConfigDefaults.delete_invoking
        )
        self.persistent_queue = config.getboolean(
            'MusicBot', 'PersistentQueue', fallback=ConfigDefaults.persistent_queue
        )
        self.status_message = config.get(
            'MusicBot', 'StatusMessage', fallback=ConfigDefaults.status_message
        )
        self.write_current_song = config.getboolean(
            'MusicBot', 'WriteCurrentSong', fallback=ConfigDefaults.write_current_song
        )
        self.allow_author_skip = config.getboolean(
            'MusicBot', 'AllowAuthorSkip', fallback=ConfigDefaults.allow_author_skip
        )
        self.use_experimental_equalization = config.getboolean(
            'MusicBot',
            'UseExperimentalEqualization',
            fallback=ConfigDefaults.use_experimental_equalization
        )
        self.embeds = config.getboolean(
            'MusicBot', 'UseEmbeds', fallback=ConfigDefaults.embeds
        )
        self.queue_length = config.getint(
            'MusicBot', 'QueueLength', fallback=ConfigDefaults.queue_length
        )
        self.remove_ap = config.getboolean(
            'MusicBot', 'RemoveFromAPOnError', fallback=ConfigDefaults.remove_ap
        )
        self.show_config_at_start = config.getboolean(
            'MusicBot', 'ShowConfigOnLaunch', fallback=ConfigDefaults.show_config_at_start
        )
        self.legacy_skip = config.getboolean(
            'MusicBot', 'LegacySkip', fallback=ConfigDefaults.legacy_skip
        )
        self.leavenonowners = config.getboolean(
            'MusicBot', 'LeaveServersWithoutOwner', fallback=ConfigDefaults.leavenonowners
        )
        self.usealias = config.getboolean('MusicBot', 'UseAlias', fallback=ConfigDefaults.usealias)
        self.debug_level = config.get('MusicBot', 'DebugLevel', fallback=ConfigDefaults.debug_level)
        self.debug_level_str = self.debug_level

    def run_checks(self):
        '''Checks that the values are valid.'''
        self.delete_invoking = self.delete_invoking and self.delete_messages

        if hasattr(logging, self.debug_level.upper()):
            self.debug_level = getattr(logging, self.debug_level.upper())
        else:
            log.warning(
                'Invalid DebugLevel option "%s" given, falling back to INFO',
                self.debug_level_str
            )
            self.debug_level = logging.INFO
            self.debug_level_str = 'INFO'

        self.debug_mode = self.debug_level <= logging.DEBUG

class FilesConfig(SectionConfig):
    '''Class containing config data of the `Files` section'''
    auto_playlist_removed_file = None

    def __init__(self, config: ConfigParser):
        self.blacklist_file = config.get(
            'Files', 'BlacklistFile', fallback=ConfigDefaults.blacklist_file
        )
        self.auto_playlist_file = config.get(
            'Files', 'AutoPlaylistFile', fallback=ConfigDefaults.auto_playlist_file
        )
        self.i18n_file = config.get('Files', 'i18nFile', fallback=ConfigDefaults.i18n_file)

    def run_checks(self):
        '''Checks that the values are valid.'''
        if self.i18n_file != ConfigDefaults.i18n_file and not os.path.isfile(self.i18n_file):
            log.warning(
                'i18n file does not exist. Trying to fallback to %s.', ConfigDefaults.i18n_file
            )
            self.i18n_file = ConfigDefaults.i18n_file
        if not os.path.isfile(self.i18n_file):
            raise HelpfulError(
                "Your i18n file was not found, and we could not fallback.",
                "As a result, the bot cannot launch. Have you moved some files? "
                "Try pulling the recent changes from Git, or resetting your local repo.",
                preface=_CONFPREFACE
            )
        log.info('Using i18n: %s', self.i18n_file)

        ap_path, ap_name = os.path.split(self.auto_playlist_file)
        apn_name, apn_ext = os.path.splitext(ap_name)
        self.auto_playlist_removed_file = os.path.join(ap_path, apn_name + '_removed' + apn_ext)

class Config:
    '''Main file for managing the configuration of the bot'''
    missing_keys = set()

    def __init__(self, config_file):
        self.config_file = config_file
        config = self.find_config()

        self.configs = [
            CredentialsConfig(config),
            PlaylistsConfig(config),
            PermissionsConfig(config),
            ChatConfig(config),
            MusicBotConfig(config),
            FilesConfig(config),
        ]

        self.run_checks()
        self.check_changes(config)
        self.find_autoplaylist()

    def __getattribute__(self, name: str):
        for config_class in self.configs:
            if hasattr(config_class, name):
                return config_class.__getattribute__(name)
        raise AttributeError(f'Config does not have {name} attribute')

    @staticmethod
    def get_all_keys(conf):
        """Returns all config keys as a list"""
        sects = dict(conf.items())
        keys = []
        for k in sects:
            keys += list(sects[k].keys())
        return keys

    def check_changes(self, conf):
        exfile = 'config/example_options.ini'
        if os.path.isfile(exfile):
            usr_keys = self.get_all_keys(conf)
            exconf = ConfigParser(interpolation=None)
            if not exconf.read(exfile, encoding='utf-8'):
                return
            ex_keys = self.get_all_keys(exconf)
            if set(usr_keys) != set(ex_keys):
                # to raise this as an issue in bot.py later
                self.missing_keys = set(ex_keys) - set(usr_keys)

    def run_checks(self):
        '''Validation logic for bot settings.'''
        for config_class in self.configs:
            config_class.run_checks()
        self.create_empty_file_if_no_exist('config/blacklist.txt')
        self.create_empty_file_if_no_exist('config/whitelist.txt')

    @staticmethod
    def create_empty_file_if_no_exist(path):
        '''Creates an empty file in the case that it does not exist'''
        if not os.path.isfile(path):
            open(path, 'a', encoding='utf-8').close()
            log.warning('Creating %s', path)

    # TODO: Add save function for future editing of options with commands
    #       Maybe add warnings about fields missing from the config file

    async def async_validate(self, bot):
        '''Permons an async validation of the values.'''
        log.debug("Validating options...")
        for config_class in self.configs:
            config_class.async_validate(bot)

    def find_config(self):
        '''Finds the config file'''
        config = ConfigParser(interpolation=None)

        if not os.path.isfile(self.config_file):
            ini_file = self.config_file + '.ini'
            if os.path.isfile(ini_file):
                shutil.move(ini_file, self.config_file)
                log.info(
                    "Moving %s to %s, you should probably turn file extensions on.",
                    ini_file,
                    self.config_file
                )

            elif os.path.isfile('config/example_options.ini'):
                shutil.copy('config/example_options.ini', self.config_file)
                log.warning('Options file not found, copying example_options.ini')

            else:
                raise HelpfulError(
                    "Your config files are missing. Neither options.ini nor example_options.ini "
                    "were found.",
                    "Grab the files back from the archive or remake them yourself and copy paste "
                    "the content from the repo. Stop removing important files!"
                )

        if not config.read(self.config_file, encoding='utf-8'):
            config = ConfigParser()
            try:
                # load the config again and check to see if the user edited that one
                config.read(self.config_file, encoding='utf-8')

                if not int(config.get('Permissions', 'OwnerID', fallback=0)): # jake pls no flame
                    print(flush=True)
                    log.critical("Please configure config/options.ini and re-run the bot.")
                    sys.exit(1)

            # Config id value was changed but its not valid
            except ValueError as err:
                raise HelpfulError(
                    'Invalid value "{}" for OwnerID, config cannot be loaded. '.format(
                        config.get('Permissions', 'OwnerID', fallback=None)
                    ),
                    "The OwnerID option requires a user ID or 'auto'."
                ) from err

            except Exception as err:
                print(flush=True)
                log.critical(
                    "Unable to copy config/example_options.ini to %s",
                    self.config_file,
                    exc_info=err
                )
                sys.exit(2)

        config.read(self.config_file, encoding='utf-8')
        check_confsections(config)

        return config

    def find_autoplaylist(self):
        '''Finds auto_playlist file'''
        if not os.path.exists(self.auto_playlist_file):
            if os.path.exists('config/_autoplaylist.txt'):
                shutil.copy('config/_autoplaylist.txt', self.auto_playlist_file)
                log.debug("Copying _autoplaylist.txt to autoplaylist.txt")
            else:
                log.warning("No autoplaylist file found.")

class ConfigDefaults:
    '''Class containing the default values of the bot configuration'''
    owner_id = None

    token = None
    dev_ids = set()
    bot_exception_ids = set()

    spotify_clientid = None
    spotify_clientsecret = None

    normie_playlist = None
    weeb_playlist = None

    command_prefix = '!'
    bound_channels = set()
    servers = set()
    unbound_servers = False
    autojoin_channels = set()
    dm_nowplaying = False
    no_nowplaying_auto = False
    nowplaying_channels = set()
    delete_nowplaying = True

    default_volume = 0.15
    skips_required = 4
    skip_ratio_required = 0.5
    save_videos = True
    now_playing_mentions = False
    auto_summon = True
    auto_playlist = True
    auto_playlist_random = True
    auto_pause = True
    delete_messages = True
    delete_invoking = False
    persistent_queue = True
    debug_level = 'INFO'
    status_message = None
    write_current_song = False
    allow_author_skip = True
    use_experimental_equalization = False
    embeds = True
    queue_length = 10
    remove_ap = True
    show_config_at_start = False
    legacy_skip = False
    leavenonowners = False
    usealias = True

    options_file = 'config/options.ini'
    blacklist_file = 'config/blacklist.txt'
    auto_playlist_file = 'config/autoplaylist.txt'  # this will change when I add playlists
    i18n_file = 'config/i18n/en.json'

setattr(
    ConfigDefaults, codecs.decode(b'ZW1haWw=', '\x62\x61\x73\x65\x36\x34').decode('ascii'), None
)
setattr(
    ConfigDefaults, codecs.decode(b'cGFzc3dvcmQ=', '\x62\x61\x73\x65\x36\x34').decode('ascii'), None
)
setattr(
    ConfigDefaults, codecs.decode(b'dG9rZW4=', '\x62\x61\x73\x65\x36\x34').decode('ascii'), None
)
