import discord
from discord.ext import commands
import asyncpg
import asyncio
import os

DISBOARD_BOT_ID = 302050872383242240
REMIND_AFTER = 60 * 60 * 2  # 2時間

class BumpCount(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool: asyncpg.Pool | None = None
        bot.loop.create_task(self.init_db())

    async def init_db(self):
        self.pool = await asyncpg.create_pool(
            dsn=os.getenv("POSTGRES_URI"),
            min_size=1,
            max_size=5
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ① Bot以外は無視
        if message.author.bot is False:
            return

        # ② DISBOARD以外は無視
        if message.author.id != DISBOARD_BOT_ID:
            return

        # ③ Embedが無い = bumpじゃない
        if not message.embeds:
            return

        embed = message.embeds[0]

        # ④ bump成功文言チェック
        description = embed.description or ""
        if not (
            "Bump done" in description
            or "表示順をアップしたよ :thumbsup:" in description
        ):
            return

        # ⑤ 実行者取得（footerに書いてある）
        if not embed.footer or not embed.footer.text:
            return

        # footer例: "Bumped by Sengoku"
        footer_text = embed.footer.text.replace("Bumped by ", "").strip()
        member = discord.utils.find(
            lambda m: m.name == footer_text,
            message.guild.members
        )

        if not member:
            return

        # ⑥ DBに加算
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bump_amount (user_id, amount)
                VALUES ($1, 1)
                ON CONFLICT (user_id)
                DO UPDATE SET amount = bump_amount.amount + 1
                """,
                member.id
            )

        # ⑦ 2時間後通知
        await asyncio.sleep(REMIND_AFTER)

        try:
            await message.channel.send(
                f"⏰ {member.mention} そろそろ /bump の時間だよ"
            )
        except discord.Forbidden:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(BumpCount(bot))
