import asyncpg
import os

class DB:
    pool = None

    @classmethod
    async def init_pool(cls):
        cls.pool = await asyncpg.create_pool(os.getenv("POSTGRES_URI"))

    @classmethod
    async def get_profile_message_link(cls, user_id: str):
        async with cls.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT channel_id, message_id FROM prof WHERE user_id = $1", user_id
            )
            if row:
                guild_id = os.getenv("GUILD_ID")
                return f"https://discord.com/channels/{guild_id}/{row['channel_id']}/{row['message_id']}"
            return None
