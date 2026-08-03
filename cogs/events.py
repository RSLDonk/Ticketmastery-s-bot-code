import time

import discord
from discord.ext import commands, tasks

from .database import (
    get_all_gcfg,
    get_categories,
)
from .views import TicketButtons, build_panel_view


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @tasks.loop(minutes=5)
    async def presence_loop(self):
        statuses = [
            ("Watching", "tickets 🎫"),
            ("Watching", "support requests 📋"),
            ("Playing", "Managing tickets 🎫"),
            ("Listening", "Tickets | /help"),
            ("Watching", "supporting servers 💬"),
        ]
        current_status = statuses[int(time.time() / 300) % len(statuses)]
        activity_type = (
            discord.ActivityType.watching if current_status[0] == "Watching"
            else discord.ActivityType.playing if current_status[0] == "Playing"
            else discord.ActivityType.listening
        )
        try:
            await self.bot.change_presence(activity=discord.Activity(type=activity_type, name=current_status[1]))
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            synced = await self.bot.tree.sync()
            print(f"✅ Synced {len(synced)} global slash commands.")
        except Exception as exc:
            print(f"Slash sync error: {exc}")

        try:
            self.bot.add_view(TicketButtons())
        except Exception as exc:
            print(f"add_view warning: {exc}")

        all_gcfg = get_all_gcfg()
        for gid_str, gcfg_data in all_gcfg.items():
            gid = int(gid_str)
            guild = self.bot.get_guild(gid)
            if not guild:
                continue

            panel_msg_id = gcfg_data.get("panel_message_id")
            cats = get_categories(gid)
            if not panel_msg_id or not cats:
                continue

            try:
                view = build_panel_view(guild)
                self.bot.add_view(view, message_id=panel_msg_id)
            except Exception:
                pass

        if not self.presence_loop.is_running():
            self.presence_loop.start()
        print(f"Bot ready as {self.bot.user}")


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
