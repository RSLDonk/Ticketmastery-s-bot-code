import os

import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or ""
OWNER_ID = 720061069628014652
SUPPORT_FEEDBACK_CHANNEL_ID = 1533866841146130564

BLUE = discord.Color.blurple()
TICKET_CREATION_COOLDOWN_SECONDS = 60

DEFAULT_PANEL_TITLE = "🎫 Need Support?"
DEFAULT_PANEL_DESCRIPTION = "\n".join([
    "Welcome to our support center. Select the category below that best matches your request, and a staff member will assist you as soon as possible.",
    "",
    "Before creating a ticket:",
    "• Explain your issue clearly",
    "• Provide any important details",
    "• Be respectful and patient with staff",
    "",
    "Please avoid opening unnecessary tickets.",
])

DEFAULT_TICKET_TITLE = "🎫 Ticket Created"
DEFAULT_TICKET_DESCRIPTION = "\n".join([
    "Thank you for contacting support!",
    "",
    "A staff member will be with you shortly. While you wait, please describe your issue with as much detail as possible.",
    "",
    "Helpful information:",
    "• What do you need help with?",
    "• When did the issue happen?",
    "• Any screenshots or extra details?",
    "",
    "A team member will review your request soon.",
])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "guild_config.db")
