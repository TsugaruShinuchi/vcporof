import discord
from discord.ext import commands
import os
from utils.db import DB

class PartyRecruitmentModal(discord.ui.Modal, title="パーティー募集内容を入力！"):
    date = discord.ui.TextInput(
        label="日時（例：21時から～、今からなど）",
        required=True,
        max_length=100,
        style=discord.TextStyle.short,
        placeholder="例：21時から～、今から など"
    )
    content = discord.ui.TextInput(
        label="募集内容（例：寝落ち、雑談など）",
        required=True,
        max_length=100,
        style=discord.TextStyle.short,
        placeholder="例：雑談、新規開拓、寝落ち など"
    )
    appeal = discord.ui.TextInput(
        label="抱負（例：かかってこいよなど）",
        required=True,
        max_length=1024,
        style=discord.TextStyle.paragraph,
        placeholder="例：今夜は徹夜覚悟！どんな相手でも楽しめる自信があります！"
    )

    async def on_submit(self, interaction: discord.Interaction):
        profile_link = await DB.get_profile_message_link(str(interaction.user.id))

        embed = discord.Embed(
            title="🔍 募集内容の確認",
            color=discord.Color.red()
        )
        embed.set_author(name=f"募集主：{interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="【日時】", value=self.date.value, inline=False)
        embed.add_field(name="【内容】", value=self.content.value, inline=False)
        embed.add_field(name="【抱負】", value=self.appeal.value, inline=False)
        embed.add_field(name="▷プロフィールはこちら", value=profile_link or "プロフィールが見つかりませんでした。", inline=False)

        view = ConfirmRecruitmentView(self.date.value, self.content.value, self.appeal.value)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ConfirmRecruitmentView(discord.ui.View):
    def __init__(self, date, content, appeal):
        super().__init__(timeout=300)
        self.date = date
        self.content = content
        self.appeal = appeal
        self.add_item(RewriteButton())
        self.add_item(ConfirmButton(date, content, appeal))

class RewriteButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="◁書き直す", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PartyRecruitmentModal())

class ConfirmButton(discord.ui.Button):
    def __init__(self, date, content, appeal):
        super().__init__(label="▷確定！", style=discord.ButtonStyle.success)
        self.date = date
        self.content = content
        self.appeal = appeal

    async def callback(self, interaction: discord.Interaction):
        from cogs.handlers import post_final_recruitment  # 遅延インポート
        await post_final_recruitment(interaction, self.date, self.content, self.appeal)

async def setup(bot: commands.Bot):
    pass  # モーダル用なので setup は空にしておきます
