import discord
from discord.ext import commands
import os
from utils.db import DB

HERO_ROLE_ID = int(os.getenv("ROLE_HERO_ID"))
PRINCESS_ROLE_ID = int(os.getenv("ROLE_PRINCESS_ID"))
HERO_TARGET_ROLE_ID = int(os.getenv("ROLE_HERO_TARGET_ID"))
PRINCESS_TARGET_ROLE_ID = int(os.getenv("ROLE_PRINCESS_TARGET_ID"))
CHANNEL_HERO_ID = int(os.getenv("CHANNEL_HERO_RECRUITMENT_ID"))
CHANNEL_PRINCESS_ID = int(os.getenv("CHANNEL_PRINCESS_RECRUITMENT_ID"))

class PartyRecruitmentModal(discord.ui.Modal, title="バディ募集内容を入力！"):
    date = discord.ui.TextInput(label="日時", required=True, max_length=100)
    content = discord.ui.TextInput(label="募集内容", required=True, max_length=100)
    appeal = discord.ui.TextInput(label="抱負", required=True, max_length=1024, style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # インタラクション応答を保留

        profile_link = await DB.get_profile_message_link(interaction.user)
        embed = discord.Embed(
            title="🔍 募集内容の確認",
            color=discord.Color.red()
        )
        embed.set_author(name=f"募集主：{interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="【日時】", value=self.date.value, inline=False)
        embed.add_field(name="【内容】", value=self.content.value, inline=False)
        embed.add_field(name="【抱負】", value=self.appeal.value, inline=False)
        embed.add_field(
            name="\u200b",
            value=f"[プロフィールを見る]({profile_link})" if profile_link else "プロフィールが見つかりませんでした。",
            inline=False
        )

        view = ConfirmRecruitmentView(self.date.value, self.content.value, self.appeal.value)
        try:
            await interaction.user.send(embed=embed, view=view)
            await interaction.followup.send("DMに確認メッセージを送信しました！", ephemeral=True)
        except:
            await interaction.followup.send("DMを送信できませんでした。設定を確認してください。", ephemeral=True)

class ConfirmRecruitmentView(discord.ui.View):
    def __init__(self, date, content, appeal):
        super().__init__(timeout=None)
        self.date = date
        self.content = content
        self.appeal = appeal
        self.add_item(RewriteButton(self))
        self.add_item(ConfirmButton(date, content, appeal, self))

class RewriteButton(discord.ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="◁取り消し", style=discord.ButtonStyle.danger)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        for item in self.parent_view.children:
            item.disabled = True
        await interaction.message.edit(view=self.parent_view)
        await interaction.response.send_message("募集をキャンセルしました。", ephemeral=True)

class ConfirmButton(discord.ui.Button):
    def __init__(self, date, content, appeal, parent_view):
        super().__init__(label="▷確定！", style=discord.ButtonStyle.success)
        self.date = date
        self.content = content
        self.appeal = appeal
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        from cogs.handlers import post_final_recruitment
        for item in self.parent_view.children:
            item.disabled = True
        await interaction.message.edit(view=self.parent_view)
        await post_final_recruitment(interaction, self.date, self.content, self.appeal)

async def setup(bot: commands.Bot):
    pass
