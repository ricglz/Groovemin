from typing import Optional
import logging

from discord.ext.commands import Context, command

from ..exceptions import CommandError, PermissionsError
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
        await self.safe_send_message(context, msg)

    @command
    async def remove(self, context: Context, index: Optional[str]=None):
        player = await self._get_player(context.channel)
        if not player.playlist.entries:
            error_msg = self.str.get('cmd-remove-none', "There's nothing to remove!")
            raise CommandError(error_msg, expire_in=20)
        if not index:
            index = len(player.playlist.entries)

        error_msg = self.str.get(
            'cmd-remove-invalid',
            f'Invalid number. Use {self.config.command_prefix}queue to find queue positions.'
        )
        invalid_number_error = CommandError(error_msg, expire_in=20)
        try:
            index = int(index)
        except (TypeError, ValueError) as err:
            raise invalid_number_error from err

        if index > len(player.playlist.entries):
            raise invalid_number_error

        author = context.author
        permissions = self.permissions.for_user(author)
        entry_author = player.playlist.get_entry_at_index(index - 1).meta.get('author', None)
        is_allowed = permissions.remove or author == entry_author
        if not is_allowed:
            error_msg = self.str.get(
                'cmd-remove-noperms',
                "You do not have the valid permissions to remove that entry from the queue, make"
                " sure you're the one who queued it or have instant skip permissions"
            )
            raise PermissionsError(error_msg, expire_in=20)

        entry = player.playlist.delete_entry_at_index((index - 1))
        if entry.meta.get('channel', False) and entry.meta.get('author', False):
            response_msg = self.str.get(
                'cmd-remove-reply-author',
                "Removed entry `{0}` added by `{1}`"
            ).format(entry.title, entry.meta['author'].name)
        else:
            response_msg = self.str.get(
                'cmd-remove-reply-noauthor',
                "Removed entry `{0}`"
            ).format(entry.title)
        response_msg = response_msg.strip()
        self.safe_send_message(context, response_msg)
