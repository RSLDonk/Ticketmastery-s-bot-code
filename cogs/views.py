import time
from typing import Any, Dict

import discord

from .config import (
    BLUE,
    DEFAULT_PANEL_DESCRIPTION,
    DEFAULT_PANEL_TITLE,
    DEFAULT_TICKET_DESCRIPTION,
    DEFAULT_TICKET_TITLE,
    TICKET_CREATION_COOLDOWN_SECONDS,
)
from .database import (
    add_category,
    assign_ticket,
    clear_categories,
    get_categories,
    get_category,
    get_gcfg,
    get_open_ticket,
    get_open_ticket_by_owner,
    remove_category,
    set_gcfg,
    update_category,
)
from .ticket_manager import TicketManager
from .utils import audit, base_embed, send_log

ticket_creation_cooldowns: Dict[int, int] = {}
SETUP_VIEW_TIMEOUT_SECONDS = 3 * 60 * 60


def build_close_confirmation_embed(ticket_info: Dict[str, Any], channel: discord.TextChannel) -> discord.Embed:
    ticket_num = ticket_info.get("num", "N/A")
    owner_id = ticket_info.get("owner_id")
    embed = discord.Embed(
        title="🔒 Close Ticket?",
        description="Confirm that you want to close this ticket.",
        color=discord.Color.red()
    )
    embed.add_field(name="Ticket", value=f"#{ticket_num}", inline=True)
    embed.add_field(name="Opened By", value=f"<@{owner_id}>" if owner_id else "Unknown", inline=True)
    embed.add_field(name="Channel", value=channel.mention, inline=True)
    return embed


class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Close Reason (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this ticket being closed?",
        max_length=1000,
        required=False
    )

    def __init__(
        self,
        guild: discord.Guild,
        closer: discord.User,
        channel: discord.TextChannel,
        ticket_info: Dict[str, Any],
        bot_client: discord.Client
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
            close_reason=close_reason
        )

        if success:
            await inter.followup.send("✅ Ticket closed & transcript sent.", ephemeral=True)
        else:
            await inter.followup.send("❌ Error closing ticket, but channel may be deleted.", ephemeral=True)


class CloseConfirmView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        closer: discord.User,
        channel: discord.TextChannel,
        ticket_info: Dict[str, Any],
        bot_client: discord.Client
    ):
        super().__init__(timeout=30)
        self.guild = guild
        self.closer = closer
        self.channel = channel
        self.ticket_info = ticket_info
        self.bot_client = bot_client

    async def _close_ticket(self, inter: discord.Interaction, close_reason: str):
        await inter.response.defer(thinking=True, ephemeral=True)
        gcfg = get_gcfg(self.guild.id)
        success = await TicketManager.close_ticket(
            self.bot_client,
            self.guild,
            self.channel,
            self.closer,
            self.ticket_info,
            transcripts_enabled=gcfg.get("log_transcripts", True),
            close_reason=close_reason
        )

        if success:
            await inter.followup.send("✅ Ticket closed & transcript sent.", ephemeral=True)
        else:
            await inter.followup.send("❌ Error closing ticket, but channel may be deleted.", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red)
    async def close(self, inter: discord.Interaction, button: discord.ui.Button):
        await self._close_ticket(inter, "No reason specified")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_message("❌ Ticket close cancelled.", ephemeral=True)


class TicketButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.blurple, custom_id="ticket_claim_btn")
    async def claim_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not inter.guild:
            return
        gcfg = get_gcfg(inter.guild.id)
        staff_role_id = gcfg.get("staff_role_id")
        if staff_role_id and isinstance(inter.user, discord.Member):
            if staff_role_id not in [r.id for r in inter.user.roles]:
                return await inter.response.send_message("🚫 Only staff can claim this ticket.", ephemeral=True)

        info = get_open_ticket(inter.guild.id, inter.channel.id)
        if not info:
            return await inter.response.send_message("❌ This isn't a ticket channel.", ephemeral=True)

        try:
            await inter.channel.edit(name=f"claimed-{inter.channel.name}")
        except Exception:
            pass

        await inter.response.send_message(f"✅ Ticket claimed by {inter.user.mention}")
        assign_ticket(inter.guild.id, inter.channel.id, inter.user.id)
        e = discord.Embed(title="🎟️ Ticket Claimed", description=f"By {inter.user.mention} in {inter.channel.mention}", color=discord.Color.green())
        await send_log(inter.guild, e)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="ticket_close_btn")
    async def close_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not inter.guild:
            return

        info = get_open_ticket(inter.guild.id, inter.channel.id)
        if not info:
            return await inter.response.send_message("❌ This isn't a ticket channel.", ephemeral=True)

        await inter.response.defer(thinking=True, ephemeral=True)
        gcfg = get_gcfg(inter.guild.id)
        success = await TicketManager.close_ticket(
            inter.client,
            inter.guild,
            inter.channel,
            inter.user,
            info,
            transcripts_enabled=gcfg.get("log_transcripts", True),
            close_reason="No reason specified"
        )
        if success:
            await inter.followup.send("✅ Ticket closed & transcript sent.", ephemeral=True)
        else:
            await inter.followup.send("❌ Error closing ticket, but channel may be deleted.", ephemeral=True)

    @discord.ui.button(label="Close with Reason", style=discord.ButtonStyle.blurple, custom_id="ticket_close_reason_btn")
    async def close_reason_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if not inter.guild:
            return

        info = get_open_ticket(inter.guild.id, inter.channel.id)
        if not info:
            return await inter.response.send_message("❌ This isn't a ticket channel.", ephemeral=True)

        await inter.response.send_modal(
            CloseReasonModal(
                inter.guild,
                inter.user,
                inter.channel,
                info,
                inter.client
            )
        )


def build_panel_view(guild: discord.Guild):
    view = discord.ui.View(timeout=None)
    cats = get_categories(guild.id)[:25]  # Dropdowns support up to 25 options

    # Build dropdown options
    options = []
    for c in cats:
        label = c["name"][:100]
        options.append(discord.SelectOption(label=label, value=str(c["id"])))

    if not options:
        return view  # No categories, return empty view

    # Create dropdown select
    class TicketSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="📋 Select a ticket category...",
                min_values=1,
                max_values=1,
                options=options,
                custom_id=f"ticket_select:{guild.id}"
            )

        async def callback(self, inter: discord.Interaction):
            category_id = int(self.values[0])
            category = get_category(inter.guild.id, category_id)

            if not category:
                return await inter.response.send_message("⚠️ That category no longer exists.", ephemeral=True)

            now = int(time.time())
            if get_open_ticket_by_owner(inter.guild.id, inter.user.id):
                return await inter.response.send_message(
                    "❌ You already have an open ticket. Close it before opening a new one.",
                    ephemeral=True
                )

            last_attempt = ticket_creation_cooldowns.get(inter.user.id, 0)
            remaining = TICKET_CREATION_COOLDOWN_SECONDS - (now - last_attempt)
            if remaining > 0:
                return await inter.response.send_message(
                    f"⏳ Please wait {remaining}s before creating another ticket.",
                    ephemeral=True
                )

            await inter.response.defer(thinking=True, ephemeral=True)

            gcfg_local = get_gcfg(inter.guild.id)
            
            tchan = await TicketManager.create_ticket(
                inter,
                inter.guild,
                inter.user,
                category,
                gcfg_local
            )

            if not tchan:
                return await inter.followup.send("❌ Failed to create ticket channel.", ephemeral=True)

            ticket_creation_cooldowns[inter.user.id] = now
            role_ping = ""
            ping_role_id = category.get("role_id")
            if ping_role_id:
                role = inter.guild.get_role(int(ping_role_id))
                if role:
                    role_ping = role.mention

            embed = base_embed(
                DEFAULT_TICKET_TITLE,
                (
                    f"**Category:** {category['name']}\n"
                    f"**User:** {inter.user.mention}\n\n"
                    f"{DEFAULT_TICKET_DESCRIPTION}"
                )
            )
            await tchan.send(
                content=f"{inter.user.mention} {role_ping}".strip(),
                embed=embed,
                view=TicketButtons()
            )

            await inter.followup.send(f"✅ Ticket created: {tchan.mention}", ephemeral=True)

    view.add_item(TicketSelect())
    return view

