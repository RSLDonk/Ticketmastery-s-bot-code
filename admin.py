import discord
from discord import app_commands
from discord.ext import commands

from .utils import admin_owner_check
from .setup import (
    SETUP_VIEW_TIMEOUT_SECONDS,
    SetupView,
    build_setup_embed,
)


class AdminCog(commands.Cog):
    """Administrative commands for configuring TicketMastery."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="Configure TicketMastery with dropdown menus",
    )
    @admin_owner_check()
    async def setup(self, inter: discord.Interaction):
        if not inter.guild or not inter.channel:
            return await inter.response.send_message("Guild only.", ephemeral=True)

        await inter.channel.send(
            embed=build_setup_embed(inter.guild),
            view=SetupView(),
            delete_after=SETUP_VIEW_TIMEOUT_SECONDS,
        )
        await inter.response.send_message(
            "✅ Setup panel posted in this channel.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
