import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncpg
from utils.db import DB


ADMIN_ROLE_ID = int(os.getenv("ROLE_ADMIN_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))

# --------------------------
# DB 接続ユーティリティ
# --------------------------
async def get_pool(bot):
    # bot.pool に接続済みなら再利用
    if not hasattr(bot, "pool"):
        bot.pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))
    return bot.pool


# --------------------------
# View本体
# --------------------------

class RecruitmentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RecruitmentButton())
        self.add_item(DeleteRecruitButton())  # ★ 削除ボタン追加


class RecruitmentButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔔募集", style=discord.ButtonStyle.primary, custom_id="recruitment_open")

    async def callback(self, interaction: discord.Interaction):
        from cogs.buddy_modals import PartyRecruitmentModal
        await interaction.response.send_modal(PartyRecruitmentModal())


# --------------------------
# ★追加：削除ボタン
# --------------------------
class DeleteRecruitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="🗑 募集削除",
            style=discord.ButtonStyle.danger,
            custom_id="recruitment_delete",
        )

    async def callback(self, interaction: discord.Interaction):
        # DB.pool が初期化されていない場合は初期化
        if DB.pool is None:
            await DB.init_pool()

        # user_id に紐づく message_id を DB から探す
        async with DB.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT message_id, channel_id FROM recruit_messages WHERE user_id = $1",
                interaction.user.id
            )

        if row is None:
            await interaction.response.send_message(
                "あなたの募集が見つかりませんでした。",
                ephemeral=True
            )
            return

        message_id = row["message_id"]
        channel_id = row["channel_id"]

        # メッセージ削除
        try:
            channel = interaction.guild.get_channel(channel_id)
            if channel is None:
                channel = await interaction.guild.fetch_channel(channel_id)

            message = await channel.fetch_message(message_id)
            await message.delete()
        except:
            await interaction.response.send_message(
                "メッセージの取得または削除に失敗しました。",
                ephemeral=True
            )
            return

        # DBからも削除
        await DB.delete_recruit_message(message_id)

        await interaction.response.send_message(
            "あなたの募集メッセージを削除しました。",
            ephemeral=True
        )


# --------------------------
# Cog
# --------------------------

class Recruitment(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(RecruitmentView())

    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.command(name="バディ募集", description="募集用のEmbedを送信（管理者のみ）")
    @app_commands.default_permissions(administrator=True)
    async def recruit(self, interaction: discord.Interaction):
        admin_role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
        if admin_role not in interaction.user.roles:
            await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
            return

        embed = discord.Embed(
            title="📢 バディ募集掲示板",
            description="募集をかけて、個通相手を探しましょう！\n【🔔募集】で募集！\n【🗑削除】であなたの募集を消せます。\n\n✉ DMを受け取れる設定にしてね✨",
            color=discord.Color.orange()
        )

        view = RecruitmentView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("募集メッセージを送信しました。", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Recruitment(bot))
