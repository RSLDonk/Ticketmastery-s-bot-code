import discord

from .database import get_gcfg, set_gcfg
from .setup import SETUP_VIEW_TIMEOUT_SECONDS, refresh_setup_panel
from .utils import audit, base_embed


def build_settings_embed(guild: discord.Guild) -> discord.Embed:
    gcfg = get_gcfg(guild.id)
    embed = base_embed(
        "⚙️ Settings Panel",
        "Configure your ticket system settings.",
    )

    staff_role = f"<@&{gcfg['staff_role_id']}>" if gcfg["staff_role_id"] else "Not set"
    log_channel = f"<#{gcfg['log_channel_id']}>" if gcfg["log_channel_id"] else "Not set"

    embed.add_field(name="👮 Staff Role", value=staff_role, inline=True)
    embed.add_field(name="📢 Log Channel", value=log_channel, inline=True)
    embed.add_field(name="📄 Log Transcripts", value=str(gcfg["log_transcripts"]), inline=True)

    return embed


class TranscriptView(discord.ui.View):
    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    @discord.ui.button(label="Toggle Transcripts", style=discord.ButtonStyle.gray)
    async def transcripts(
        self,
        inter: discord.Interaction,
        button: discord.ui.Button,
    ):
        gcfg = get_gcfg(inter.guild.id)
        gcfg["log_transcripts"] = not gcfg["log_transcripts"]
        set_gcfg(inter.guild.id, gcfg)

        await audit(
            inter.guild,
            inter.user,
            f"toggled transcripts to {gcfg['log_transcripts']}",
        )
        await inter.response.send_message(
            f"📄 Transcripts logging: **{gcfg['log_transcripts']}**",
            ephemeral=True,
        )
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )


__all__ = ["TranscriptView", "build_settings_embed"]
