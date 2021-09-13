from typing import List

from .messenger import MessengerCog
from .player import PlayerCog
from .summon import SummonCog
from .custom_cog import CustomCog as Cog

COGS: List[Cog] = [MessengerCog, PlayerCog, SummonCog]
