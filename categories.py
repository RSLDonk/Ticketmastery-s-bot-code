import time
from typing import Dict

import discord

from .config import (
    DEFAULT_TICKET_DESCRIPTION,
    DEFAULT_TICKET_TITLE,
    TICKET_CREATION_COOLDOWN_SECONDS,
)
from .database import (
    add_category,
    clear_categories,
    get_categories,
    get_category,
    get_gcfg,
    get_open_ticket_by_owner,
    remove_category,
    update_category,
)
from .setup import SETUP_VIEW_TIMEOUT_SECONDS, refresh_setup_panel
from .ticket_controls import TicketButtons
from .ticket_manager import TicketManager
from .utils import audit, base_embed


ticket_creation_cooldowns: Dict[int, int] = {}


class TicketCategorySelect(discord.ui.Select):
    """Category selector displayed on the public ticket panel."""

    def __init__(self, guild: discord.Guild):
        options = [
            discord.SelectOption(label=category["name"][:100], value=str(category["id"]))
            for category in get_categories(guild.id)[:25]
        ]
        super().__init__(
            placeholder="📋 Select a ticket category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"ticket_select:{guild.id}",
        )

    async def callback(self, inter: discord.Interaction):
        category_id = int(self.values[0])
        category = get_category(inter.guild.id, category_id)

        if not category:
            return await inter.response.send_message(
                "⚠️ That category no longer exists.",
                ephemeral=True,
            )

        now = int(time.time())
        if get_open_ticket_by_owner(inter.guild.id, inter.user.id):
            return await inter.response.send_message(
                "❌ You already have an open ticket. Close it before opening a new one.",
                ephemeral=True,
            )

        last_attempt = ticket_creation_cooldowns.get(inter.user.id, 0)
        remaining = TICKET_CREATION_COOLDOWN_SECONDS - (now - last_attempt)
        if remaining > 0:
            return await inter.response.send_message(
                f"⏳ Please wait {remaining}s before creating another ticket.",
                ephemeral=True,
            )

        await inter.response.defer(thinking=True, ephemeral=True)

        gcfg_local = get_gcfg(inter.guild.id)
        tchan = await TicketManager.create_ticket(
            inter,
            inter.guild,
            inter.user,
            category,
            gcfg_local,
        )

        if not tchan:
            return await inter.followup.send(
                "❌ Failed to create ticket channel.",
                ephemeral=True,
            )

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
            ),
        )
        await tchan.send(
            content=f"{inter.user.mention} {role_ping}".strip(),
            embed=embed,
            view=TicketButtons(),
        )

        await inter.followup.send(
            f"✅ Ticket created: {tchan.mention}",
            ephemeral=True,
        )


def build_categories_embed(guild: discord.Guild) -> discord.Embed:
    cats = get_categories(guild.id)
    embed = base_embed(
        "📂 Category Manager",
        "Manage ticket categories.",
    )

    if not cats:
        embed.add_field(
            name="No Categories",
            value="Add some categories to get started!",
            inline=False,
        )
    else:
        lines = []
        for index, category in enumerate(cats, 1):
            name = category.get("name", f"Category {index}")
            role_id = category.get("role_id")
            role_ping = f"<@&{role_id}>" if role_id else "No ping"
            lines.append(
                f"{index}. **{name}** (ID: `{category['id']}`) — {role_ping}"
            )
        embed.add_field(
            name=f"Categories ({len(cats)}/10)",
            value="\n".join(lines),
            inline=False,
        )

    return embed


class AddCategoryModal(discord.ui.Modal, title="Add Ticket Category"):
    name = discord.ui.TextInput(
        label="Category Name",
        placeholder="Enter category name",
    )

    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        cats = get_categories(inter.guild.id)
        if len(cats) >= 10:
            return await inter.response.send_message(
                "❌ You can only have up to 10 categories.",
                ephemeral=True,
            )

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
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )


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
    async def no_ping_role(
        self,
        inter: discord.Interaction,
        button: discord.ui.Button,
    ):
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
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )


class EditCategoryModal(discord.ui.Modal, title="Edit Ticket Category"):
    category_id = discord.ui.TextInput(
        label="Category ID",
        placeholder="Enter the category ID to edit",
    )
    name = discord.ui.TextInput(
        label="New Category Name",
        placeholder="Enter the updated category name",
    )
    role_id = discord.ui.TextInput(
        label="Ping Role ID (optional)",
        placeholder="Enter new role ID or leave blank",
        required=False,
    )

    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        try:
            category_id = int(self.category_id.value)
        except ValueError:
            return await inter.response.send_message(
                "❌ Invalid category ID.",
                ephemeral=True,
            )

        category = get_category(inter.guild.id, category_id)
        if not category:
            return await inter.response.send_message(
                "❌ Category not found.",
                ephemeral=True,
            )

        role_id = None
        if self.role_id.value:
            try:
                role_id = int(self.role_id.value)
                role = inter.guild.get_role(role_id)
                if not role:
                    return await inter.response.send_message(
                        "❌ Role not found in this server.",
                        ephemeral=True,
                    )
            except ValueError:
                return await inter.response.send_message(
                    "❌ Invalid role ID. Please enter a number.",
                    ephemeral=True,
                )

        update_category(inter.guild.id, category_id, self.name.value, role_id)
        await audit(
            inter.guild,
            inter.user,
            f"edited category '{category['name']}' to '{self.name.value}'",
        )
        message = f"✅ Updated category `{self.name.value}`"
        if role_id:
            message += f" (pings <@&{role_id}>)"
        await inter.response.send_message(message, ephemeral=True)
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )


class DeleteCategoryModal(discord.ui.Modal, title="Delete Ticket Category"):
    category_id = discord.ui.TextInput(
        label="Category ID",
        placeholder="Enter the category ID to delete",
    )

    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__()
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    async def on_submit(self, inter: discord.Interaction):
        try:
            category_id = int(self.category_id.value)
        except ValueError:
            return await inter.response.send_message(
                "❌ Invalid category ID.",
                ephemeral=True,
            )

        category = get_category(inter.guild.id, category_id)
        if not category:
            return await inter.response.send_message(
                "❌ Category not found.",
                ephemeral=True,
            )

        remove_category(inter.guild.id, category_id)
        await audit(inter.guild, inter.user, f"deleted category '{category['name']}'")
        await inter.response.send_message(
            f"🗑️ Deleted category `{category['name']}`.",
            ephemeral=True,
        )
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )


class CategoryView(discord.ui.View):
    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    @discord.ui.button(label="➕ Add Category", style=discord.ButtonStyle.green)
    async def add(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(
            AddCategoryModal(self.setup_channel_id, self.setup_message_id)
        )

    @discord.ui.button(label="✏️ Edit Category", style=discord.ButtonStyle.blurple)
    async def edit(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(
            EditCategoryModal(self.setup_channel_id, self.setup_message_id)
        )

    @discord.ui.button(label="🗑️ Delete Category", style=discord.ButtonStyle.red)
    async def delete(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(
            DeleteCategoryModal(self.setup_channel_id, self.setup_message_id)
        )

    @discord.ui.button(label="🗑️ Clear Categories", style=discord.ButtonStyle.gray)
    async def clear(self, inter: discord.Interaction, button: discord.ui.Button):
        clear_categories(inter.guild.id)
        await audit(inter.guild, inter.user, "cleared all categories")
        await inter.response.send_message(
            "🧹 Categories cleared.",
            ephemeral=True,
        )
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )

    @discord.ui.button(label="📃 View Categories", style=discord.ButtonStyle.gray)
    async def view(self, inter: discord.Interaction, button: discord.ui.Button):
        cats = get_categories(inter.guild.id)
        if not cats:
            text = "No categories configured."
        else:
            text = "\n".join(
                f"• {category['name']} (ID: `{category['id']}`)"
                for category in cats
            )
        await inter.response.send_message(
            f"**Categories:**\n{text}",
            ephemeral=True,
        )
