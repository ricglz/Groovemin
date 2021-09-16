import logging

from discord.ext.commands import Context
from dislash import command

from ..exceptions import CommandError
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class SpecialPlayCog(Cog):
    async def _play_weeb(self, context: Context):
        playlist = self.config.weeb_playlist
        if playlist is None or playlist == '':
            raise CommandError('There is no weeb playlist stored')
        await self._get_cog('PlayCog')._play(context, playlist, shuffle=True)

    @command(description='Plays weeb playlist')
    async def play_weeb(self, context: Context):
        await self._play_weeb(context)

    async def _play_normie(self, context: Context):
        playlist = self.config.normie_playlist
        if playlist is None or playlist == '':
            raise CommandError('There is no normie playlist stored')
        await self._get_cog('PlayCog')._play(context, playlist, shuffle=True)

    @command(description='Plays normie playlist')
    async def play_normie(self, context: Context):
        await self._play_normie(context)

    @command(description='Plays both, normie and weeb, playlists')
    async def play_all(self, context: Context):
        await self._play_weeb(context)
        await self._play_normie(context)
        await self._get_cog('MusicManagerCog').shuffle(context)