# ---------- SETUP PANEL SYSTEM ----------

# Embed builders
def build_setup_embed(guild: discord.Guild) -> discord.Embed:
    gcfg = get_gcfg(guild.id)
    cats = get_categories(guild.id)

    staff_role = f"<@&{gcfg['staff_role_id']}>" if gcfg["staff_role_id"] else "Not Set"
    log_channel = f"<#{gcfg['log_channel_id']}>" if gcfg["log_channel_id"] else "Not Set"
    panel_status = "Created" if gcfg.get("panel_message_id") else "Not Created"

    embed = base_embed(
        "⚙️ TicketMastery Setup",
        "Welcome to the setup panel.\n\nConfigure your ticket system using the options below.\nNo channel IDs or role IDs are required."
    )
    embed.add_field(
        name="📊 Current Configuration",
        value=(
            f"🟢 **Ticket Panel**\n{panel_status}\n\n"
            f"{'🟢' if gcfg['staff_role_id'] else '🟡'} **Staff Role**\n{staff_role}\n\n"
            f"{'🟢' if gcfg['log_channel_id'] else '🟡'} **Log Channel**\n{log_channel}\n\n"
            f"{'🟢' if gcfg['log_transcripts'] else '🟡'} **Transcript Logs**\n"
            f"{'Enabled' if gcfg['log_transcripts'] else 'Disabled'}\n\n"
            f"🟢 **Categories**\n{len(cats)} Created"
        ),
        inline=False
    )
    embed.set_footer(text="Use the menu below to edit your settings.")
    return embed


async def refresh_setup_panel(
    guild: discord.Guild,
    setup_channel_id: int | None,
    setup_message_id: int | None
) -> None:
    if not setup_channel_id or not setup_message_id:
        return

    channel = guild.get_channel(setup_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = await channel.fetch_message(setup_message_id)
        await message.edit(embed=build_setup_embed(guild))
    except (discord.Forbidden, discord.HTTPException, discord.NotFound):
        pass


def build_settings_embed(guild: discord.Guild) -> discord.Embed:
    gcfg = get_gcfg(guild.id)
    embed = base_embed(
        "⚙️ Settings Panel",
        "Configure your ticket system settings."
    )
    
    staff_role = f"<@&{gcfg['staff_role_id']}>" if gcfg['staff_role_id'] else "Not set"
    log_channel = f"<#{gcfg['log_channel_id']}>" if gcfg['log_channel_id'] else "Not set"
    
    embed.add_field(name="👮 Staff Role", value=staff_role, inline=True)
    embed.add_field(name="📢 Log Channel", value=log_channel, inline=True)
    embed.add_field(name="📄 Log Transcripts", value=str(gcfg['log_transcripts']), inline=True)
    
    return embed

def build_categories_embed(guild: discord.Guild) -> discord.Embed:
    cats = get_categories(guild.id)
    embed = base_embed(
        "📂 Category Manager",
        "Manage ticket categories."
    )
    
    if not cats:
        embed.add_field(name="No Categories", value="Add some categories to get started!", inline=False)
    else:
        lines = []
        for i, c in enumerate(cats, 1):
            nm = c.get("name", f"Category {i}")
            rid = c.get("role_id")
            rp = f"<@&{rid}>" if rid else "No ping"
            lines.append(f"{i}. **{nm}** (ID: `{c['id']}`) — {rp}")
        embed.add_field(name=f"Categories ({len(cats)}/10)", value="\n".join(lines), inline=False)
    
    return embed

def build_panel_embed(guild: discord.Guild) -> discord.Embed:
    gcfg = get_gcfg(guild.id)
    embed = base_embed(
        "🎫 Panel Manager",
        "Control the ticket panel."
    )
    
    desc = gcfg.get("panel_description") or DEFAULT_PANEL_DESCRIPTION
    embed.add_field(name="📨 Current Description", value=desc[:500] + "..." if len(desc) > 500 else desc, inline=False)
    
    panel_status = "✅ Active" if gcfg.get("panel_message_id") else "❌ Not posted"
    embed.add_field(name="📍 Panel Status", value=panel_status, inline=True)
    
    return embed


# Modals
class StaffRoleModal(discord.ui.Modal, title="Set Staff Role"):
    role_id = discord.ui.TextInput(label="Role ID", placeholder="Enter the role ID (right-click role > Copy ID)")

    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        try:
            role_id = int(self.role_id.value)
            role = inter.guild.get_role(role_id)
            if not role:
                return await inter.response.send_message("❌ Role not found in this server.", ephemeral=True)
            
            gcfg = get_gcfg(inter.guild.id)
            gcfg["staff_role_id"] = role_id
            set_gcfg(inter.guild.id, gcfg)
            await audit(inter.guild, inter.user, f"set staff role to {role.mention}")
            await inter.response.send_message(f"✅ Staff role set to {role.mention}", ephemeral=True)
            await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)
        except ValueError:
            await inter.response.send_message("❌ Invalid role ID. Please enter a number.", ephemeral=True)

