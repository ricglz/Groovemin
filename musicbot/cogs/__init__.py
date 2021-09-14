from typing import List

from .custom_cog import CustomCog as Cog
from .messenger import MessengerCog
from .music_manager import MusicManagerCog
from .player import PlayerCog
from .summon import SummonCog

COGS: List[Cog] = [
    MessengerCog,
    MusicManagerCog,
    PlayerCog,
    SummonCog
]
