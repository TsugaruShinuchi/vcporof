import os
from discord import Color

ROLE_BRAVE = int(os.getenv("ROLE_BRAVE_ID"))
ROLE_PRINCESS = int(os.getenv("ROLE_PRINCESS_ID"))
ROLE_INN = int(os.getenv("ROLE_INN_ID"))
ROLE_HAPPY = int(os.getenv("ROLE_HAPPY_ID"))
ROLE_FAIRY = int(os.getenv("ROLE_FAIRY_ID"))

def determine_color(embed_color, member):
    if embed_color:
        try:
            return int(embed_color.strip().lstrip("#"), 16)
        except:
            pass
    rids = [r.id for r in member.roles]
    if any(r in (ROLE_INN, ROLE_HAPPY, ROLE_FAIRY) for r in rids):
        return 0x00FF00
    if ROLE_PRINCESS in rids:
        return 0xFFC0CB
    if ROLE_BRAVE in rids:
        return 0xBCE2E8
    return Color.default()
