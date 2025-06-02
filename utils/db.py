import asyncpg
import os
import traceback

class DB:
    pool = None

    @classmethod
    async def init_pool(cls):
        try:
            uri = os.getenv("POSTGRES_URI")
            print(f"🔍 DB接続URI: {uri}")
            cls.pool = await asyncpg.create_pool(uri)
            print("✅ asyncpg.create_pool 成功")
            return cls.pool
        except Exception as e:
            print("❌ DBプール初期化失敗:")
            traceback.print_exc()  # ← これが重要
            cls.pool = None
            return None

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
        
    @classmethod
    async def save_recruit(cls, user_id: int, channel_id: int, message_id: int):
        async with cls.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO recruit_messages (user_id, channel_id, message_id) VALUES ($1, $2, $3)",
                user_id, channel_id, message_id
            )

    @classmethod
    async def get_all_recruit_messages(cls):
        async with cls.pool.acquire() as conn:
            return await conn.fetch("SELECT user_id, channel_id, message_id FROM recruit_messages")

    @classmethod
    async def delete_recruit_message(cls, message_id: int):
        async with cls.pool.acquire() as conn:
            await conn.execute("DELETE FROM recruit_messages WHERE message_id = $1", message_id)