class LogChannelModal(discord.ui.Modal, title="Set Log Channel"):
    channel_id = discord.ui.TextInput(label="Channel ID", placeholder="Enter the channel ID (right-click channel > Copy ID)")

    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        try:
            channel_id = int(self.channel_id.value)
            channel = inter.guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return await inter.response.send_message("❌ Text channel not found in this server.", ephemeral=True)
            
            gcfg = get_gcfg(inter.guild.id)
            gcfg["log_channel_id"] = channel_id
            set_gcfg(inter.guild.id, gcfg)
            await audit(inter.guild, inter.user, f"set log channel to {channel.mention}")
            await inter.response.send_message(f"✅ Log channel set to {channel.mention}", ephemeral=True)
            await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)
        except ValueError:
            await inter.response.send_message("❌ Invalid channel ID. Please enter a number.", ephemeral=True)

class AddCategoryModal(discord.ui.Modal, title="Add Ticket Category"):
    name = discord.ui.TextInput(label="Category Name", placeholder="Enter category name")

    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        cats = get_categories(inter.guild.id)
        if len(cats) >= 10:
            return await inter.response.send_message("❌ You can only have up to 10 categories.", ephemeral=True)

        await inter.response.send_message(
            "Choose the role to ping when this ticket category opens:",
            view=AddCategoryRoleView(
                str(self.name.value),
                self.setup_channel_id,
                self.setup_message_id,
            ),
            ephemeral=True,
        )


class AddCategoryRolePicker(discord.ui.RoleSelect):
    def __init__(
        self,
        category_name: str,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        self.category_name = category_name
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id
        super().__init__(
            placeholder="Select a role to ping...",
            min_values=1,
            max_values=1,
        )

    async def callback(self, inter: discord.Interaction):
        role = self.values[0]
        cats = get_categories(inter.guild.id)
        if len(cats) >= 10:
            return await inter.response.send_message(
                "❌ You can only have up to 10 categories.",
                ephemeral=True,
            )

        add_category(inter.guild.id, self.category_name, role.id)
        await audit(inter.guild, inter.user, f"added category '{self.category_name}'")
        await inter.response.send_message(
            f"✅ Added category `{self.category_name}` (pings {role.mention})",
            ephemeral=True,
        )
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)


