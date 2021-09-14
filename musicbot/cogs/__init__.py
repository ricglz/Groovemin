'''Module containing all the Cogs for music bot'''
from typing import List

from .custom_cog import CustomCog as Cog
from .messenger import MessengerCog
from .music_manager import MusicManager
from .play import PlayCog
from .player import PlayerCog
from .connection_manager import ConnectionManagerCog

COGS: List[Cog] = [
    ConnectionManagerCog,
    MessengerCog,
    PlayCog,
    PlayerCog,
]
