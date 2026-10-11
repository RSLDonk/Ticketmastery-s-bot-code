from typing import Any, Dict

import discord

from .database import assign_ticket, get_gcfg, get_open_ticket
from .ticket_manager import TicketManager
from .utils import send_log


def build_close_confirmation_embed(
    closer: discord.User | discord.Member,
    bot_user: discord.ClientUser | None,
) -> discord.Embed:
    embed = discord.Embed(
        title="Close Confirmation",
        description="Please confirm that you want to close this ticket",
        color=discord.Color.green(),
    )
    embed.set_author(
        name=closer.display_name,
        icon_url=closer.display_avatar.url,
    )
    if bot_user:
        embed.set_footer(
            text="Powered by TicketMastery",
            icon_url=bot_user.display_avatar.url,
        )
    else:
        embed.set_footer(text="Powered by TicketMastery")
    return embed


class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Close Reason (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this ticket being closed?",
        max_length=1000,
        required=False,
    )

    def __init__(
        self,
        guild: discord.Guild,
        closer: discord.User,
        channel: discord.TextChannel,
        ticket_info: Dict[str, Any],
        bot_client: discord.Client,
    ):
        super().__init__()
        self.guild = guild
        self.closer = closer
        self.channel = channel
        self.ticket_info = ticket_info
        self.bot_client = bot_client

    async def on_submit(self, inter: discord.Interaction):
        await inter.response.defer(thinking=True, ephemeral=True)
        gcfg = get_gcfg(self.guild.id)
        close_reason = str(self.reason.value).strip() or "No reason specified"
        success = await TicketManager.close_ticket(
            self.bot_client,
            self.guild,
            self.channel,
            self.closer,
            self.ticket_info,
            transcripts_enabled=gcfg.get("log_transcripts", True),
            close_reason=close_reason,
        )

        if success:
            await inter.followup.send(
                "✅ Ticket closed & transcript sent.",
                ephemeral=True,
            )
        else:
            await inter.followup.send(
                "❌ Error closing ticket, but channel may be deleted.",
                ephemeral=True,
            )


class CloseConfirmView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        closer: discord.User,
        channel: discord.TextChannel,
        ticket_info: Dict[str, Any],
        bot_client: discord.Client,
    ):
        super().__init__(timeout=30)
        self.guild = guild
        self.closer = closer
        self.channel = channel
        self.ticket_info = ticket_info
        self.bot_client = bot_client
        self._closing = False

    async def _close_ticket(self, inter: discord.Interaction, close_reason: str):
        if self._closing:
            return await inter.response.send_message(
                "⏳ This ticket is already being closed.",
                ephemeral=True,
            )

        ticket_info = get_open_ticket(self.guild.id, self.channel.id)
        if not ticket_info:
            return await inter.response.send_message(
                "❌ This ticket is already closed.",
                ephemeral=True,
            )

        self._closing = True
        for child in self.children:
            child.disabled = True
        await inter.response.edit_message(view=self)
        self.stop()

        gcfg = get_gcfg(self.guild.id)
        success = await TicketManager.close_ticket(
            self.bot_client,
            self.guild,
            self.channel,
            inter.user,
            ticket_info,
            transcripts_enabled=gcfg.get("log_transcripts", True),
            close_reason=close_reason,
        )

        if success:
            await inter.followup.send(
                "✅ Ticket closed & transcript sent.",
                ephemeral=True,
            )
        else:
            await inter.followup.send(
                "❌ Error closing ticket, but channel may be deleted.",
                ephemeral=True,
            )

    @discord.ui.button(
        label="Close",
        emoji="✔️",
        style=discord.ButtonStyle.blurple,
    )
    async def close(self, inter: discord.Interaction, button: discord.ui.Button):
        await self._close_ticket(inter, "No reason specified")


class TicketButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.blurple,
        custom_id="ticket_claim_btn",
    )
    async def claim_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not inter.guild:
            return
        gcfg = get_gcfg(inter.guild.id)
        staff_role_id = gcfg.get("staff_role_id")
        if staff_role_id and isinstance(inter.user, discord.Member):
            if staff_role_id not in [r.id for r in inter.user.roles]:
                return await inter.response.send_message(
                    "🚫 Only staff can claim this ticket.",
                    ephemeral=True,
                )

        info = get_open_ticket(inter.guild.id, inter.channel.id)
        if not info:
            return await inter.response.send_message(
                "❌ This isn't a ticket channel.",
                ephemeral=True,
            )

        try:
            await inter.channel.edit(name=f"claimed-{inter.channel.name}")
        except Exception:
            pass

        await inter.response.send_message(f"✅ Ticket claimed by {inter.user.mention}")
        assign_ticket(inter.guild.id, inter.channel.id, inter.user.id)
        e = discord.Embed(
            title="🎟️ Ticket Claimed",
            description=f"By {inter.user.mention} in {inter.channel.mention}",
            color=discord.Color.green(),
        )
        await send_log(inter.guild, e)

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.red,
        custom_id="ticket_close_btn",
    )
    async def close_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not inter.guild:
            return

        info = get_open_ticket(inter.guild.id, inter.channel.id)
        if not info:
            return await inter.response.send_message(
                "❌ This isn't a ticket channel.",
                ephemeral=True,
            )

        view = CloseConfirmView(
            inter.guild,
            inter.user,
            inter.channel,
            info,
            inter.client,
        )
        await inter.response.send_message(
            embed=build_close_confirmation_embed(inter.user, inter.client.user),
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Close with Reason",
        style=discord.ButtonStyle.blurple,
        custom_id="ticket_close_reason_btn",
    )
    async def close_reason_btn(
        self,
        inter: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not inter.guild:
            return

        info = get_open_ticket(inter.guild.id, inter.channel.id)
        if not info:
            return await inter.response.send_message(
                "❌ This isn't a ticket channel.",
                ephemeral=True,
            )

        await inter.response.send_modal(
            CloseReasonModal(
                inter.guild,
                inter.user,
                inter.channel,
                info,
                inter.client,
            )
        )
