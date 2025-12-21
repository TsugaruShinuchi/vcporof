import discord
from discord.ext import commands
import asyncio

DISBOARD_BOT_ID = 302050872383242240
REMIND_AFTER = 60 * 60 * 2  # 2時間

class BumpCount(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool = bot.profile_db_pool  # ← 既存のDBプールを使う

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bot以外は無視
        if not message.author.bot:
            return

        # DISBOARD以外は無視
        if message.author.id != DISBOARD_BOT_ID:
            return

        # Embedなしは無視
        if not message.embeds:
            return

        embed = message.embeds[0]
        description = (embed.description or "").lower()

        # bump 成功っぽい文言だけ拾う（雑でOK）
        if "表示順をアップしたよ" not in description:
            return

        # footer から実行者取得
        if not embed.footer or not embed.footer.text:
            return

        footer_text = embed.footer.text.replace("Bumped by ", "").strip()

        # username#1234 を想定
        if "#" not in footer_text:
            return

        name, discrim = footer_text.rsplit("#", 1)

        member = discord.utils.find(
            lambda m: m.name == name and m.discriminator == discrim,
            message.guild.members
        )

        if not member:
            return

        # DBに加算
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

        # 通知は別タスクで
        asyncio.create_task(
            self.remind_later(member, message.channel)
        )

    async def remind_later(self, member: discord.Member, channel: discord.TextChannel):
        await asyncio.sleep(REMIND_AFTER)
        try:
            await channel.send(
                f"⏰ {member.mention} そろそろ /bump の時間だよ"
            )
        except discord.Forbidden:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(BumpCount(bot))
