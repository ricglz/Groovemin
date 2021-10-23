'''Module containing the logic for ConnectionManager Cog'''
import logging

from discord.ext.commands import Context
from dislash import command

from .custom_cog import CustomCog as Cog

log = logging.getLogger(__name__)

class ConnectionManagerCog(Cog):
    '''
    Cog class which handles the summoning and disconnection of the bot.
    '''
    @command(description='Summons the bot into the voice channel you currently are')
    async def summon(self, context: Context):
        '''Summons the bot into the voice channel you currently are'''

    @command(description='Removes the bot from the current voice channel')
    async def disconnect(self, context: Context):
        '''Disconnects from the current voice channel'''
