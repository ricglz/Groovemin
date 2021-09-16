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
        expire_in = kwargs.pop('expire_in', None)
        allow_none = kwargs.pop('allow_none', True)

        msg = None
        log_func = log.debug if quiet else log.warning

        try:
            if content is not None or allow_none:
                if isinstance(dest, discord.TextChannel):
                    msg = await dest.send(content, tts=tts, delete_after=expire_in)
                elif isinstance(content, discord.Embed):
                    msg = await dest.reply(embed=content, delete_after=expire_in)
                else:
                    msg = await dest.reply(content, tts=tts, delete_after=expire_in)

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
