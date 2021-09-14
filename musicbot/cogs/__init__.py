'''Module containing all the Cogs for music bot'''
from typing import List

from .custom_cog import CustomCog as Cog
from .messenger import MessengerCog
from .play import PlayCog
from .player import PlayerCog
from .summon import SummonCog

COGS: List[Cog] = [
    MessengerCog,
    PlayCog,
    PlayerCog,
    SummonCog
]
