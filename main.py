import asyncio
import sys
from pathlib import Path

import discord
from discord.ext import commands

try:
    from cogs.config import TOKEN
    from cogs.database import init_db
except ModuleNotFoundError as exc:
    if exc.name == "cogs":
        cogs_path = Path(__file__).with_name("cogs")
        print(f"ERROR: Missing cogs package at {cogs_path}")
        print("Upload or deploy the entire cogs/ folder next to main.py, including cogs/__init__.py.")
        sys.exit(1)
    raise


def build_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.messages = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot


async def load_extensions(bot: commands.Bot):
    for extension in ("cogs.events", "cogs.tickets"):
        await bot.load_extension(extension)


async def main():
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN missing in .env")
        return

    init_db()
    bot = build_bot()
    await load_extensions(bot)
    try:
        await bot.start(TOKEN)
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
