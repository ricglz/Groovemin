'''Module containing SpecialPlayCog'''
import logging

from discord.ext.commands import Context
from dislash import command

from ..exceptions import CommandError
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class SpecialPlayCog(Cog):
    '''Class of Cog in charge of the special play commands (play_weeb, play_normie and play_all)'''
    async def _play_playlist(self, context, playlist: str):
        await self._get_cog('PlayCog')._play(context, playlist, shuffle=True)

    async def _play_weeb(self, context: Context):
        playlist = self.config.weeb_playlist
        if playlist is None or playlist == '':
            raise CommandError('There is no weeb playlist stored')
        await self._play_playlist(context, playlist)

    @command(description='Plays weeb playlist')
    async def play_weeb(self, context: Context):
        '''Plays the weeb playlist'''
        await self._play_weeb(context)

    async def _play_normie(self, context: Context):
        playlist = self.config.normie_playlist
        if playlist is None or playlist == '':
            raise CommandError('There is no normie playlist stored')
        await self._play_playlist(context, playlist)

    @command(description='Plays normie playlist')
    async def play_normie(self, context: Context):
        ''''Plays normie playlist'''
        await self._play_normie(context)

    @command(description='Plays both, normie and weeb, playlists')
    async def play_all(self, context: Context):
        '''Plays both, normie and weeb, playlists'''
        await self._play_weeb(context)
        await self._play_normie(context)
        await self._get_cog('MusicManagerCog').shuffle(context)
