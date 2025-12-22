# cogs/bump_listener.py

import discord
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
import re

DISBOARD_BOT_ID = 302050872383242240
SUCCESS_TEXT = "表示順をアップしたよ"
BUMP_COOLDOWN = 60 * 60 * 2  # 2時間

class BumpListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # channel_id: (task, user_id)
        self.scheduled_reminders: dict[int, tuple[asyncio.Task, int | None]] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id != DISBOARD_BOT_ID:
            return

        if not message.embeds:
            return

        embed = message.embeds[0]
        description = embed.description or ""

        if SUCCESS_TEXT not in description:
            return

        user_id = self.extract_executor_id(embed)

        await self.send_success_embed(message, user_id)

        channel_id = message.channel.id

        # すでにスケジュール済みなら何もしない
        if channel_id in self.scheduled_reminders:
            return

        task = asyncio.create_task(
            self.bump_reminder(message.guild, message.channel, user_id)
        )
        self.scheduled_reminders[channel_id] = (task, user_id)

    def extract_executor_id(self, embed: discord.Embed) -> int | None:
        if not embed.footer or not embed.footer.text:
            return None

        footer = embed.footer.text

        match = re.search(r"<@!?(\d+)>", footer)
        if match:
            return int(match.group(1))

        return None  # 名前ベースは捨てる。精度が低いから。

    async def send_success_embed(
        self,
        message: discord.Message,
        user_id: int | None
    ):
        next_bump = datetime.utcnow() + timedelta(hours=2)

        mention = f"<@{user_id}>" if user_id else "誰か"

        embed = discord.Embed(
            title="🚀 BUMP 成功！",
            description=f"{mention} が /bump を実行しました。",
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

    async def bump_reminder(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user_id: int | None
    ):
        try:
            await asyncio.sleep(BUMP_COOLDOWN)

            member = guild.get_member(user_id) if user_id else None
            mention = member.mention if member else "@here"

            embed = discord.Embed(
                title="⏰ BUMP の時間！",
                description=f"{mention} そろそろ `/bump` できるよ。",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )

            await channel.send(embed=embed)

        finally:
            self.scheduled_reminders.pop(channel.id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpListener(bot))
