# cogs/bump_listener.py

import discord
from discord.ext import commands

DISBOARD_BOT_ID = 302050872383242240
SUCCESS_TEXT = "表示順をアップしたよ"

class BumpListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bot 自身や他人の雑談は無視
        if message.author.bot is False:
            return

        # DISBOARD Bot 以外は無視
        if message.author.id != DISBOARD_BOT_ID:
            return

        # 成功文言を含んでいるか
        if SUCCESS_TEXT in message.content:
            await self.on_bump_success(message)

    async def on_bump_success(self, message: discord.Message):
        guild = message.guild
        channel = message.channel

        # ログ用。ここをDB加算やロール付与に差し替える
        print(
            f"[BUMP SUCCESS] "
            f"Guild={guild.name if guild else 'DM'} "
            f"Channel={channel.name} "
            f"MessageID={message.id}"
        )

        # 例：リアクション付ける
        try:
            await message.add_reaction("👍")
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpListener(bot))