class AddCategoryRoleView(discord.ui.View):
    def __init__(
        self,
        category_name: str,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.category_name = category_name
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id
        self.add_item(
            AddCategoryRolePicker(
                category_name,
                setup_channel_id,
                setup_message_id,
            )
        )

    @discord.ui.button(label="No Ping Role", style=discord.ButtonStyle.gray)
    async def no_ping_role(self, inter: discord.Interaction, button: discord.ui.Button):
        cats = get_categories(inter.guild.id)
        if len(cats) >= 10:
            return await inter.response.send_message(
                "❌ You can only have up to 10 categories.",
                ephemeral=True,
            )

        add_category(inter.guild.id, self.category_name, None)
        await audit(inter.guild, inter.user, f"added category '{self.category_name}'")
        await inter.response.send_message(
            f"✅ Added category `{self.category_name}` without a ping role",
            ephemeral=True,
        )
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)

class EditCategoryModal(discord.ui.Modal, title="Edit Ticket Category"):
    category_id = discord.ui.TextInput(label="Category ID", placeholder="Enter the category ID to edit")
    name = discord.ui.TextInput(label="New Category Name", placeholder="Enter the updated category name")
    role_id = discord.ui.TextInput(label="Ping Role ID (optional)", placeholder="Enter new role ID or leave blank", required=False)

    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        try:
            category_id = int(self.category_id.value)
        except ValueError:
            return await inter.response.send_message("❌ Invalid category ID.", ephemeral=True)

        category = get_category(inter.guild.id, category_id)
        if not category:
            return await inter.response.send_message("❌ Category not found.", ephemeral=True)

        role_id = None
        if self.role_id.value:
            try:
                role_id = int(self.role_id.value)
                role = inter.guild.get_role(role_id)
                if not role:
                    return await inter.response.send_message("❌ Role not found in this server.", ephemeral=True)
            except ValueError:
                return await inter.response.send_message("❌ Invalid role ID. Please enter a number.", ephemeral=True)

        update_category(inter.guild.id, category_id, self.name.value, role_id)
        await audit(inter.guild, inter.user, f"edited category '{category['name']}' to '{self.name.value}'")
        msg = f"✅ Updated category `{self.name.value}`"
        if role_id:
            msg += f" (pings <@&{role_id}>)"
        await inter.response.send_message(msg, ephemeral=True)
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)

class DeleteCategoryModal(discord.ui.Modal, title="Delete Ticket Category"):
    category_id = discord.ui.TextInput(label="Category ID", placeholder="Enter the category ID to delete")

    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        try:
            category_id = int(self.category_id.value)
        except ValueError:
            return await inter.response.send_message("❌ Invalid category ID.", ephemeral=True)

        category = get_category(inter.guild.id, category_id)
        if not category:
            return await inter.response.send_message("❌ Category not found.", ephemeral=True)

        remove_category(inter.guild.id, category_id)
        await audit(inter.guild, inter.user, f"deleted category '{category['name']}'")
        await inter.response.send_message(f"🗑️ Deleted category `{category['name']}`.", ephemeral=True)
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)

class PanelDescModal(discord.ui.Modal, title="Edit Panel Description"):
    description = discord.ui.TextInput(
        label="Panel Description", 
        style=discord.TextStyle.paragraph,
        placeholder="Enter the description that appears on the ticket panel",
        max_length=1000
    )

    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        gcfg = get_gcfg(inter.guild.id)
        gcfg["panel_description"] = self.description.value
        set_gcfg(inter.guild.id, gcfg)
        await audit(inter.guild, inter.user, "updated panel description")
        await inter.response.send_message("✅ Panel description updated.", ephemeral=True)
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)

