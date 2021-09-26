'''Module containing custom ConfigParser'''
from configparser import ConfigParser as BaseConfigParser, SectionProxy as BaseSectionProxy
import logging

log = logging.getLogger(__name__)

class ConfigParser(BaseConfigParser):
    '''Modified version of BaseConfigParser that can parse sets.'''
    @staticmethod
    def str_to_list(string_value: str):
        '''Parses a string of elements into a list.'''
        return string_value.lower().replace(',', ' ').split()

    def get_set(self, section: str, option: str, *, raw=False, vars=None, fallback=None):
        '''Gets a set for the given section and option.'''
        option_value = self.get(section, option, raw=raw, vars=vars, fallback=fallback)
        if option_value is None:
            return set()
        return set(self.str_to_list(option_value))

    def get_int_set(self, section: str, option: str, *, raw=False, vars=None, fallback=None):
        '''
        Gets a set for the given section and option, the values of the set will be cast to int.
        '''
        option_set = self.get_set(section, option, raw=raw, vars=vars, fallback=fallback)
        try:
            return set(int(value) for value in option_set)
        except ValueError:
            log.warning('%s data is invalid, will ignore.', option)
            return set()

class SectionProxy(BaseSectionProxy):
    '''Modified version of BaseConfigParser that can parse sets.'''
    def get_set(self, option, fallback=None, *, raw=False, vars=None, **kwargs):
        '''Gets a set for the given option.'''
        return self._parser.get_set(
            self._name, option, raw=raw, vars=vars, fallback=fallback, **kwargs
        )

    def get_int_set(self, option, fallback=None, *, raw=False, vars=None, **kwargs):
        '''Gets a set for the given option, the values of the set will be cast to int.'''
        return self._parser.get_int_set(
            self._name, option, raw=raw, vars=vars, fallback=fallback, **kwargs
        )
