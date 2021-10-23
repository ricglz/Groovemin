'''Custom Cog module'''
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from discord import Guild
from discord.ext.commands import Cog

from ..player import MusicPlayer

if TYPE_CHECKING:
    from ..bot import MusicBot
    from .messenger import MessengerCog
    from .player import PlayerCog

@dataclass
class CustomCog(Cog):
    '''
    Auxiliar class for other cog classes as it contains helper attributes
    functions shared between them
    '''
    bot: MusicBot

    @property
    def voice_clients(self):
        '''Voice clients where the bot is allowed'''
        return self.bot.voice_clients

    @property
    def str(self):
        return self.bot.str

    @property
    def config(self):
        return self.bot.config

    @property
    def aiolocks(self):
        return self.bot.aiolocks

    @property
    def permissions(self):
        return self.bot.permissions

    @property
    def server_specific_data(self):
        return self.bot.server_specific_data

    @property
    def autoplaylist(self):
        return self.bot.autoplaylist

    async def check_last_msg(self, guild: Guild):
        '''
        Checks the last message send to the specified guild, if it exists then
        it will be deleted.
        '''
        if not self.config.delete_nowplaying:
            return
        last_np_msg = self.server_specific_data[guild]['last_np_msg']
        if last_np_msg is None:
            return
        await self.safe_delete_message(last_np_msg)
        self.server_specific_data[guild]['last_np_msg'] = None

    def _get_cog(self, cog_name: str):
        cog = self.bot.get_cog(cog_name)
        if cog is None:
            raise ValueError(f'{cog_name} is missing')
        return cog

    def _get_messenger_cog(self) -> MessengerCog:
        return self._get_cog('MessengerCog')

    def _get_player_cog(self) -> PlayerCog:
        return self._get_cog('PlayerCog')

    async def safe_send_message(self, dest, content, **kwargs):
        '''Send messages to the specified destination'''
        return await self._get_messenger_cog().safe_send_message(dest, content, **kwargs)

    async def safe_delete_message(self, message, *, quiet=False):
        '''Deletes a sent message'''
        return await self._get_messenger_cog().safe_delete_message(message, quiet=quiet)

    async def _get_player(self, channel) -> MusicPlayer:
        return await self._get_player_cog().get_player(channel)
