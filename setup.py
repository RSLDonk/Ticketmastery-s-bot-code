import discord

from .database import get_categories, get_gcfg, set_gcfg
from .utils import audit, base_embed


SETUP_VIEW_TIMEOUT_SECONDS = 3 * 60 * 60


def build_setup_embed(guild: discord.Guild) -> discord.Embed:
    gcfg = get_gcfg(guild.id)
    cats = get_categories(guild.id)

    staff_role = f"<@&{gcfg['staff_role_id']}>" if gcfg["staff_role_id"] else "Not Set"
    log_channel = f"<#{gcfg['log_channel_id']}>" if gcfg["log_channel_id"] else "Not Set"
    panel_status = "Created" if gcfg.get("panel_message_id") else "Not Created"

    embed = base_embed(
        "⚙️ TicketMastery Setup",
        "Welcome to the setup panel.\n\nConfigure your ticket system using the options below.\nNo channel IDs or role IDs are required.",
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
        inline=False,
    )
    embed.set_footer(text="Use the menu below to edit your settings.")
    return embed


async def refresh_setup_panel(
    guild: discord.Guild,
    setup_channel_id: int | None,
    setup_message_id: int | None,
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


class StaffRoleModal(discord.ui.Modal, title="Set Staff Role"):
    role_id = discord.ui.TextInput(
        label="Role ID",
        placeholder="Enter the role ID (right-click role > Copy ID)",
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
            role_id = int(self.role_id.value)
            role = inter.guild.get_role(role_id)
            if not role:
                return await inter.response.send_message(
                    "❌ Role not found in this server.",
                    ephemeral=True,
                )

            gcfg = get_gcfg(inter.guild.id)
            gcfg["staff_role_id"] = role_id
            set_gcfg(inter.guild.id, gcfg)
            await audit(inter.guild, inter.user, f"set staff role to {role.mention}")
            await inter.response.send_message(
                f"✅ Staff role set to {role.mention}",
                ephemeral=True,
            )
            await refresh_setup_panel(
                inter.guild,
                self.setup_channel_id,
                self.setup_message_id,
            )
        except ValueError:
            await inter.response.send_message(
                "❌ Invalid role ID. Please enter a number.",
                ephemeral=True,
            )


class LogChannelModal(discord.ui.Modal, title="Set Log Channel"):
    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Enter the channel ID (right-click channel > Copy ID)",
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
            channel_id = int(self.channel_id.value)
            channel = inter.guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return await inter.response.send_message(
                    "❌ Text channel not found in this server.",
                    ephemeral=True,
                )

            gcfg = get_gcfg(inter.guild.id)
            gcfg["log_channel_id"] = channel_id
            set_gcfg(inter.guild.id, gcfg)
            await audit(inter.guild, inter.user, f"set log channel to {channel.mention}")
            await inter.response.send_message(
                f"✅ Log channel set to {channel.mention}",
                ephemeral=True,
            )
            await refresh_setup_panel(
                inter.guild,
                self.setup_channel_id,
                self.setup_message_id,
            )
        except ValueError:
            await inter.response.send_message(
                "❌ Invalid channel ID. Please enter a number.",
                ephemeral=True,
            )


class SetupMenu(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Ticket Panel",
                description="Create or edit your ticket panel",
                emoji="🎫",
                value="panel",
            ),
            discord.SelectOption(
                label="Staff Role",
                description="Select who can manage tickets",
                emoji="👥",
                value="staff",
            ),
            discord.SelectOption(
                label="Logs",
                description="Choose where ticket logs are sent",
                emoji="📋",
                value="logs",
            ),
            discord.SelectOption(
                label="Categories",
                description="Manage ticket categories",
                emoji="📁",
                value="categories",
            ),
            discord.SelectOption(
                label="Transcripts",
                description="Toggle transcript logging",
                emoji="📄",
                value="transcripts",
            ),
            discord.SelectOption(
                label="Appearance",
                description="Customize embeds",
                emoji="🎨",
                value="appearance",
            ),
        ]
        super().__init__(
            placeholder="Select a setup section...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, inter: discord.Interaction):
        section = self.values[0]
        setup_channel_id = inter.message.channel.id if inter.message else None
        setup_message_id = inter.message.id if inter.message else None

        if section == "panel":
            from .panel import PanelManagerView, build_panel_embed

            return await inter.response.send_message(
                embed=build_panel_embed(inter.guild),
                view=PanelManagerView(setup_channel_id, setup_message_id),
                ephemeral=True,
            )

        if section == "staff":
            return await inter.response.send_message(
                "Select a role:",
                view=StaffRoleSelectView(
                    inter.guild,
                    setup_channel_id,
                    setup_message_id,
                ),
                ephemeral=True,
            )

        if section == "logs":
            return await inter.response.send_message(
                "Select a channel:",
                view=LogChannelSelectView(
                    inter.guild,
                    setup_channel_id,
                    setup_message_id,
                ),
                ephemeral=True,
            )

        if section == "categories":
            from .categories import CategoryView, build_categories_embed

            return await inter.response.send_message(
                embed=build_categories_embed(inter.guild),
                view=CategoryView(setup_channel_id, setup_message_id),
                ephemeral=True,
            )

        if section == "transcripts":
            from .transcripts import TranscriptView, build_settings_embed

            return await inter.response.send_message(
                embed=build_settings_embed(inter.guild),
                view=TranscriptView(setup_channel_id, setup_message_id),
                ephemeral=True,
            )

        await inter.response.send_message(
            "🎨 Appearance settings are coming soon. Use the panel description editor for now.",
            ephemeral=True,
        )


class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.add_item(SetupMenu())


class StaffRolePicker(discord.ui.RoleSelect):
    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id
        super().__init__(
            placeholder="Select a staff role...",
            min_values=1,
            max_values=1,
        )

    async def callback(self, inter: discord.Interaction):
        role = self.values[0]
        gcfg = get_gcfg(inter.guild.id)
        gcfg["staff_role_id"] = role.id
        set_gcfg(inter.guild.id, gcfg)
        await audit(inter.guild, inter.user, f"set staff role to {role.mention}")
        await inter.response.send_message(
            f"✅ Staff role set to {role.mention}",
            ephemeral=True,
        )
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )


class StaffRoleSelectView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.add_item(StaffRolePicker(setup_channel_id, setup_message_id))


class LogChannelPicker(discord.ui.ChannelSelect):
    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id
        super().__init__(
            placeholder="Select a log channel...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )

    async def callback(self, inter: discord.Interaction):
        selected = self.values[0]
        channel = inter.guild.get_channel(selected.id) if inter.guild else None
        if not isinstance(channel, discord.TextChannel):
            return await inter.response.send_message(
                "❌ Please select a text channel.",
                ephemeral=True,
            )

        gcfg = get_gcfg(inter.guild.id)
        gcfg["log_channel_id"] = channel.id
        set_gcfg(inter.guild.id, gcfg)
        await audit(inter.guild, inter.user, f"set log channel to {channel.mention}")
        await inter.response.send_message(
            f"✅ Log channel set to {channel.mention}",
            ephemeral=True,
        )
        await refresh_setup_panel(
            inter.guild,
            self.setup_channel_id,
            self.setup_message_id,
        )


class LogChannelSelectView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.add_item(LogChannelPicker(setup_channel_id, setup_message_id))


class SettingsView(discord.ui.View):
    def __init__(
        self,
        setup_channel_id: int | None = None,
        setup_message_id: int | None = None,
    ):
        super().__init__(timeout=SETUP_VIEW_TIMEOUT_SECONDS)
        self.setup_channel_id = setup_channel_id
        self.setup_message_id = setup_message_id

    @discord.ui.button(label="👮 Set Staff Role", style=discord.ButtonStyle.blurple)
    async def staff(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(
            StaffRoleModal(self.setup_channel_id, self.setup_message_id)
        )

    @discord.ui.button(label="📢 Set Log Channel", style=discord.ButtonStyle.blurple)
    async def logs(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(
            LogChannelModal(self.setup_channel_id, self.setup_message_id)
        )

    @discord.ui.button(label="📄 Toggle Transcripts", style=discord.ButtonStyle.gray)
    async def transcripts(self, inter: discord.Interaction, button: discord.ui.Button):
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
