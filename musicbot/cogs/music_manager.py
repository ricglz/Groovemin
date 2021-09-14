from datetime import timedelta
from typing import Optional
import logging

from discord.ext.commands import Context, command

from ..constants import DISCORD_MSG_CHAR_LIMIT
from ..exceptions import CommandError, PermissionsError
from ..utils import ftimedelta
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

    @command
    async def queue(self, context: Context):
        player = self._get_player(context.channel)
        lines = []
        unlisted = 0
        andmoretext = '* ... and %s more*' % ('x' * len(player.playlist.entries))

        if player.is_playing:
            # TODO: Fix timedelta garbage with util function
            song_progress = ftimedelta(timedelta(seconds=player.progress))
            song_total = ftimedelta(timedelta(seconds=player.current_entry.duration))
            prog_str = '`[%s/%s]`' % (song_progress, song_total)

            if player.current_entry.meta.get('channel', False) and \
               player.current_entry.meta.get('author', False):
                line = self.str.get(
                    'cmd-queue-playing-author',
                    "Currently playing: `{0}` added by `{1}` {2}\n"
                ).format(
                    player.current_entry.title,
                    player.current_entry.meta['author'].nae,
                    prog_str
                )
            else:
                line = self.str.get(
                    'cmd-queue-playing-noauthor',
                    "Currently playing: `{0}` {1}\n"
                ).format(player.current_entry.title, prog_str)
            lines.append(line)

        currentlinesum = len(lines[0] + 1)
        for i, item in enumerate(player.playlist, 1):
            if item.meta.get('channel', False) and item.meta.get('author', False):
                nextline = self.str.get(
                    'cmd-queue-entry-author',
                    '{0} -- `{1}` by `{2}`'
                ).format(i, item.title, item.meta['author'].name)
            else:
                nextline = self.str.get(
                    'cmd-queue-entry-noauthor',
                    '{0} -- `{1}`'
                ).format(i, item.title)
            nextline.strip()

            potential_len = currentlinesum + len(nextline) + len(andmoretext)
            if (potential_len > DISCORD_MSG_CHAR_LIMIT) or \
               i > self.config.queue_length:
                if currentlinesum + len(andmoretext):
                    unlisted += 1
                    continue

            lines.append(nextline)
            currentlinesum = len(nextline) + 1

        if unlisted:
            lines.append(self.str.get('cmd-queue-more', '\n... and %s more') % unlisted)

        if not lines:
            lines.append(
                self.str.get(
                    'cmd-queue-none',
                    'There are no songs queued! Queue something with {}play.'
                ).format(self.config.command_prefix)
            )

        message = '\n'.join(lines)
        self.safe_send_message(context, message)
