import logging

from discord.ext.commands import Context, command

from ..exceptions import CommandError
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class MusicManager(Cog):
    @command
    async def pause(self, context: Context):
        player_cog = self.get_player_cog()
        player = await player_cog.get_player(context.channel)

        if not player.is_playing:
            error_msg = self.str.get('cmd-pause-none', 'Player is not playing.')
            raise CommandError(error_msg, expire_in=30)

        player.pause()
        msg = self.str.get(
            'cmd-pause-reply',
            'Paused music in `{player.voice_client.channel.name}`'
        )
        await self.safe_send_message(context, msg)
