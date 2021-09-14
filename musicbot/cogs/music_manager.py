import logging

from discord.ext.commands import Context, command

from ..exceptions import CommandError
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class MusicManager(Cog):
    @command
    async def pause(self, context: Context):
        player = await self._get_player(context.channel)

        if player.is_paused:
            error_msg = self.str.get('cmd-pause-none', 'Player is not playing.')
            raise CommandError(error_msg, expire_in=30)

        player.pause()
        msg = self.str.get(
            'cmd-pause-reply',
            'Paused music in `{player.voice_client.channel.name}`'
        )
        await self.safe_send_message(context, msg)

    @command
    async def resume(self, context: Context):
        player = await self._get_player(context.channel)

        if player.is_playing:
            error_msg = self.str.get('cmd-resume-none', 'Player is not paused.')
            raise CommandError(error_msg, expire_in=30)

        player.resume()
        msg = self.str.get(
            'cmd-pause-reply',
            'Resumed music in `{player.voice_client.channel.name}`'
        )
        await self.safe_send_message(context, msg)

    @command
    async def shuffle(self, context: Context):
        player = await self._get_player(context.channel)
        player.playlist.shuffle()
        msg = self.str.get(
            'cmd-shuffle-reply',
            "Shuffled `{player.voice_client.channel.guild}`'s queue."
        )
        await self.safe_send_message(context, msg)

    @command
    async def clear(self, context: Context):
        player = await self._get_player(context.channel)
        player.playlist.clear()
        msg = self.str.get(
            'cmd-clear-reply',
            "Cleared `{player.voice_client.channel.guild}`'s queue"
        )
