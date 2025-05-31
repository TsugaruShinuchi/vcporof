async def set_profile(pool, user_id: int, message_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO prof (user_id, message_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET message_id = $2
        """, user_id, message_id)

async def set_color(pool, user_id: int, color: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE prof SET embed_color = $1 WHERE user_id = $2
        """, color, user_id)

async def get_profile(pool, user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT message_id AS bio, embed_color AS color FROM prof WHERE user_id = $1
        """, user_id)
        return row

