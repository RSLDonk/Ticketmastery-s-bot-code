import io
import time
from typing import Any, Dict, List, Optional

import discord

from .database import (
    add_open_ticket,
    get_gcfg,
    remove_open_ticket,
    set_gcfg,
)
from .interaction_guard import (
    add_active_interaction,
    check_active_interaction,
    remove_active_interaction,
)
from .utils import base_embed, build_transcript_embed, send_log

class TicketManager:
    """Central ticket operation manager - prevents duplicated logic."""
    
    @staticmethod
    def sanitize_channel_name(name: str, max_len: int = 15) -> str:
        """Safe channel name creation."""
        return name.lower().replace(" ", "-")[:max_len]
    
    @staticmethod
    def build_ticket_channel_name(num: int, user_name: str) -> str:
        """Ticket naming based on the ticket number."""
        return f"ticket-{num:04d}"

    @staticmethod
    def build_txt_transcript(
        messages: List[tuple],
        ticket_info: Dict[str, Any],
        closer: discord.User,
        close_reason: str
    ) -> str:
        lines = [
            f"Ticket #{ticket_info.get('num', 'N/A')} Closed",
            f"Closed by: {closer}",
            f"Claimed by: {ticket_info.get('assigned_to') or 'Unclaimed'}",
            f"Reason: {close_reason}",
            "",
            "Transcript:",
        ]

        if messages:
            lines.extend(f"[{ts}] {author}: {content}" for ts, author, content in messages)
        else:
            lines.append("(No messages in transcript)")

        return "\n".join(lines)

    @staticmethod
    async def create_ticket(
        inter: discord.Interaction,
        guild: discord.Guild,
        user: discord.User,
        category_data: Dict[str, Any],
        gcfg: Dict[str, Any]
    ) -> Optional[discord.TextChannel]:
        """
        Create a new ticket channel safely with interaction guard.
        Returns: created TextChannel or None if failed.
        """
        # Check if already processing ticket creation
        if check_active_interaction(user.id, inter.channel.id, "ticket_create"):
            await inter.followup.send("⏳ Already creating a ticket for you...", ephemeral=True)
            return None
        
        add_active_interaction(user.id, inter.channel.id, "ticket_create")
        
        try:
            # Get fresh config to increment counter
            gcfg = get_gcfg(guild.id)
            gcfg["tickets_created"] = int(gcfg.get("tickets_created", 0)) + 1
            num = gcfg["tickets_created"]
            set_gcfg(guild.id, gcfg)
            
            # Ensure Discord category exists
            disc_cat = discord.utils.get(guild.categories, name=category_data["name"])
            if disc_cat is None:
                try:
                    disc_cat = await guild.create_category(category_data["name"])
                except Exception:
                    disc_cat = None
            
            # Build permission overwrites
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True
                ),
            }
            
            # Add staff role if configured
            staff_role_id = gcfg.get("staff_role_id")
            if staff_role_id:
                role = guild.get_role(staff_role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
            
            # Create channel with improved naming
            ch_name = TicketManager.build_ticket_channel_name(num, user.name)
            tchan = await guild.create_text_channel(
                name=ch_name,
                category=disc_cat,
                overwrites=overwrites,
                reason=f"Ticket #{num} opened by {user}"
            )
            
            # Register ticket with category
            category_id = category_data.get("id")
            add_open_ticket(guild.id, tchan.id, user.id, num, category_id=category_id)
            
            return tchan
        finally:
            remove_active_interaction(user.id, inter.channel.id, "ticket_create")
    
    @staticmethod
    async def close_ticket(
        bot: discord.Client,
        guild: discord.Guild,
        channel: discord.TextChannel,
        closer: discord.User,
        ticket_info: Dict[str, Any],
        transcripts_enabled: bool = True,
        close_reason: str = "No reason specified"
    ) -> bool:
        """
        Close ticket safely with transcript and logging.
        Returns: True if successful, False if failed.
        """
        try:
            # Build transcript
            messages: List[tuple] = []
            try:
                async for m in channel.history(limit=1000, oldest_first=True):
                    ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    content = m.content or ""
                    messages.append((ts, m.author.name, content))
            except Exception:
                pass
            
            transcript_text = TicketManager.build_txt_transcript(messages, ticket_info, closer, close_reason)
            filename = f"ticket_{channel.id}_{int(time.time())}.txt"
            
            # DM opener
            e = build_transcript_embed(ticket_info, closer, channel, guild, close_reason)
            try:
                opener = await bot.fetch_user(int(ticket_info.get("owner_id", closer.id)))
                dm_file = discord.File(io.BytesIO(transcript_text.encode("utf-8")), filename=filename)
                await opener.send(
                    "📋 Your ticket transcript is attached.",
                    embed=e,
                    file=dm_file
                )
            except Exception:
                pass
            
            if transcripts_enabled:
                log_file = discord.File(io.BytesIO(transcript_text.encode("utf-8")), filename=filename)
                await send_log(guild, e, file=log_file)
            else:
                await send_log(guild, e)
            
            # Remove from registry
            remove_open_ticket(guild.id, channel.id)
            
            # Delete channel with fallback
            try:
                await channel.delete(reason=f"Ticket closed by {closer}: {close_reason[:400]}")
            except Exception as e:
                # Log deletion failure
                await send_log(
                    guild,
                    base_embed(
                        "⚠️ Ticket Cleanup Failed",
                        f"Could not delete <#{channel.id}>\nError: {str(e)[:100]}",
                        discord.Color.orange()
                    )
                )

            return True
        except Exception:
            return False
