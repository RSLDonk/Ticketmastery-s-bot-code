import discord

from .categories import TicketCategorySelect
from .config import BLUE, DEFAULT_PANEL_DESCRIPTION, DEFAULT_PANEL_TITLE
from .database import get_categories, get_gcfg, set_gcfg
from .setup import SETUP_VIEW_TIMEOUT_SECONDS, refresh_setup_panel
from .utils import audit, base_embed


def build_panel_view(guild: discord.Guild) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if get_categories(guild.id):
        view.add_item(TicketCategorySelect(guild))
    return view


def build_panel_embed(guild: discord.Guild) -> discord.Embed:
    gcfg = get_gcfg(guild.id)
    embed = base_embed(
        "🎫 Panel Manager",
        "Control the ticket panel.",
    )

    desc = gcfg.get("panel_description") or DEFAULT_PANEL_DESCRIPTION
    embed.add_field(
        name="📨 Current Description",
        value=desc[:500] + "..." if len(desc) > 500 else desc,
        inline=False,
    )

    panel_status = "✅ Active" if gcfg.get("panel_message_id") else "❌ Not posted"
    embed.add_field(name="📍 Panel Status", value=panel_status, inline=True)

    return embed


class PanelDescModal(discord.ui.Modal, title="Edit Panel Description"):
    description = discord.ui.TextInput(
        label="Panel Description",
        style=discord.TextStyle.paragraph,
        placeholder="Enter the description that appears on the ticket panel",
        max_length=1000,
    )

    def __init__(
        self,
        current_description: str,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__()
        self.description.default = current_description
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        gcfg = get_gcfg(inter.guild.id)
        gcfg["panel_description"] = self.description.value
        set_gcfg(inter.guild.id, gcfg)
        await audit(inter.guild, inter.user, "updated panel description")
        await inter.response.send_message(
            "✅ Panel description updated.",
            ephemeral=True,
        )
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )


class PanelManagerView(discord.ui.View):
    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    # TODO: Ensure panel persists across bot restarts and old panels continue to work
    @discord.ui.button(label="📨 Send Panel Here", style=discord.ButtonStyle.green)
    async def send(self, inter: discord.Interaction, button: discord.ui.Button):
        await send_ticket_panel(
            inter,
            self.setup_channel_id,
            self.setup_message_id,
        )

    @discord.ui.button(label="✏️ Edit Description", style=discord.ButtonStyle.blurple)
    async def edit(self, inter: discord.Interaction, button: discord.ui.Button):
        gcfg = get_gcfg(inter.guild.id)
        current_description = (
            gcfg.get("panel_description") or DEFAULT_PANEL_DESCRIPTION
        )
        await inter.response.send_modal(
            PanelDescModal(
                current_description,
                self.setup_channel_id,
                self.setup_message_id,
            )
        )


async def send_ticket_panel(
    inter: discord.Interaction,
    setup_channel_id: int | None = None,
    setup_message_id: int | None = None,
):
    gcfg = get_gcfg(inter.guild.id)
    cats = get_categories(inter.guild.id)

    if not cats:
        return await inter.response.send_message(
            "⚠️ No categories configured. Add some categories first!",
            ephemeral=True,
        )

    embed = discord.Embed(
        title=DEFAULT_PANEL_TITLE,
        description=gcfg.get("panel_description") or DEFAULT_PANEL_DESCRIPTION,
        color=BLUE,
    )

    view = build_panel_view(inter.guild)
    msg = await inter.channel.send(embed=embed, view=view)

    gcfg["panel_channel_id"] = inter.channel.id
    gcfg["panel_message_id"] = msg.id
    set_gcfg(inter.guild.id, gcfg)
    await inter.response.send_message(
        "✅ Ticket panel created in this channel.",
        ephemeral=True,
    )
    await refresh_setup_panel(
        inter.guild,
        setup_channel_id,
        setup_message_id,
    )


__all__ = [
    "PanelDescModal",
    "PanelManagerView",
    "build_panel_embed",
    "build_panel_view",
    "send_ticket_panel",
]
