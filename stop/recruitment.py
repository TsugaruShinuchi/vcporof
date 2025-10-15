import discord
from discord import app_commands
from discord.ext import commands
import os

ADMIN_ROLE_ID = int(os.getenv("ROLE_ADMIN_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))

class RecruitmentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RecruitmentButton())

class RecruitmentButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔔募集", style=discord.ButtonStyle.primary, custom_id="recruitment_open")

    async def callback(self, interaction: discord.Interaction):
        from cogs.modals import PartyRecruitmentModal
        await interaction.response.send_modal(PartyRecruitmentModal())

class Recruitment(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.command(name="バディ募集", description="募集用のEmbedを送信（管理者のみ）")
    @app_commands.default_permissions(administrator=True)
    async def recruit(self, interaction: discord.Interaction):
        # 管理者チェック
        admin_role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
        if admin_role not in interaction.user.roles:
            await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
            return
        embed = discord.Embed(
            title="📢 バディ募集掲示板",
            description="募集をかけて、個通相手を探しましょう！\n【🔔募集】を押すと、募集がかけられます！\n\n✉ DMを使うから、受け取れる設定にしてね✨",
            color=discord.Color.orange()
        )

        view = RecruitmentView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("募集メッセージを送信しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Recruitment(bot))
