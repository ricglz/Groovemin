'''Custom Cog module'''
from dataclasses import dataclass
from typing import Optional

from discord.abc import GuildChannel
from discord.ext.commands import Bot, Cog

from ..config import Config
from ..player import MusicPlayer

@dataclass
class CustomCog(Cog):
    bot: Bot

    @property
    def voice_clients(self):
        '''Voice clients where the bot is allowed'''
        return self.bot.voice_clients

    @property
    def str(self):
        return self.bot.str

    @property
    def config(self) -> Config:
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

    @property
    def downloader(self):
        return self.bot.downloader

    @staticmethod
    def _check_if_empty(v_channel: GuildChannel, *, excluding_me=True, excluding_deaf=False):
        def check(member):
            if excluding_me and member == v_channel.guild.me:
                return False

            if excluding_deaf and any([member.deaf, member.self_deaf]):
                return False

            if member.bot:
                return False

            return True

        return not sum(1 for m in v_channel.members if check(m))

    def _get_cog(self, cog_name: str):
        cog = self.bot.get_cog(cog_name)
        if cog is None:
            raise ValueError(f'{cog_name} is missing')
        return cog

    def _get_messenger_cog(self):
        return self._get_cog('MessengerCog')

    async def safe_send_message(self, dest, content, **kwargs):
        messenger_cog = self._get_messenger_cog()
        return await messenger_cog.safe_send_message(dest, content, **kwargs)

    async def safe_delete_message(self, message, *, quiet=False):
        messenger_cog = self._get_messenger_cog()
        return await messenger_cog.safe_delete_message(message, quiet=quiet)

    def get_player_cog(self):
        return self._get_cog('PlayerCog')

    async def _get_player(self, channel) -> MusicPlayer:
        return await self.get_player_cog().get_player(channel)
