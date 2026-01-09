# cogs/bump_listener.py

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import asyncio

DISBOARD_BOT_ID = 302050872383242240
SUCCESS_TEXT = "表示順をアップしたよ"
BUMP_COOLDOWN = 60 * 60 * 2  # 2時間


class BumpListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # channel_id: (task, user_id)
        self.scheduled_reminders: dict[int, tuple[asyncio.Task, int | None]] = {}

    # ===============================
    # BUMP 検知
    # ===============================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # DISBOARD 以外は無視
        if message.author.id != DISBOARD_BOT_ID:
            return

        if not message.embeds:
            return

        embed = message.embeds[0]
        description = embed.description or ""

        # 成功メッセージ判定
        if SUCCESS_TEXT not in description:
            return

        # interaction_metadata 優先
        user_id: int | None = None
        metadata = getattr(message, "interaction_metadata", None)
        if metadata and metadata.user:
            user_id = metadata.user.id

        # ===== DB処理 =====
        current_amount: int | None = None

        if user_id is not None:
            async with self.bot.db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO bump_amount (user_id, amount)
                    VALUES ($1, 1)
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        amount = bump_amount.amount + 1
                    RETURNING amount;
                    """,
                    user_id
                )
                current_amount = row["amount"]

        # ===== 成功メッセージ =====
        await self.send_success_embed(message, user_id, current_amount)

        # ===== リマインド =====
        channel_id = message.channel.id
        if channel_id in self.scheduled_reminders:
            return

        task = asyncio.create_task(
            self.bump_reminder(message.guild, message.channel, user_id)
        )
        self.scheduled_reminders[channel_id] = (task, user_id)

    # ===============================
    # 成功 Embed
    # ===============================
    async def send_success_embed(
        self,
        message: discord.Message,
        user_id: int | None,
        amount: int | None
    ):
        next_bump = datetime.utcnow() + timedelta(seconds=BUMP_COOLDOWN)

        member = (
            message.guild.get_member(user_id)
            if user_id and message.guild
            else None
        )

        mention = member.mention if member else "誰か"

        amount_text = (
            f"🎉 **{amount} 回目の BUMP！**"
            if amount is not None
            else "🎉 **BUMP 成功！**"
        )

        embed = discord.Embed(
            title="🚀 BUMP 成功！",
            description=f"{mention} が /bump を実行しました。\n\n{amount_text}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name="⏰ 次のBUMP可能時刻",
            value=f"<t:{int(next_bump.timestamp())}:R>",
            inline=False
        )

        # 実行者アイコン（中サイズ）
        if member and member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        embed.set_footer(text="DISBOARD Bump Tracker")

        await message.channel.send(embed=embed)

    # ===============================
    # リマインド
    # ===============================
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
                description=f"`/bump` の時間だよ。\n"f"</bump:947088344167366698>",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )

            await channel.send(embed=embed)

        finally:
            self.scheduled_reminders.pop(channel.id, None)

    # ===============================
    # /bumprank ギルドコマンド
    # ===============================
    @app_commands.command(
        name="bumprank",
        description="BUMP 回数ランキングを表示します"
    )
    @app_commands.guild_only()
    async def bump_rank(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        guild = interaction.guild

        async with self.bot.db.acquire() as conn:
            top_rows = await conn.fetch(
                """
                SELECT user_id, amount
                FROM bump_amount
                ORDER BY amount DESC
                LIMIT 10;
                """
            )

            if not top_rows:
                await interaction.response.send_message(
                    "まだ誰も BUMP してない。静かすぎる。",
                    ephemeral=True
                )
                return

            top_user_ids = [r["user_id"] for r in top_rows]
            is_in_top10 = user_id in top_user_ids

            user_rank_row = None
            if not is_in_top10:
                user_rank_row = await conn.fetchrow(
                    """
                    SELECT rank, amount FROM (
                        SELECT
                            user_id,
                            amount,
                            RANK() OVER (ORDER BY amount DESC) AS rank
                        FROM bump_amount
                    ) t
                    WHERE user_id = $1;
                    """,
                    user_id
                )

        lines = []

        for i, row in enumerate(top_rows, start=1):
            member = guild.get_member(row["user_id"]) if guild else None

            if member:
                name = member.display_name
                mention = member.mention
            else:
                name = "不明な冒険者"
                mention = f"<@{row['user_id']}>"

            lines.append(
                f"**{i}.** {name}（{mention}） ― `{row['amount']}` 回"
            )

        # 実行者がTOP10外なら追記
        if user_rank_row:
            member = guild.get_member(user_id)
            name = member.display_name if member else interaction.user.name

            lines.append("\n――――――――――")
            lines.append(
                f"**あなたの順位：{user_rank_row['rank']} 位**\n"
                f"{name}（{interaction.user.mention}） ― `{user_rank_row['amount']}` 回"
            )

        embed = discord.Embed(
            title="🏆 BUMP ランキング TOP10",
            description="\n".join(lines),
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpListener(bot))
