import logging

from discord import Guild, Member
from discord.ext.commands import Context, command

from ..exceptions import CommandError
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class ConnectionManagerCog(Cog):
    def voice_client_in(self, guild):
        for voice_client in self.voice_clients:
            if voice_client.guild == guild:
                return voice_client
        return None

    @command()
    async def summon(self, context: Context):
        author: Member = context.author

        if not author.voice:
            raise CommandError(self.str.get('cmd-summon-novc', 'You are not connected to voice. Try joining a voice channel!'))

        guild: Guild = context.guild
        voice_client = self.voice_client_in(guild)

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

    async def _initialize_player(self, author: Member):
        player_cog = self.get_player_cog()
        player = await player_cog.get_player(author.voice.channel, create=True, deserialize=self.config.persistent_queue)

        if player.is_stopped:
            player.play()

        if self.config.auto_playlist:
            await player_cog.on_player_finished_playing(player)

    async def disconnect_voice_client(self, guild, player_cog):
        voice_client = self.voice_client_in(guild)
        if not voice_client:
            return

        player_cog.remove_player(guild)

        await voice_client.disconnect()

    async def disconnect_all_voice_clients(self, player_cog):
        voice_clients = list(self.voice_clients).copy()
        for voice_client in voice_clients:
            await self.disconnect_voice_client(
                voice_client.channel.guild,
                player_cog
            )

    @command()
    async def disconnect(self, context: Context):
        guild = context.guild
        player_cog = self.get_player_cog()
        await self.disconnect_voice_client(guild, player_cog)

    @command()
    async def shutdown(self, context: Context):
        channel = context.channel
        await self.safe_send_message(channel, "\N{WAVING HAND SIGN}")

        player_cog = self.get_player_cog()
        player = player_cog.get_player_in(channel.guild)
        if player and player.is_paused:
            player.resume()

        await self.disconnect_all_voice_clients(player_cog)
        raise TerminateSignal()