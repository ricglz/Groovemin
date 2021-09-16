'''Module containing the logic for ConnectionManager Cog'''
import logging

from discord import Guild, Member
from discord.ext.commands import Context
from dislash import command

from ..exceptions import CommandError
from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class ConnectionManagerCog(Cog):
    '''
    Cog class which handles the summoning and disconnection of the bot.
    '''
    def voice_client_in(self, guild: Guild):
        '''Returns the voice client of the guild'''
        for voice_client in self.voice_clients:
            if voice_client.guild == guild:
                return voice_client
        return None

    @command(description='Summons the bot into the voice channel you currently are')
    async def summon(self, context: Context):
        '''Summons the bot into the voice channel you currently are'''
        author: Member = context.author

        if not author.voice:
            error_msg = self.str.get(
                'cmd-summon-novc',
                'You are not connected to voice. Try joining a voice channel!'
            )
            raise CommandError(error_msg)

        guild: Guild = context.guild
        voice_client = self.voice_client_in(guild)

        if voice_client and guild == author.voice.channel.guild:
            await voice_client.move_to(author.voice.channel)
        else:
            # move to _verify_vc_perms?
            chperms = author.voice.channel.permissions_for(guild.me)

            if not chperms.connect:
                log.warning(
                    "Cannot join channel '%s', no permission to connect.", author.voice.channel.name
                )
                error_msg = self.str.get(
                    'cmd-summon-noperms-connect',
                    "Cannot join channel `{0}`, no permission to connect."
                ).format(author.voice.channel.name)
                raise CommandError(error_msg, expire_in=25)

            if not chperms.speak:
                log.warning(
                    "Cannot join channel '%s', no permission to speak.", author.voice.channel.name
                )
                error_msg = self.str.get(
                    'cmd-summon-noperms-speak',
                    "Cannot join channel `{0}`, no permission to speak."
                ).format(author.voice.channel.name)
                raise CommandError(error_msg, expire_in=25)

            await self._initialize_player(author)

        msg = "Joining {0.guild.name}/{0.name}".format(author.voice.channel)
        log.info(msg)
        await self.safe_send_message(context, msg)

    async def _initialize_player(self, author: Member):
        player_cog = self.g_et_player_cog()
        player = await player_cog.get_player(
            author.voice.channel, create=True, deserialize=self.config.persistent_queue
        )

        if player.is_stopped:
            player.play()

        if self.config.auto_playlist:
            await player_cog.on_player_finished_playing(player)

    async def disconnect_voice_client(self, guild: Guild, player_cog):
        '''Disconnects the bot from the voice client'''
        voice_client = self.voice_client_in(guild)
        if not voice_client:
            return

        player_cog.remove_player(guild)

        await voice_client.disconnect()

    async def disconnect_all_voice_clients(self, player_cog):
        '''Disconnects the bot from all the voice clients'''
        voice_clients = list(self.voice_clients).copy()
        for voice_client in voice_clients:
            await self.disconnect_voice_client(
                voice_client.channel.guild,
                player_cog
            )

    @command(description='Removes the bot from the current voice channel')
    async def disconnect(self, context: Context):
        '''Disconnects from the current voice channel'''
        guild: Guild = context.guild
        player_cog = self._get_player_cog()
        await self.disconnect_voice_client(guild, player_cog)
        await self.safe_send_message(context, 'Bot was disconnected')

    # @command(description='Turns off the bot')
    # async def shutdown(self, context: Context):
    #     channel = context.channel
    #     await self.safe_send_message(channel, "\N{WAVING HAND SIGN}")

    #     player_cog = self._get_player_cog()
    #     player = player_cog.get_player_in(channel.guild)
    #     if player and player.is_paused:
    #         player.resume()

    #     await self.disconnect_all_voice_clients(player_cog)
