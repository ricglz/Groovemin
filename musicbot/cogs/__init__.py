'''Module containing all the Cogs for music bot'''
from typing import List

from .connection_manager import ConnectionManagerCog
from .custom_cog import CustomCog as Cog
from .messenger import MessengerCog
from .music_manager import MusicManagerCog
from .now_playing import NowPlayingCog
from .play import PlayCog
from .player import PlayerCog

COGS: List[Cog] = [
    ConnectionManagerCog,
    MessengerCog,
    MusicManagerCog,
    NowPlayingCog,
    PlayCog,
    PlayerCog,
]
