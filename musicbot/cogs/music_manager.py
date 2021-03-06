'''Module containing MusicManagerCog.'''
from datetime import timedelta
from math import ceil
from typing import Optional
import logging

from discord.ext.commands import Context
from dislash import command, Option, OptionType

from ..constants import DISCORD_MSG_CHAR_LIMIT
from ..exceptions import CommandError, PermissionsError
from ..utils import ftimedelta
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class MusicManagerCog(Cog):
    '''
    Class in charge of managing the music commands aside from play.
    '''

    @command(description='Pauses the audio')
    async def pause(self, context: Context):
        '''Pauses the audio'''
        player = await self._get_player(context.channel)

        if player.is_paused:
            error_msg = self.str.get('cmd-pause-none', 'Player is not playing.')
            raise CommandError(error_msg, expire_in=30)

        player.pause()
        msg = self.str.get(
            'cmd-pause-reply', 'Paused music in `{0.name}`'
        ).format(player.voice_client.channel)
        await self.safe_send_message(context, msg)

    @command(description='Resumes the audio from where it stopped')
    async def resume(self, context: Context):
        '''Resumes the audio from where it stopped'''
        player = await self._get_player(context.channel)

        if player.is_playing:
            error_msg = self.str.get('cmd-resume-none', 'Player is not paused.')
            raise CommandError(error_msg, expire_in=30)

        player.resume()
        msg = self.str.get(
            'cmd-resume-reply',
            'Resumed music in `{0.name}`'
        ).format(player.voice_client.channel)
        await self.safe_send_message(context, msg)

    @command(description='Shuffles the queue')
    async def shuffle(self, context: Context):
        '''Shuffles the queue'''
        player = await self._get_player(context.channel)
        player.playlist.shuffle()
        msg = self.str.get(
            'cmd-shuffle-reply',
            "Shuffled `{0}`'s queue."
        ).format(player.voice_client.channel.guild)
        await self.safe_send_message(context, msg)

    @command(description='Remove all entries in the queue')
    async def clear(self, context: Context):
        '''Remove all entries in the queue'''
        player = await self._get_player(context.channel)
        player.playlist.clear()
        msg = self.str.get(
            'cmd-clear-reply',
            "Cleared `{0}`'s queue"
        ).format(player.voice_client.channel.guild)
        await self.safe_send_message(context, msg)

    @command(
        description='Removes a given entry of the queue, or removes the last one',
        options=[
            Option(
                'index',
                'Position of the entry in the queue',
                OptionType.INTEGER,
            )
        ]
    )
    async def remove(self, context: Context, index: Optional[str]=None):
        '''Removes a given entry of the queue, or removes the last one'''
        player_cog = self._get_player_cog()
        player = await player_cog.get_player(context.channel)
        if not player.playlist.entries:
            error_msg = self.str.get('cmd-remove-none', "There's nothing to remove!")
            raise CommandError(error_msg, expire_in=20)
        if not index:
            index = len(player.playlist.entries)

        error_msg = self.str.get(
            'cmd-remove-invalid',
            'Invalid number. Use {0}queue to find queue positions.'
        ).format(self.config.command_prefix)
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
        await player_cog.serialize_queue(player.voice_client.channel.guild)
        await self.safe_send_message(context, response_msg)

    def _is_playing_line(self, player):
        # TODO: Fix timedelta garbage with util function
        song_progress = ftimedelta(timedelta(seconds=player.progress))
        song_total = ftimedelta(timedelta(seconds=player.current_entry.duration))
        prog_str = '`[%s/%s]`' % (song_progress, song_total)

        if player.current_entry.meta.get('channel', False) and \
           player.current_entry.meta.get('author', False):
            return self.str.get(
                'cmd-queue-playing-author',
                "Currently playing: `{0}` added by `{1}` {2}\n"
            ).format(
                player.current_entry.title,
                player.current_entry.meta['author'].nae,
                prog_str
            )
        return self.str.get(
            'cmd-queue-playing-noauthor',
            "Currently playing: `{0}` {1}\n"
        ).format(player.current_entry.title, prog_str)

    def _get_next_line(self, i: int, item: object):
        if item.meta.get('channel', False) and item.meta.get('author', False):
            next_line = self.str.get(
                'cmd-queue-entry-author',
                '{0} -- `{1}` by `{2}`'
            ).format(i, item.title, item.meta['author'].name)
        else:
            next_line = self.str.get(
                'cmd-queue-entry-noauthor',
                '{0} -- `{1}`'
            ).format(i, item.title)
        return next_line.strip()

    @command(description='Displays a queue of the following entries')
    async def queue(self, context: Context):
        '''Displays a queue of the following entries'''
        player = await self._get_player(context.channel)
        lines = []
        unlisted = 0
        and_more_text = '* ... and %s more*' % ('x' * len(player.playlist.entries))

        if player.is_playing:
            lines.append(self._is_playing_line(player))

        current_line_sum = len(lines[0]) + 1 if player.is_playing else 0
        for i, item in enumerate(player.playlist, 1):
            next_line = self._get_next_line(i, item)
            potential_len = current_line_sum + len(next_line) + len(and_more_text)
            if potential_len > DISCORD_MSG_CHAR_LIMIT or \
               i > self.config.queue_length:
                if current_line_sum + len(and_more_text):
                    unlisted += 1
                    continue

            lines.append(next_line)
            current_line_sum += len(next_line) + 1

        if unlisted > 0:
            lines.append(self.str.get('cmd-queue-more', '\n... and %s more') % unlisted)

        if not lines:
            lines.append(
                self.str.get(
                    'cmd-queue-none',
                    'There are no songs queued! Queue something with {0}play.'
                ).format(self.config.command_prefix)
            )

        message = '\n'.join(lines)
        await self.safe_send_message(context, message)

    @command(description='Allows to skip the current song')
    async def skip(self, context: Context):
        '''Allows to skip the current song'''
        player = await self._get_player(context.channel)
        if player.is_stopped:
            error_msg = self.str.get('cmd-skip-none', "Can't skip! The player is not playing!")
            raise CommandError(error_msg, expire_in=20)

        if not player.current_entry:
            if player.playlist.peek():
                if player.playlist.peek()._is_downloading:
                    response_msg = self.str.get(
                        'cmd-skip-dl',
                        "The next song (`%s`) is downloading, please wait."
                    ) % player.playlist.peek().title
                    return await self.safe_send_message(context, response_msg)

                if player.playlist.peek().is_downloaded:
                    print("The next song will be played shortly. Please wait.")
                else:
                    print("Something odd is happening.  "
                          "You might want to restart the bot if it doesn't start working.")
            else:
                print("Something strange is happening.  "
                      "You might want to restart the bot if it doesn't start working.")

        current_entry = player.current_entry

        voice_channel = context.guild.me.voice.channel
        num_voice = sum(
            1 for m in voice_channel.members
              if not (m.voice.deaf or m.voice.self_deaf or m == self.bot.user)
        )

        # In case all users are deafened, to avoid division by zero
        if num_voice == 0:
            num_voice = 1

        # TODO: Check how to use this
        # num_skips = player.skip_state.add_skipper(context.author.id, context.message)
        num_skips = 1

        skips_remaining = min(
            self.config.skips_required,
            ceil(self.config.skip_ratio_required / (1 / num_voice))
        ) - num_skips

        if skips_remaining <= 0:
            # check autopause stuff here
            player.skip()
            extra_msg = self.str.get(
                'cmd-skip-reply-skipped-2',
                ' Next song coming up!'
            ) if player.playlist.peek() else ''
            response_msg = self.str.get(
                'cmd-skip-reply-skipped-1',
                'Your skip for `{0}` was acknowledged.\nThe vote to skip has been passed.{1}'
            ).format(current_entry.title, extra_msg)

        else:
            # TODO: When a song gets skipped, delete the old x needed to skip
            # messages
            extra_msg = self.str.get('cmd-skip-reply-voted-2', 'person is') \
                        if skips_remaining == 1 \
                        else self.str.get('cmd-skip-reply-voted-3', 'people are')
            response_msg = self.str.get(
                'cmd-skip-reply-voted-1',
                'Your skip for `{0}` was acknowledged.\n**{1}** more {2}'
                ' required to vote to skip this song.'
            ).format(
                current_entry.title,
                skips_remaining,
                extra_msg
            )

        await self.safe_send_message(context, response_msg)
