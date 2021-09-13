from typing import List

from .custom_cog import CustomCog as Cog
from .messenger import MessengerCog
from .player import PlayerCog
from .summon import SummonCog

COGS: List[Cog] = [MessengerCog, PlayerCog, SummonCog]
