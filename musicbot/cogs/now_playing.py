'''NowPlaying Cog module'''
from datetime import timedelta
import logging

from discord import Guild
from discord.ext.commands import Context
from dislash import command

from ..exceptions import CommandError
from ..playlist import StreamPlaylistEntry
from ..utils import ftimedelta
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class NowPlayingCog(Cog):
    '''Cog class in charge of the now_playing command'''
    async def check_last_msg(self, guild: Guild):
        '''
        Checks the last message send to the specified guild, if it exists then
        it will be deleted.
        '''
        last_np_msg = self.server_specific_data[guild]['last_np_msg']
        if last_np_msg is None:
            return
        await self.safe_delete_message(last_np_msg)
        self.server_specific_data[guild]['last_np_msg'] = None

    def get_prog_bar(self, player, streaming: bool):
        '''Gets the progress related strings'''
        # TODO: Fix timedelta garbage with util function
        song_progress = ftimedelta(timedelta(seconds=player.progress))
        song_total = ftimedelta(timedelta(seconds=player.current_entry.duration))

        prog_str = ('`[{progress}]`' if streaming else '`[{progress}/{total}]`').format(
            progress=song_progress, total=song_total
        )

        # percentage shows how much of the current song has already been played
        percentage = 0 if player.current_entry.duration == 0 \
                     else player.progress / player.current_entry.duration

        # create the actual bar
        progress_bar_length = 30
        prog_bar_str = ''
        for i in range(progress_bar_length):
            prog_bar_str += '□' if percentage < 1 / progress_bar_length * i else '■'

        return prog_str, prog_bar_str

    @command(
        description='Sends message specifying which entry is currently playing and how long it will last'
    )
    async def now_playing(self, context: Context):
        '''Sends message specifying which entry is currently playing and how long it will last'''
        player = await self._get_player(context.channel)
        if not player.current_entry:
            error_msg = self.str.get(
                'cmd-np-none',
                'There are no songs queued! Queue something with {0}play.'
            ).format(self.config.command_prefix)
            raise CommandError(error_msg, expire_in=30)

        guild: Guild = context.guild
        await self.check_last_msg(guild)

        streaming = isinstance(player.current_entry, StreamPlaylistEntry)
        prog_str, prog_bar_str = self.get_prog_bar(player, streaming)

        action_text = self.str.get('cmd-np-action-streaming', 'Streaming') if streaming \
                      else self.str.get('cmd-np-action-playing', 'Playing')

        author_is_known = player.current_entry.meta.get('channel', False) and \
                          player.current_entry.meta.get('author', False)
        if author_is_known:
            np_text = self.str.get(
                'cmd-np-reply-author',
                "Now {action}: **{title}** added by **{author}**\nProgress: {progress_bar} "
                "{progress}\n\N{WHITE RIGHT POINTING BACKHAND INDEX} <{url}>"
            ).format(
                action=action_text,
                title=player.current_entry.title,
                author=player.current_entry.meta['author'].name,
                progress_bar=prog_bar_str,
                progress=prog_str,
                url=player.current_entry.url
            )
        else:
            np_text = self.str.get(
                'cmd-np-reply-noauthor',
                "Now {action}: **{title}**\nProgress: {progress_bar} {progress}"
                "\n\N{WHITE RIGHT POINTING BACKHAND INDEX} <{url}>"
            ).format(
                action=action_text,
                title=player.current_entry.title,
                progress_bar=prog_bar_str,
                progress=prog_str,
                url=player.current_entry.url
            )

        self.server_specific_data[guild]['last_np_msg'] = \
            await self.safe_send_message(context, np_text)
