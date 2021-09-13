import asyncio
import logging

import discord

from ..constants import DISCORD_MSG_CHAR_LIMIT
from .custom_cog import CustomCog

log = logging.getLogger(__name__)

class MessengerCog(CustomCog):
    async def safe_send_message(self, dest, content, **kwargs):
        tts = kwargs.pop('tts', False)
        quiet = kwargs.pop('quiet', False)
        expire_in = kwargs.pop('expire_in', 0)
        allow_none = kwargs.pop('allow_none', True)
        also_delete = kwargs.pop('also_delete', None)

        msg = None
        log_func = log.debug if quiet else log.warning

        try:
            if content is not None or allow_none:
                if isinstance(content, discord.Embed):
                    msg = await dest.send(embed=content)
                else:
                    msg = await dest.send(content, tts=tts)

        except discord.Forbidden:
            log_func("Cannot send message to \"%s\", no permission", dest.name)

        except discord.NotFound:
            log_func("Cannot send message to \"%s\", invalid channel?", dest.name)

        except discord.HTTPException:
            if len(content) > DISCORD_MSG_CHAR_LIMIT:
                log_func("Message is over the message size limit (%s)", DISCORD_MSG_CHAR_LIMIT)
            else:
                log_func("Failed to send message")
                log.noise("Got HTTPException trying to send message to %s: %s", dest, content)

        finally:
            if msg and expire_in:
                asyncio.ensure_future(self._wait_delete_msg(msg, expire_in))

            if also_delete and isinstance(also_delete, discord.Message):
                asyncio.ensure_future(self._wait_delete_msg(also_delete, expire_in))

        return msg

    async def _wait_delete_msg(self, message, after):
        await asyncio.sleep(after)
        await self.safe_delete_message(message, quiet=True)

    async def safe_delete_message(self, message, *, quiet=False):
        log_func = log.debug if quiet else log.warning

        try:
            return await message.delete()

        except discord.Forbidden:
            log_func("Cannot delete message \"%s\", no permission", message.clean_content)

        except discord.NotFound:
            log_func("Cannot delete message \"%s\", message not found", message.clean_content)
