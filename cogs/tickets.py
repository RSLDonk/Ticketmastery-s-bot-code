import discord
from discord import app_commands
from discord.ext import commands

from .config import BLUE, SUPPORT_FEEDBACK_CHANNEL_ID
from .database import (
    assign_ticket,
    get_gcfg,
    get_open_ticket,
)
from .ticket_manager import TicketManager
from .utils import admin_owner_check, send_log
from .views import (
    SETUP_VIEW_TIMEOUT_SECONDS,
    CloseConfirmView,
    SetupView,
    build_close_confirmation_embed,
    build_setup_embed,
)


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Get help and support info")
    async def help_command(self, inter: discord.Interaction):
        embed = discord.Embed(
            title="📘 TicketMastery Help",
            color=BLUE
        )

        embed.add_field(
            name="🎫 Tickets",
            value="`/ticket_close` – Close your ticket\n`/claim` – Claim a ticket\n`/feedback` – Send feedback to the TicketMastery team",
            inline=False
        )

        embed.add_field(
            name="⚙️ Setup",
            value="`/setup` – Configure the ticket system with dropdown menus",
            inline=False
        )

        embed.add_field(
            name="🛠️ Admin",
            value="Staff roles, logs, panels, categories, transcripts, and appearance live in `/setup`",
            inline=False
        )

        embed.add_field(
            name="🔗 Support",
            value="[Join Support Server](https://discord.gg/XrDWPGucQG) for help, updates, and feedback!",
            inline=False
        )

        embed.set_footer(text="TicketMastery • Always here to help")

        await inter.response.send_message(embed=embed)

    @app_commands.command(name="ping", description="Show bot latency.")
    async def ping(self, inter: discord.Interaction):
        await inter.response.send_message(f"🏓 {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="feedback", description="Send feedback to the TicketMastery team.")
    @app_commands.describe(message="Your feedback, suggestion, or bug report")
    async def feedback(self, inter: discord.Interaction, message: str):
        feedback_text = discord.utils.escape_mentions(message.strip())
        if not feedback_text:
            return await inter.response.send_message(
                "❌ Please include some feedback.",
                ephemeral=True,
            )

        await inter.response.defer(ephemeral=True)

        channel = self.bot.get_channel(SUPPORT_FEEDBACK_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(SUPPORT_FEEDBACK_CHANNEL_ID)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                channel = None

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await inter.followup.send(
                "❌ I couldn't deliver your feedback right now. Please try again later.",
                ephemeral=True,
            )

        source_name = inter.guild.name if inter.guild else "Direct Message"
        source_id = str(inter.guild.id) if inter.guild else "N/A"
        embed = discord.Embed(
            title="💬 New TicketMastery Feedback",
            description=feedback_text[:4096],
            color=BLUE,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=str(inter.user),
            icon_url=inter.user.display_avatar.url,
        )
        embed.add_field(name="From", value=inter.user.mention, inline=True)
        embed.add_field(name="Server", value=source_name[:1024], inline=True)
        embed.set_footer(text=f"User ID: {inter.user.id} • Server ID: {source_id}")

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            return await inter.followup.send(
                "❌ I couldn't deliver your feedback right now. Please try again later.",
                ephemeral=True,
            )

        await inter.followup.send(
            "✅ Thanks! Your feedback was sent to the TicketMastery team.",
            ephemeral=True,
        )

    @app_commands.command(name="setup", description="Configure TicketMastery with dropdown menus")
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
            ephemeral=True
        )

    # ---- Ticket Actions ----
    @app_commands.command(name="claim", description="Claim the current ticket (staff only if staff role is set).")
    async def claim(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("Guild only.", ephemeral=True)
        info = get_open_ticket(inter.guild.id, inter.channel.id)
        if not info:
            return await inter.response.send_message("❌ This isn't a ticket channel.", ephemeral=True)

        # TODO: Add anti-spam for claiming tickets (one per user every 60 seconds)
        gcfg = get_gcfg(inter.guild.id)
        staff_role_id = gcfg.get("staff_role_id")
        if staff_role_id and isinstance(inter.user, discord.Member):
            if staff_role_id not in [r.id for r in inter.user.roles]:
                # TODO: Add warning message that staff role is unknown, tell staff who tried to claim it
                return await inter.response.send_message("🚫 Only staff can claim this ticket.", ephemeral=True)

        try:
            await inter.channel.edit(name=f"claimed-{inter.channel.name}")
        except Exception:
            pass

        await inter.response.send_message(f"✅ Ticket claimed by {inter.user.mention}")
        assign_ticket(inter.guild.id, inter.channel.id, inter.user.id)
        e = discord.Embed(title="🎟️ Ticket Claimed", description=f"By {inter.user.mention} in {inter.channel.mention}", color=discord.Color.green())
        await send_log(inter.guild, e)

    @app_commands.command(name="ticket_close", description="Close this ticket and DM a transcript to the opener.")
    async def ticket_close(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("Guild only.", ephemeral=True)
        
        info = get_open_ticket(inter.guild.id, inter.channel.id)
        if not info:
            return await inter.response.send_message("❌ This isn't a ticket channel.", ephemeral=True)

        view = CloseConfirmView(inter.guild, inter.user, inter.channel, info, self.bot)
        await inter.response.send_message(
            embed=build_close_confirmation_embed(info, inter.channel),
            view=view,
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
