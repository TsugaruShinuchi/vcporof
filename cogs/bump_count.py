# cogs/bump_count.py
import os
import asyncio
import discord
from discord.ext import commands

BUMP_CHANNEL_ID = 1358395771895939146

class BumpCount(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_bump_user_id: int | None = None

    # /bump を押した「人」を記録
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.application_command:
            return

        if interaction.command and interaction.command.name == "bump":
            if interaction.channel_id == BUMP_CHANNEL_ID:
                self.last_bump_user_id = interaction.user.id

    # DISBOARDの結果Embedを検知
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        # Bot以外は無視
        if not message.author.bot:
            return

        # チャンネル制限
        if message.channel.id != BUMP_CHANNEL_ID:
            return

        # Embedなしは無視
        if not message.embeds:
            return

        embed = message.embeds[0]

        # DISBOARD以外は無視
        if message.author.name != "DISBOARD":
            return

        # 本文がなければ無視
        if not embed.description:
            return

        # BUMP成功判定（日本語DISBOARD）
        if "表示順をアップしたよ" not in embed.description:
            return

        # 実行者が不明なら終了
        if not self.last_bump_user_id:
            return

        user = message.guild.get_member(self.last_bump_user_id)
        if not user:
            return

        # ===== DB処理（bot.pyのプールを使う）=====
        async with self.bot.profile_db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bump_amount (user_id, amount)
                VALUES ($1, 1)
                ON CONFLICT (user_id)
                DO UPDATE SET amount = bump_amount.amount + 1
                """,
                user.id
            )

            amount = await conn.fetchval(
                "SELECT amount FROM bump_amount WHERE user_id = $1",
                user.id
            )

            rank = await conn.fetchval(
                """
                SELECT COUNT(*) + 1
                FROM bump_amount
                WHERE amount > $1
                """,
                amount
            )

        # ===== 結果Embed =====
        result_embed = discord.Embed(
            title=f"{user.display_name}さん！BUMP TY✌️",
            description=(
                f"**{amount}回目のBUMPです！**\n"
                f"現在のランキング **{rank}位**"
            ),
            color=discord.Color.gold()
        )
        result_embed.set_thumbnail(
            url=user.display_avatar.replace(size=1024).url
        )

        await message.channel.send(embed=result_embed)

        # ===== 2時間後リマインド =====
        self.bot.loop.create_task(
            self.send_bump_reminder(message.channel)
        )

        # キャッシュクリア（誤爆防止）
        self.last_bump_user_id = None

    # 2時間後通知
    async def send_bump_reminder(self, channel: discord.TextChannel):
        await asyncio.sleep(60 * 60 * 2)

        reminder_embed = discord.Embed(
            title="⏰ BUMPの時間だよ",
            description="そろそろ `/bump` が使えます。",
            color=discord.Color.green()
        )

        await channel.send(embed=reminder_embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(BumpCount(bot))
