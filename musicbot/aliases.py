'''Module containing the logic for aliases'''
from dataclasses import dataclass
from pathlib import Path
import json
import logging
import shutil

from .exceptions import HelpfulError

log = logging.getLogger(__name__)

class Aliases:
    '''Class in charge of managing the aliases'''
    def __init__(self, aliases_file):
        self.aliases_file = Path(aliases_file)
        self.aliases_seed = AliasesDefault.aliases_seed
        self.aliases = AliasesDefault.aliases

        self._find_aliases_file()
        self._parse_json()
        self._construct()

    def _find_aliases_file(self):
        if not self.aliases_file.is_file():
            example_aliases = Path('config/example_aliases.json')
            if example_aliases.is_file():
                shutil.copy(str(example_aliases), str(self.aliases_file))
                log.warning('Aliases file not found, copying example_aliases.json')
            else:
                raise HelpfulError(
                    "Your aliases files are missing. Neither aliases.json nor "
                    "example_aliases.json were found. Grab the files back from the archive or "
                    "remake them yourself and copy paste the content from the repo. Stop removing ",
                    "important files!"
                )

    def _parse_json(self):
        with self.aliases_file.open() as file:
            try:
                self.aliases_seed = json.load(file)
            except json.JSONDecodeError as error:
                raise HelpfulError(
                    "Failed to parse aliases file.",
                    f"Ensure your {str(self.aliases_file)} is a valid json"
                    "file and restart the bot."
                ) from error

    def _construct(self):
        for cmd, aliases in self.aliases_seed.items():
            if not isinstance(cmd, str) or not isinstance(aliases, list):
                raise HelpfulError(
                    "Failed to parse aliases file.",
                    "See documents and config {} properly!".format(str(self.aliases_file))
                )
            self.aliases.update({alias.lower(): cmd.lower() for alias in aliases})


    def get(self, arg):
        """
        Return cmd name (string) that given arg points.
        If arg is not registered as alias, empty string will be returned.
        supposed to be called from bot.on_message
        """
        ret = self.aliases.get(arg)
        return ret if ret else ''

@dataclass
class AliasesDefault:
    '''Class containing the defaults of the class'''
    aliases_file = 'config/aliases.json'
    aliases_seed = {}
    aliases = {}
