# cogs/bump_listener.py

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from discord import app_commands

# =========================
# Bot IDs
# =========================
DISBOARD_BOT_ID = 302050872383242240
DISSOKU_BOT_ID = 761562078095867916  # ディス速Bot

# =========================
# 判定テキスト / クールダウン
# =========================
DISBOARD_SUCCESS_TEXT = "表示順をアップしたよ"
DISBOARD_COOLDOWN = 60 * 60 * 2  # 2時間

# ディス速は「○○ をアップしたよ!」が成功例
DISSOKU_COOLDOWN = 60 * 60 * 1  # 1時間
DISSOKU_SUCCESS_RE = re.compile(r"をアップしたよ", re.IGNORECASE)
DISSOKU_NG_WORDS = ("失敗", "間隔をあけてください", "間隔を開けてください")


class BumpListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (channel_id, provider) -> (task, user_id)
        self.scheduled_reminders: dict[tuple[int, str], tuple[asyncio.Task, int | None]] = {}

    # ===============================
    # 成功判定
    # ===============================
    def _is_disboard_success(self, embed: discord.Embed) -> bool:
        desc = embed.description or ""
        return DISBOARD_SUCCESS_TEXT in desc

    def _is_dissoku_success(self, embed: discord.Embed) -> bool:
        desc = embed.description or ""
        if not DISSOKU_SUCCESS_RE.search(desc):
            return False
        if any(w in desc for w in DISSOKU_NG_WORDS):
            return False
        return True

    # ===============================
    # BUMP / UP 検知
    # ===============================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 対象Bot以外は無視
        if message.author.id not in (DISBOARD_BOT_ID, DISSOKU_BOT_ID):
            return

        if not message.embeds:
            return

        embed = message.embeds[0]

        # provider 判定
        if message.author.id == DISBOARD_BOT_ID:
            provider = "disboard"
            cooldown = DISBOARD_COOLDOWN
            ok = self._is_disboard_success(embed)
        else:
            provider = "dissoku"
            cooldown = DISSOKU_COOLDOWN
            ok = self._is_dissoku_success(embed)

        if not ok:
            return

        # interaction_metadata 優先
        user_id: int | None = None
        metadata = getattr(message, "interaction_metadata", None)
        if metadata and getattr(metadata, "user", None):
            user_id = metadata.user.id

        # ===== DB処理 =====
        current_amount: int | None = None

        if user_id is not None:
            async with self.bot.db.acquire() as conn:
                if provider == "dissoku":
                    # up_amount(id, user_id UNIQUE, amount)
                    row = await conn.fetchrow(
                        """
                        INSERT INTO up_amount (user_id, amount)
                        VALUES ($1, 1)
                        ON CONFLICT (user_id)
                        DO UPDATE SET amount = up_amount.amount + 1
                        RETURNING amount;
                        """,
                        user_id
                    )
                else:
                    # bump_amount(user_id PK/UNIQUE, amount)
                    row = await conn.fetchrow(
                        """
                        INSERT INTO bump_amount (user_id, amount)
                        VALUES ($1, 1)
                        ON CONFLICT (user_id)
                        DO UPDATE SET amount = bump_amount.amount + 1
                        RETURNING amount;
                        """,
                        user_id
                    )
                current_amount = row["amount"]

        # ===== 成功メッセージ =====
        await self.send_success_embed(message, provider, cooldown, user_id, current_amount)

        # ===== リマインド（同チャンネルでも provider 別に管理）=====
        key = (message.channel.id, provider)
        if key in self.scheduled_reminders:
            return

        task = asyncio.create_task(
            self.bump_reminder(message.guild, message.channel, provider, cooldown, user_id)
        )
        self.scheduled_reminders[key] = (task, user_id)

    # ===============================
    # 成功 Embed
    # ===============================
    async def send_success_embed(
        self,
        message: discord.Message,
        provider: str,
        cooldown: int,
        user_id: int | None,
        amount: int | None
    ):
        next_time = datetime.utcnow() + timedelta(seconds=cooldown)

        member = (
            message.guild.get_member(user_id)
            if user_id and message.guild
            else None
        )

        mention = member.mention if member else "誰か"

        if provider == "dissoku":
            action = "/up"
            title = "🚀 UP 成功！（ディス速）"
            footer = "ディス速 Up Tracker"
        else:
            action = "/bump"
            title = "🚀 BUMP 成功！（DISBOARD）"
            footer = "DISBOARD Bump Tracker"

        amount_text = f"🎉 **{amount} 回目！**" if amount is not None else "🎉 **成功！**"

        embed = discord.Embed(
            title=title,
            description=f"{mention} が {action} を実行しました。\n\n{amount_text}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name="⏰ 次に実行できる時刻",
            value=f"<t:{int(next_time.timestamp())}:R>",
            inline=False
        )

        if member and member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        embed.set_footer(text=footer)
        await message.channel.send(embed=embed)

    # ===============================
    # リマインド
    # ===============================
    async def bump_reminder(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        provider: str,
        cooldown: int,
        user_id: int | None
    ):
        key = (channel.id, provider)
        try:
            await asyncio.sleep(cooldown)

            member = guild.get_member(user_id) if user_id else None
            mention = member.mention if member else "@here"

            if provider == "dissoku":
                cmd = "`/up`"
                title = "⏰ UP の時間！（ディス速）"
                footer = "ディス速 Up Tracker"
            else:
                cmd = "</bump:947088344167366698>"
                title = "⏰ BUMP の時間！（DISBOARD）"
                footer = "DISBOARD Bump Tracker"

            embed = discord.Embed(
                title=title,
                description=f"{mention}\n{cmd} の時間だよ。",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=footer)

            await channel.send(embed=embed)

        finally:
            self.scheduled_reminders.pop(key, None)

    # ===============================
    # /bumprank ギルドコマンド（DISBOARD）
    # ===============================
    @app_commands.command(
        name="bumprank",
        description="BUMP 回数ランキングを表示します（DISBOARD）"
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

        lines: list[str] = []

        for i, row in enumerate(top_rows, start=1):
            member = guild.get_member(row["user_id"]) if guild else None
            if member:
                name = member.display_name
                mention = member.mention
            else:
                name = "不明な冒険者"
                mention = f"<@{row['user_id']}>"

            lines.append(f"**{i}.** {name}（{mention}） ― `{row['amount']}` 回")

        if user_rank_row:
            member = guild.get_member(user_id)
            name = member.display_name if member else interaction.user.name

            lines.append("\n――――――――――")
            lines.append(
                f"**あなたの順位：{user_rank_row['rank']} 位**\n"
                f"{name}（{interaction.user.mention}） ― `{user_rank_row['amount']}` 回"
            )

        embed = discord.Embed(
            title="🏆 BUMP ランキング TOP10（DISBOARD）",
            description="\n".join(lines),
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        await interaction.response.send_message(embed=embed)

    # ===============================
    # /uprank ギルドコマンド（ディス速）
    # ===============================
    @app_commands.command(
        name="uprank",
        description="UP 回数ランキングを表示します（ディス速）"
    )
    @app_commands.guild_only()
    async def up_rank(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        guild = interaction.guild

        async with self.bot.db.acquire() as conn:
            top_rows = await conn.fetch(
                """
                SELECT user_id, amount
                FROM up_amount
                ORDER BY amount DESC
                LIMIT 10;
                """
            )

            if not top_rows:
                await interaction.response.send_message(
                    "まだ誰も UP してない。平和すぎる。",
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
                        FROM up_amount
                    ) t
                    WHERE user_id = $1;
                    """,
                    user_id
                )

        lines: list[str] = []

        for i, row in enumerate(top_rows, start=1):
            member = guild.get_member(row["user_id"]) if guild else None
            if member:
                name = member.display_name
                mention = member.mention
            else:
                name = "不明な冒険者"
                mention = f"<@{row['user_id']}>"

            lines.append(f"**{i}.** {name}（{mention}） ― `{row['amount']}` 回")

        if user_rank_row:
            member = guild.get_member(user_id)
            name = member.display_name if member else interaction.user.name

            lines.append("\n――――――――――")
            lines.append(
                f"**あなたの順位：{user_rank_row['rank']} 位**\n"
                f"{name}（{interaction.user.mention}） ― `{user_rank_row['amount']}` 回"
            )

        embed = discord.Embed(
            title="🏆 UP ランキング TOP10（ディス速）",
            description="\n".join(lines),
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpListener(bot))
