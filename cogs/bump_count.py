# cogs/bump_listener.py

import discord
from discord.ext import commands
from datetime import datetime, timedelta

DISBOARD_BOT_ID = 302050872383242240
SUCCESS_TEXT = "表示順をアップしたよ"

class BumpListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 人間の発言は無視
        if not message.author.bot:
            return

        # DISBOARD 以外は無視
        if message.author.id != DISBOARD_BOT_ID:
            return

        # 成功文言チェック
        if SUCCESS_TEXT not in message.content:
            return

        await self.send_success_embed(message)

    async def send_success_embed(self, message: discord.Message):
        next_bump = datetime.utcnow() + timedelta(hours=2)

        embed = discord.Embed(
            title="🚀 BUMP 成功！",
            description="サーバーの表示順がアップしました。",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name="⏰ 次のBUMP可能時刻",
            value=f"<t:{int(next_bump.timestamp())}:R>",
            inline=False
        )

        embed.set_footer(text="DISBOARD Bump Tracker")

        await message.channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpListener(bot))