# Views
class SetupMenu(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Ticket Panel",
                description="Create or edit your ticket panel",
                emoji="🎫",
                value="panel"
            ),
            discord.SelectOption(
                label="Staff Role",
                description="Select who can manage tickets",
                emoji="👥",
                value="staff"
            ),
            discord.SelectOption(
                label="Logs",
                description="Choose where ticket logs are sent",
                emoji="📋",
                value="logs"
            ),
            discord.SelectOption(
                label="Categories",
                description="Manage ticket categories",
                emoji="📁",
                value="categories"
            ),
            discord.SelectOption(
                label="Transcripts",
                description="Toggle transcript logging",
                emoji="📄",
                value="transcripts"
            ),
            discord.SelectOption(
                label="Appearance",
                description="Customize embeds",
                emoji="🎨",
                value="appearance"
            ),
        ]
        super().__init__(
            placeholder="Select a setup section...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, inter: discord.Interaction):
        section = self.values[0]
        setup_channel_id = inter.message.channel.id if inter.message else None
        setup_message_id = inter.message.id if inter.message else None

        if section == "panel":
            return await inter.response.send_message(
                embed=build_panel_embed(inter.guild),
                view=PanelManagerView(setup_channel_id, setup_message_id),
                ephemeral=True
            )

        if section == "staff":
            return await inter.response.send_message(
                "Select a role:",
                view=StaffRoleSelectView(inter.guild, setup_channel_id, setup_message_id),
                ephemeral=True
            )

        if section == "logs":
            return await inter.response.send_message(
                "Select a channel:",
                view=LogChannelSelectView(inter.guild, setup_channel_id, setup_message_id),
                ephemeral=True
            )

        if section == "categories":
            return await inter.response.send_message(
                embed=build_categories_embed(inter.guild),
                view=CategoryView(setup_channel_id, setup_message_id),
                ephemeral=True
            )

        if section == "transcripts":
            return await inter.response.send_message(
                embed=build_settings_embed(inter.guild),
                view=TranscriptView(setup_channel_id, setup_message_id),
                ephemeral=True
            )

        await inter.response.send_message(
            "🎨 Appearance settings are coming soon. Use the panel description editor for now.",
            ephemeral=True
        )


class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.add_item(SetupMenu())


class StaffRolePicker(discord.ui.RoleSelect):
    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id
        super().__init__(
            placeholder="Select a staff role...",
            min_values=1,
            max_values=1
        )

    async def callback(self, inter: discord.Interaction):
        role = self.values[0]
        gcfg = get_gcfg(inter.guild.id)
        gcfg["staff_role_id"] = role.id
        set_gcfg(inter.guild.id, gcfg)
        await audit(inter.guild, inter.user, f"set staff role to {role.mention}")
        await inter.response.send_message(f"✅ Staff role set to {role.mention}", ephemeral=True)
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)


class StaffRoleSelectView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.add_item(StaffRolePicker(setup_channel_id, setup_message_id))


class LogChannelPicker(discord.ui.ChannelSelect):
    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id
        super().__init__(
            placeholder="Select a log channel...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, inter: discord.Interaction):
        selected = self.values[0]
        channel = inter.guild.get_channel(selected.id) if inter.guild else None
        if not isinstance(channel, discord.TextChannel):
            return await inter.response.send_message("❌ Please select a text channel.", ephemeral=True)

        gcfg = get_gcfg(inter.guild.id)
        gcfg["log_channel_id"] = channel.id
        set_gcfg(inter.guild.id, gcfg)
        await audit(inter.guild, inter.user, f"set log channel to {channel.mention}")
        await inter.response.send_message(f"✅ Log channel set to {channel.mention}", ephemeral=True)
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)


class LogChannelSelectView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.add_item(LogChannelPicker(setup_channel_id, setup_message_id))


class TranscriptView(discord.ui.View):
    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    @discord.ui.button(label="Toggle Transcripts", style=discord.ButtonStyle.gray)
    async def transcripts(self, inter: discord.Interaction, button: discord.ui.Button):
        gcfg = get_gcfg(inter.guild.id)
        gcfg["log_transcripts"] = not gcfg["log_transcripts"]
        set_gcfg(inter.guild.id, gcfg)

        await audit(inter.guild, inter.user, f"toggled transcripts to {gcfg['log_transcripts']}")
        await inter.response.send_message(
            f"📄 Transcripts logging: **{gcfg['log_transcripts']}**",
            ephemeral=True
        )
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)

