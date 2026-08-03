import time
from datetime import datetime
from typing import Any, Dict

import discord
from discord import app_commands

from .config import BLUE, OWNER_ID
from .database import get_gcfg


def base_embed(title: str, description: str = "", color=BLUE) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


def is_admin_or_owner(inter: discord.Interaction) -> bool:
    if inter.user.id == OWNER_ID:
        return True
    if isinstance(inter.user, discord.Member):
        return inter.user.guild_permissions.administrator
    return False


def admin_owner_check():
    async def predicate(inter: discord.Interaction):
        if not is_admin_or_owner(inter):
            await inter.response.send_message("🚫 Admins (or bot owner) only.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)


async def send_log(guild: discord.Guild, embed: discord.Embed, file: discord.File | None = None):
    gcfg = get_gcfg(guild.id)
    cid = gcfg.get("log_channel_id")
    if not cid:
        return
    ch = guild.get_channel(cid)
    if not ch:
        return
    embed.timestamp = discord.utils.utcnow()
    try:
        await ch.send(embed=embed, file=file)
    except discord.Forbidden:
        pass


async def audit(guild: discord.Guild, user: discord.User, action: str):
    if not guild:
        return
    e = base_embed(
        "⚙️ Admin Action",
        f"{user.mention} → {action}",
        discord.Color.gold()
    )
    await send_log(guild, e)


def build_transcript_embed(
    ticket_info: Dict[str, Any],
    closer: discord.User,
    channel: discord.TextChannel,
    guild: discord.Guild,
    close_reason: str = "No reason specified"
) -> discord.Embed:
    opener_id = ticket_info.get("owner_id")
    claimed_by = ticket_info.get("assigned_to")
    created = ticket_info.get("created_at", int(time.time()))
    now = int(time.time())

    created_dt = datetime.fromtimestamp(created)
    closed_dt = datetime.fromtimestamp(now)
    created_at = f"{created_dt.strftime('%B')} {created_dt.day}, {created_dt.year} at {created_dt.strftime('%I:%M %p').lstrip('0')}"
    closed_at = f"{closed_dt.month}/{closed_dt.day}/{str(closed_dt.year)[-2:]}, {closed_dt.strftime('%I:%M %p').lstrip('0')}"
    reason = close_reason.strip() if close_reason else "No reason specified"

    e = discord.Embed(title="Ticket Closed", color=discord.Color.green())
    if guild.icon:
        e.set_author(name=guild.name, icon_url=guild.icon.url)
    else:
        e.set_author(name=guild.name)

    e.add_field(name="🔢 Ticket ID", value=f"{ticket_info.get('num', 'N/A')}", inline=True)
    e.add_field(name="✅ Opened By", value=f"<@{opener_id}>" if opener_id else "Unknown", inline=True)
    e.add_field(name="🔒 Closed By", value=closer.mention, inline=True)
    e.add_field(name="🕒 Open Time", value=created_at, inline=True)
    e.add_field(name="👤 Claimed By", value=f"<@{claimed_by}>" if claimed_by else "Unclaimed", inline=True)
    e.add_field(name="❔ Reason", value=reason[:1024], inline=False)
    e.set_footer(text=closed_at)
    e.timestamp = discord.utils.utcnow()

    return e
