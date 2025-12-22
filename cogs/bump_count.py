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
        self.scheduled_reminders: dict[int, asyncio.Task] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # DISBOARD Bot 以外は無視
        if message.author.id != DISBOARD_BOT_ID:
            return

        if not message.embeds:
            return

        embed = message.embeds[0]
        description = embed.description or ""

        if SUCCESS_TEXT not in description:
            return

        member = self.extract_executor(message, embed)

        # 成功通知
        await self.send_success_embed(message, member)

        channel_id = message.channel.id

        # すでにスケジュール済みなら何もしない
        if channel_id in self.scheduled_reminders:
            return

        # 新規スケジュール
        task = asyncio.create_task(
            self.bump_reminder(message.channel, member)
        )
        self.scheduled_reminders[channel_id] = task

    def extract_executor(
        self,
        message: discord.Message,
        embed: discord.Embed
    ) -> discord.Member | None:
        if not embed.footer or not embed.footer.text:
            return None

        footer = embed.footer.text

        match = re.search(r"<@!?(\d+)>", footer)
        if match:
            return message.guild.get_member(int(match.group(1)))

        name = footer.replace("Bumped by", "").strip()
        return discord.utils.find(
            lambda m: m.display_name == name or m.name == name,
            message.guild.members
        )

    async def send_success_embed(
        self,
        message: discord.Message,
        member: discord.Member | None
    ):
        next_bump = datetime.utcnow() + timedelta(hours=2)
        mention = member.mention if member else "誰か"

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
        channel: discord.TextChannel,
        member: discord.Member | None
    ):
        try:
            await asyncio.sleep(BUMP_COOLDOWN)

            mention = member.mention if member else "@here"

            embed = discord.Embed(
                title="⏰ BUMP の時間！",
                description=f"{mention} そろそろ `/bump` できるよ。",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )

            await channel.send(embed=embed)

        finally:
            # 通知後 or 途中キャンセルでも必ず消す
            self.scheduled_reminders.pop(channel.id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpListener(bot))
