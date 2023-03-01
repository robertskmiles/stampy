from collections.abc import Coroutine
from servicemodules.serviceConstants import Services
from utilities.serviceutils import (
    ServiceChannel,
    ServiceMessage,
    ServiceRole,
    ServiceServer,
    ServiceUser,
)
from typing import Any, no_type_check, Optional 
import discord


class DiscordUser(ServiceUser):
    def __init__(self, user: discord.abc.User):
        super().__init__(user.name, user.display_name, str(user.id))
        self._user = user
        if hasattr(user, "roles"):
            self.parse_discord_roles(user.roles)
        self.discriminator = user.discriminator
        self.full_name = f"{self.name}#{self.discriminator}"

    def parse_discord_roles(self, roles: list[discord.Role]) -> None:
        for role in roles:
            self.roles.append(ServiceRole(role.name, str(role.id)))


class DiscordChannel(ServiceChannel):
    def __init__(self, channel: discord.abc.Messageable, server: Optional[ServiceServer]):
        self._channel = channel
        self.history = channel.history
        if not isinstance(channel, discord.DMChannel):
            name = channel.name
        else:
            name = None
        super().__init__(name, str(channel.id), server)

    @property
    def guild(self) -> Optional[ServiceServer]:
        """
        Alias for server for discord message compatibility.
        """
        return self.server

    """
    Have to put no type check for now.  discord-py is not typed so discord.abc.Messageable is type(object)
    """
    @no_type_check
    async def send(self, *args, **kwargs) -> discord.message.Message:
        return self._channel.send(*args, **kwargs)


class DiscordMessage(ServiceMessage):
    def __init__(self, msg: discord.message.Message):
        self._message = msg
        author = DiscordUser(msg.author)
        guild: Optional[ServiceServer]
        if msg.guild:
            guild = ServiceServer(msg.guild.name, str(msg.guild.id))
        else:
            guild = None
        channel = DiscordChannel(msg.channel, guild)
        service = Services.DISCORD

        super().__init__(str(msg.id), msg.content, author, channel, service)
        self.clean_content = msg.clean_content.replace("\u200b", "")
        self._parse_discord_mentions(msg.mentions)
        self.reference = msg.reference
        self.reactions = msg.reactions  # We need reactions for recalculating stamps from history
        if guild is None:
            self.is_dm = True

    def _parse_discord_mentions(self, mentions: list[discord.abc.User]):
        for user in mentions:
            self.mentions.append(DiscordUser(user))