class SettingsView(discord.ui.View):
    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    @discord.ui.button(label="👮 Set Staff Role", style=discord.ButtonStyle.blurple)
    async def staff(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(StaffRoleModal(self.setup_channel_id, self.setup_message_id))

    @discord.ui.button(label="📢 Set Log Channel", style=discord.ButtonStyle.blurple)
    async def logs(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(LogChannelModal(self.setup_channel_id, self.setup_message_id))

    @discord.ui.button(label="📄 Toggle Transcripts", style=discord.ButtonStyle.gray)
    async def transcripts(self, inter: discord.Interaction, button: discord.ui.Button):
        gcfg = get_gcfg(inter.guild.id)
        gcfg["log_transcripts"] = not gcfg["log_transcripts"]
        set_gcfg(inter.guild.id, gcfg)
        
        await audit(inter.guild, inter.user, f"toggled transcripts to {gcfg['log_transcripts']}")
        await inter.response.send_message(
            f"📄 Transcripts logging: **{gcfg['log_transcripts']}**",
            ephemeral=True
        )
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)

class CategoryView(discord.ui.View):
    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    @discord.ui.button(label="➕ Add Category", style=discord.ButtonStyle.green)
    async def add(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(AddCategoryModal(self.setup_channel_id, self.setup_message_id))

    @discord.ui.button(label="✏️ Edit Category", style=discord.ButtonStyle.blurple)
    async def edit(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(EditCategoryModal(self.setup_channel_id, self.setup_message_id))

    @discord.ui.button(label="🗑️ Delete Category", style=discord.ButtonStyle.red)
    async def delete(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(DeleteCategoryModal(self.setup_channel_id, self.setup_message_id))

    @discord.ui.button(label="🗑️ Clear Categories", style=discord.ButtonStyle.gray)
    async def clear(self, inter: discord.Interaction, button: discord.ui.Button):
        clear_categories(inter.guild.id)
        await audit(inter.guild, inter.user, "cleared all categories")
        await inter.response.send_message("🧹 Categories cleared.", ephemeral=True)
        await refresh_setup_panel(inter.guild, self.setup_channel_id, self.setup_message_id)

    @discord.ui.button(label="📃 View Categories", style=discord.ButtonStyle.gray)
    async def view(self, inter: discord.Interaction, button: discord.ui.Button):
        cats = get_categories(inter.guild.id)
        if not cats:
            text = "No categories configured."
        else:
            text = "\n".join([f"• {c['name']} (ID: `{c['id']}`)" for c in cats])
        await inter.response.send_message(f"**Categories:**\n{text}", ephemeral=True)

class PanelManagerView(discord.ui.View):
    def __init__(self, setup_channel_id: int | None = None, setup_message_id: int | None = None):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    # TODO: Ensure panel persists across bot restarts and old panels continue to work
    @discord.ui.button(label="📨 Send Panel Here", style=discord.ButtonStyle.green)
    async def send(self, inter: discord.Interaction, button: discord.ui.Button):
        await send_ticket_panel(inter, self.setup_channel_id, self.setup_message_id)

    @discord.ui.button(label="✏️ Edit Description", style=discord.ButtonStyle.blurple)
    async def edit(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(PanelDescModal(self.setup_channel_id, self.setup_message_id))

async def send_ticket_panel(
    inter: discord.Interaction,
    setup_channel_id: int | None = None,
    setup_message_id: int | None = None
):
    gcfg = get_gcfg(inter.guild.id)
    cats = get_categories(inter.guild.id)
    
    if not cats:
        return await inter.response.send_message("⚠️ No categories configured. Add some categories first!", ephemeral=True)

    embed = discord.Embed(
        title=DEFAULT_PANEL_TITLE,
        description=gcfg.get("panel_description") or DEFAULT_PANEL_DESCRIPTION,
        color=BLUE
    )

    view = build_panel_view(inter.guild)
    msg = await inter.channel.send(embed=embed, view=view)

    gcfg["panel_channel_id"] = inter.channel.id
    gcfg["panel_message_id"] = msg.id
    set_gcfg(inter.guild.id, gcfg)
    await inter.response.send_message("✅ Ticket panel created in this channel.", ephemeral=True)
    await refresh_setup_panel(inter.guild, setup_channel_id, setup_message_id)
