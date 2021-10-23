'''Module containing logic for PlayerCog.'''
from os import path, makedirs
import logging

from discord import Object, Game, Guild

from ..exceptions import CommandError
from ..player import MusicPlayer
from ..playlist import Playlist
from ..utils import _func_
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class PlayerCog(Cog):
    '''Cog in charge of managing the player class.'''
    last_status = None
    players = {}

    async def deserialize_queue(
        self,
        guild,
        playlist=None,
        *,
        filepath=None
    ) -> MusicPlayer:
        """
        Deserialize a saved queue for a server into a MusicPlayer. If no queue
        is saved, returns None.
        """

        if playlist is None:
            playlist = Playlist(self.bot)

        if filepath is None:
            filepath = 'data/%s/queue.json' % guild.id

        if not path.isfile(filepath):
            return None

        async with self.aiolocks['queue_serialization' + ':' + str(guild.id)]:
            log.debug("Deserializing queue for %s", guild.id)

            with open(filepath, 'r', encoding='utf8') as file:
                # TODO: Acutally use the data by doing other stuff
                data = file.read()

        return MusicPlayer(self.bot.loop)

    async def _init_player(self):
        player = MusicPlayer(self.bot.loop)

    async def get_player(self, channel, create=False, *, deserialize=False) -> MusicPlayer:
        '''
        Gets player by either of the following ways:
        * Fetching a cached player
        * Deserializing a player of a previous session
        * Creating a new player
        '''
        guild = channel.guild

        if guild.id in self.players:
            log.debug('Used cached player')
            return self.players[guild.id]

        async with self.aiolocks[_func_() + ':' + str(guild.id)]:
            if deserialize:
                player = await self.deserialize_queue(guild)

                if player:
                    log.debug(
                        'Created player via de-serialization for guild %s with %s entries',
                        guild.id,
                        len(player.playlist)
                    )
                    # Since deserializing only happens when the bot starts,
                    # I should never need to reconnect
                    return player

            if not create:
                raise CommandError(
                    'The bot is not in a voice channel.  '
                    'Use %ssummon to summon it to your voice channel.' % self.config.command_prefix)

            log.debug('Will create new player')

            return self._init_player()


    def get_player_in(self, guild: Guild) -> MusicPlayer:
        '''Gets the MusicPlayer that is playing in the given guild.'''
        return self.players.get(guild.id)

    async def serialize_queue(self, guild):
        """Serialize the current queue for a server's player to json."""

        player = self.get_player_in(guild)
        if not player:
            return

        directory = path.join('data', str(guild.id))
        makedirs(directory, exist_ok=True)

        filepath = path.join(directory, 'queue.json')

        async with self.aiolocks['queue_serialization' + ':' + str(guild.id)]:
            log.debug("Serializing queue for %s", guild.id)

            with open(filepath, 'w', encoding='utf8') as file:
                file.write(player.serialize(sort_keys=True))

    async def write_current_song(self, guild, entry, *, directory=None):
        """Writes the current song to file."""
        player = self.get_player_in(guild)
        if not player:
            return

        if directory is None:
            directory = 'data/%s/current.txt' % guild.id

        async with self.aiolocks['current_song' + ':' + str(guild.id)]:
            log.debug("Writing current song for %s", guild.id)

            with open(directory, 'w', encoding='utf8') as file:
                file.write(entry.title)
