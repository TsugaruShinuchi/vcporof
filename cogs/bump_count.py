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

# ディス速：画像だと「をアップしたよ！(全角)」なので両対応にする
DISSOKU_COOLDOWN = 60 * 60 * 2  # 2時間（※ここはあなたの現状のまま）
DISSOKU_SUCCESS_RE = re.compile(r"をアップしたよ[!！]")  # 半角/全角どっちでもOK
DISSOKU_CMD_TEXT = "command: /up"  # 成功画面に出てるので利用（embed fields想定）
DISSOKU_NG_WORDS = ("失敗", "間隔をあけてください", "間隔を開けてください")

# 一時的なデバッグチャンネル（管理者だけ見える場所推奨）
DEBUG_CHANNEL_ID = 1358395770386120742


class BumpListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (channel_id, provider) -> (task, user_id)
        self.scheduled_reminders: dict[tuple[int, str], tuple[asyncio.Task, int | None]] = {}

    # ===============================
    # デバッグ送信（方法3）
    # ===============================
    async def _debug_send(self, guild: discord.Guild | None, content: str):
        if guild is None:
            return
        ch = guild.get_channel(DEBUG_CHANNEL_ID)
        if ch is None:
            return
        try:
            # Discordの2000文字制限を雑に回避
            await ch.send(content[:1900])
        except discord.Forbidden:
            # 権限ないなら諦める
            pass
        except discord.HTTPException:
            pass

    # ===============================
    # embed内テキスト（title + description + fields）
    # ===============================
    def _embed_text(self, embed: discord.Embed) -> str:
        parts: list[str] = []
        if embed.title:
            parts.append(embed.title)
        if embed.description:
            parts.append(embed.description)

        for f in getattr(embed, "fields", []) or []:
            if f.name:
                parts.append(str(f.name))
            if f.value:
                parts.append(str(f.value))

        return "\n".join(parts)

    def _embed_debug_dump(self, embed: discord.Embed) -> str:
        # 見やすいように整形（fieldsも出す）
        lines: list[str] = []
        lines.append(f"title: {embed.title!r}")
        lines.append(f"description: {embed.description!r}")

        if embed.fields:
            lines.append("fields:")
            for i, f in enumerate(embed.fields, start=1):
                lines.append(f"  [{i}] name={f.name!r}")
                lines.append(f"      value={f.value!r}")
        else:
            lines.append("fields: (none)")

        return "\n".join(lines)

    # ===============================
    # 成功判定
    # ===============================
    def _is_disboard_success(self, embed: discord.Embed) -> bool:
        text = self._embed_text(embed)
        return DISBOARD_SUCCESS_TEXT in text

    def _is_dissoku_success(self, embed: discord.Embed) -> bool:
        text = self._embed_text(embed)

        # 失敗系ワード除外
        if any(w in text for w in DISSOKU_NG_WORDS):
            return False

        # 成功文言（半角/全角の!対応）
        if not DISSOKU_SUCCESS_RE.search(text):
            return False

        # 成功画面にある command 行（フィールド想定）
        if DISSOKU_CMD_TEXT not in text:
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

        # embedが無いなら無視（「embed内だけ検知」方針）
        if not message.embeds:
            # ディス速だけは「embed無し」も調査したいのでデバッグ送る（必要なら外してOK）
            if message.author.id == DISSOKU_BOT_ID:
                await self._debug_send(
                    message.guild,
                    "【DISSOKU DEBUG】embed無しでメッセージが来た\n"
                    f"channel={getattr(message.channel, 'id', None)}\n"
                    f"content={message.content!r}"
                )
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

        # ===== デバッグ（ディス速の判定材料を送る）=====
        if provider == "dissoku":
            text = self._embed_text(embed)
            dump = self._embed_debug_dump(embed)
            await self._debug_send(
                message.guild,
                "【DISSOKU DEBUG】判定ログ\n"
                f"ok={ok}\n"
                f"author_id={message.author.id}\n"
                f"channel_id={message.channel.id}\n"
                f"interaction_metadata={'yes' if getattr(message, 'interaction_metadata', None) else 'no'}\n\n"
                "---- embed dump ----\n"
                f"{dump}\n\n"
                "---- embed_text (判定対象) ----\n"
                f"{text}"
            )

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
    # /bumprank（DISBOARD）
    # ===============================
    @app_commands.command(name="bumprank", description="BUMP 回数ランキングを表示します（DISBOARD）")
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
                        SELECT user_id, amount, RANK() OVER (ORDER BY amount DESC) AS rank
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
    # /uprank（ディス速）
    # ===============================
    @app_commands.command(name="uprank", description="UP 回数ランキングを表示します（ディス速）")
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
                        SELECT user_id, amount, RANK() OVER (ORDER BY amount DESC) AS rank
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
