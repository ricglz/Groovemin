'''Module containing the MusicPlayer state management'''
from dataclasses import dataclass
from enum import Enum

class MusicPlayerState(Enum):
    '''Enum class representing the state that the MusicPlayer is currently at.'''
    STOPPED = 0  # When the player isn't playing anything
    PLAYING = 1  # The player is actively playing music.
    PAUSED = 2   # The player is paused on a song.
    WAITING = 3  # The player has finished its song but is still downloading the next one
    DEAD = 4     # The player has been killed.
    RESET = 5    # The player is playing but will play the same song when finished
    LOOP = 6     # The player is playing but will play the same song until go out of the loop

    def __str__(self):
        return self.name

@dataclass
class MusicPlayerStateHandler:
    '''Helper class to handle music state'''
    state: MusicPlayerState = MusicPlayerState.STOPPED

    @property
    def is_stopped(self):
        return self.state == MusicPlayerState.STOPPED

    @property
    def is_playing(self):
        return self.state == MusicPlayerState.PLAYING

    @property
    def is_paused(self):
        return self.state == MusicPlayerState.PAUSED

    @property
    def is_waiting(self):
        return self.state == MusicPlayerState.WAITING

    @property
    def is_dead(self):
        return self.state == MusicPlayerState.DEAD

    @property
    def is_reset(self):
        return self.state == MusicPlayerState.RESET

    @property
    def is_looped(self):
        return self.state == MusicPlayerState.LOOP
