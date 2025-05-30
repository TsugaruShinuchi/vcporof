import asyncpg
import os

class DB:
    pool = None

    @classmethod
    async def init_pool(cls):
        cls.pool = await asyncpg.create_pool(os.getenv("POSTGRES_URI"))

    @classmethod
    async def get_profile_message_link(cls, user: 'discord.Member'):
        async with cls.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT message_id FROM prof WHERE user_id = $1", int(user.id))
            if not row:
                return None

            role_ids = [r.id for r in user.roles]

            if any(int(os.getenv(k)) in role_ids for k in ["ROLE_NONPLAYER1_ID", "ROLE_NONPLAYER2_ID", "ROLE_NONPLAYER3_ID"]):
                channel_id = os.getenv("PROFILE_CHANNEL_NONPLAYER_ID")
            elif int(os.getenv("ROLE_PRINCESS_ID")) in role_ids:
                channel_id = os.getenv("PROFILE_CHANNEL_PRINCESS_ID")
            elif int(os.getenv("ROLE_HERO_ID")) in role_ids:
                channel_id = os.getenv("PROFILE_CHANNEL_HERO_ID")
            else:
                return None

            guild_id = os.getenv("GUILD_ID")
            return f"https://discord.com/channels/{guild_id}/{channel_id}/{row['message_id']}"
