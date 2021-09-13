from typing import Optional
import logging

from discord import Member, Guild
from discord.ext.commands import Context, command

from ..constructs import Response
from ..exceptions import CommandError
from .custom_cog import CustomCog as Cog
from .player import PlayerCog

log = logging.getLogger(__name__)

class SummonCog(Cog):
    def _voice_client_in(self, guild: Guild):
        for vc in self.voice_clients:
            if vc.guild == guild:
                return vc
        return None

    @command()
    async def summon(self, context: Context):
        author: Member = context.author

        if not author.voice:
            raise ValueError()

        guild: Guild = context.guild
        voice_client = self._voice_client_in(guild)

        if voice_client and guild == author.voice.channel.guild:
            await voice_client.move_to(author.voice.channel)
        else:
            # move to _verify_vc_perms?
            chperms = author.voice.channel.permissions_for(guild.me)

            if not chperms.connect:
                log.warning("Cannot join channel '{0}', no permission.".format(author.voice.channel.name))
                raise CommandError(
                    self.str.get('cmd-summon-noperms-connect', "Cannot join channel `{0}`, no permission to connect.").format(author.voice.channel.name),
                    expire_in=25
                )

            if not chperms.speak:
                log.warning("Cannot join channel '{0}', no permission to speak.".format(author.voice.channel.name))
                raise CommandError(
                    self.str.get('cmd-summon-noperms-speak', "Cannot join channel `{0}`, no permission to speak.").format(author.voice.channel.name),
                    expire_in=25
                )

            await self._initialize_player(author)

        log.info("Joining {0.guild.name}/{0.name}".format(author.voice.channel))

        return Response(self.str.get('cmd-summon-reply', 'Connected to `{0.name}`').format(author.voice.channel))

    async def _initialize_player(self, author: Member):
        player_cog: Optional[PlayerCog] = self.bot.get_cog('PlayerCog')
        if player_cog is None:
            raise ValueError('PlayerCog is missing')

        player = await player_cog.get_player(author.voice.channel, create=True, deserialize=self.config.persistent_queue)

        if player.is_stopped:
            player.play()

        if self.config.auto_playlist:
            await player_cog.on_player_finished_playing(player)