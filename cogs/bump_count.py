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

        # 二重カウント防止：message_id -> last_seen_utc
        self.processed_message_ids: dict[int, datetime] = {}
        self._processed_ttl_sec = 60 * 60  # 1時間くらい覚えておけば十分

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
            await ch.send(content[:1900])  # 雑に2000制限回避
        except (discord.Forbidden, discord.HTTPException):
            pass

    def _cleanup_processed(self):
        now = datetime.utcnow()
        dead = [mid for mid, t in self.processed_message_ids.items()
                if (now - t).total_seconds() > self._processed_ttl_sec]
        for mid in dead:
            self.processed_message_ids.pop(mid, None)

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

    def _message_components_dump(self, message: discord.Message) -> str:
        # できる範囲で “何か付いてるか” を覗く（ボタンとか）
        rows = []
        for row in (message.components or []):
            children = []
            for c in getattr(row, "children", []) or []:
                children.append({
                    "type": str(getattr(c, "type", None)),
                    "label": getattr(c, "label", None),
                    "custom_id": getattr(c, "custom_id", None),
                    "url": getattr(c, "url", None),
                })
            rows.append({
                "row_type": str(getattr(row, "type", None)),
                "children": children
            })
        return str(rows)

    # ===============================
    # 成功判定
    # ===============================
    def _is_disboard_success(self, embed: discord.Embed) -> bool:
        text = self._embed_text(embed)
        return DISBOARD_SUCCESS_TEXT in text

    def _is_dissoku_success(self, embed: discord.Embed) -> bool:
        text = self._embed_text(embed)

        if any(w in text for w in DISSOKU_NG_WORDS):
            return False

        if not DISSOKU_SUCCESS_RE.search(text):
            return False

        # これが原因で取りこぼす可能性もある。まずは現物重視で必須にしてる。
        if DISSOKU_CMD_TEXT not in text:
            return False

        return True

    # ===============================
    # 成功処理（共通化）
    # ===============================
    async def _handle_success(
        self,
        message: discord.Message,
        provider: str,
        cooldown: int,
        embed: discord.Embed | None,
        via: str,  # "message" / "edit"
    ):
        self._cleanup_processed()

        # 二重処理防止（編集で拾った時に2回加算されがちなので）
        if message.id in self.processed_message_ids:
            return
        self.processed_message_ids[message.id] = datetime.utcnow()

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

        # ===== リマインド =====
        key = (message.channel.id, provider)
        if key not in self.scheduled_reminders:
            task = asyncio.create_task(
                self.bump_reminder(message.guild, message.channel, provider, cooldown, user_id)
            )
            self.scheduled_reminders[key] = (task, user_id)

        # ===== デバッグ（成功ログ）=====
        if provider == "dissoku":
            text = self._embed_text(embed) if embed else "(no embed)"
            await self._debug_send(
                message.guild,
                "【DISSOKU DEBUG】SUCCESS handled\n"
                f"via={via}\n"
                f"message_id={message.id}\n"
                f"channel_id={message.channel.id}\n"
                f"user_id={user_id}\n"
                f"interaction_metadata={'yes' if getattr(message, 'interaction_metadata', None) else 'no'}\n"
                "---- text ----\n"
                f"{text}"
            )

    # ===============================
    # BUMP / UP 検知（新規メッセージ）
    # ===============================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id not in (DISBOARD_BOT_ID, DISSOKU_BOT_ID):
            return

        provider = "disboard" if message.author.id == DISBOARD_BOT_ID else "dissoku"
        cooldown = DISBOARD_COOLDOWN if provider == "disboard" else DISSOKU_COOLDOWN

        # embed無し：ディス速はここが“本体”の可能性があるので、情報を出す
        if not message.embeds:
            if provider == "dissoku":
                await self._debug_send(
                    message.guild,
                    "【DISSOKU DEBUG】embed無しでメッセージが来た\n"
                    f"message_id={message.id}\n"
                    f"channel={getattr(message.channel, 'id', None)}\n"
                    f"content={message.content!r}\n"
                    f"attachments={len(message.attachments)}\n"
                    f"stickers={len(getattr(message, 'stickers', []) or [])}\n"
                    f"flags={getattr(message, 'flags', None)}\n"
                    f"type={getattr(message, 'type', None)}\n"
                    f"components={self._message_components_dump(message)}\n"
                )
            return

        # embed有り
        embed = message.embeds[0]
        ok = self._is_disboard_success(embed) if provider == "disboard" else self._is_dissoku_success(embed)

        # デバッグ（ディス速）
        if provider == "dissoku":
            await self._debug_send(
                message.guild,
                "【DISSOKU DEBUG】判定ログ(on_message)\n"
                f"ok={ok}\n"
                f"message_id={message.id}\n"
                f"channel_id={message.channel.id}\n"
                f"interaction_metadata={'yes' if getattr(message, 'interaction_metadata', None) else 'no'}\n\n"
                "---- embed dump ----\n"
                f"{self._embed_debug_dump(embed)}\n\n"
                "---- embed_text ----\n"
                f"{self._embed_text(embed)}"
            )

        if not ok:
            return

        await self._handle_success(message, provider, cooldown, embed, via="message")

    # ===============================
    # BUMP / UP 検知（編集：後からembedが付くケース）
    # ===============================
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # ディス速だけ監視（DISBOARDは基本編集しない想定）
        if after.author.id != DISSOKU_BOT_ID:
            return

        # afterにembedが付いたら、ここが勝ち筋
        if not after.embeds:
            return

        embed = after.embeds[0]
        ok = self._is_dissoku_success(embed)

        await self._debug_send(
            after.guild,
            "【DISSOKU DEBUG】判定ログ(on_message_edit)\n"
            f"ok={ok}\n"
            f"message_id={after.id}\n"
            f"channel_id={after.channel.id}\n"
            f"before_embeds={len(before.embeds)} after_embeds={len(after.embeds)}\n"
            f"interaction_metadata={'yes' if getattr(after, 'interaction_metadata', None) else 'no'}\n\n"
            "---- embed dump ----\n"
            f"{self._embed_debug_dump(embed)}\n\n"
            "---- embed_text ----\n"
            f"{self._embed_text(embed)}"
        )

        if not ok:
            return

        await self._handle_success(after, "dissoku", DISSOKU_COOLDOWN, embed, via="edit")

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
                await interaction.response.send_message("まだ誰も BUMP してない。静かすぎる。", ephemeral=True)
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
            name = member.display_name if member else "不明な冒険者"
            mention = member.mention if member else f"<@{row['user_id']}>"
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
                await interaction.response.send_message("まだ誰も UP してない。平和すぎる。", ephemeral=True)
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
            name = member.display_name if member else "不明な冒険者"
            mention = member.mention if member else f"<@{row['user_id']}>"
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
