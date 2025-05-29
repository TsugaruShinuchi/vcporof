import discord
from discord.ext import commands
import os
from utils.db import DB

# 環境変数
HERO_ROLE_ID = int(os.getenv("ROLE_HERO_ID"))
PRINCESS_ROLE_ID = int(os.getenv("ROLE_PRINCESS_ID"))
HERO_TARGET_ROLE_ID = int(os.getenv("ROLE_HERO_TARGET_ID"))
PRINCESS_TARGET_ROLE_ID = int(os.getenv("ROLE_PRINCESS_TARGET_ID"))

CHANNEL_HERO_ID = int(os.getenv("CHANNEL_HERO_RECRUITMENT_ID"))
CHANNEL_PRINCESS_ID = int(os.getenv("CHANNEL_PRINCESS_RECRUITMENT_ID"))
CHANNEL_LOG_ID = int(os.getenv("CHANNEL_LOG_ID"))

class ApplyButton(discord.ui.Button):
    def __init__(self, author_id: int):
        super().__init__(label="✋応募", style=discord.ButtonStyle.success, custom_id=f"apply_{author_id}")
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction):
        profile_link = await DB.get_profile_message_link(str(interaction.user.id))

        is_hero = discord.utils.get(interaction.user.roles, id=HERO_ROLE_ID) is not None
        embed_color = discord.Color.blue() if is_hero else discord.Color.red()

        embed = discord.Embed(
            title="📝 パーティー応募",
            description=f"{interaction.user.mention} からパーティーへの応募がありました！",
            color=embed_color
        )
        embed.add_field(name="▷プロフィールはこちら", value=profile_link or "プロフィールが見つかりませんでした。", inline=False)

        try:
            author = await interaction.guild.fetch_member(self.author_id)
            await author.send(embed=embed)
        except:
            await interaction.response.send_message("DMを送信できませんでした。", ephemeral=True)
            return

        log_channel = interaction.guild.get_channel(CHANNEL_LOG_ID)
        if log_channel:
            await log_channel.send(f"{author.mention} の募集に {interaction.user.mention} が応募しました！")

        await interaction.response.send_message("応募を送信しました！", ephemeral=True)

class ApplyView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.add_item(ApplyButton(author_id))

async def post_final_recruitment(interaction: discord.Interaction, date: str, content: str, appeal: str):
    member = interaction.user

    is_hero = discord.utils.get(member.roles, id=HERO_ROLE_ID) is not None
    is_princess = discord.utils.get(member.roles, id=PRINCESS_ROLE_ID) is not None

    if not is_hero and not is_princess:
        await interaction.response.send_message("ロールが設定されていません（勇者またはお姫様）。", ephemeral=True)
        return

    profile_link = await DB.get_profile_message_link(str(member.id))

    embed = discord.Embed(
        title="🎯 パーティー募集",
        color=discord.Color.blue() if is_hero else discord.Color.red()
    )
    embed.set_author(name=f"募集主：{member.display_name}", icon_url=member.display_avatar.url)
    embed.add_field(name="【日時】", value=date, inline=False)
    embed.add_field(name="【内容】", value=content, inline=False)
    embed.add_field(name="【抱負】", value=appeal, inline=False)
    embed.add_field(name="▷プロフィールはこちら", value=profile_link or "プロフィールが見つかりませんでした。", inline=False)

    # メンションと投稿先
    mention_role_id = HERO_TARGET_ROLE_ID if is_hero else PRINCESS_TARGET_ROLE_ID
    channel_id = CHANNEL_HERO_ID if is_hero else CHANNEL_PRINCESS_ID

    recruitment_channel = interaction.guild.get_channel(channel_id)
    if recruitment_channel is None:
        await interaction.response.send_message("募集チャンネルが見つかりません。", ephemeral=True)
        return

    view = ApplyView(member.id)
    message = await recruitment_channel.send(content=f"<@&{mention_role_id}>", embed=embed, view=view)

    # 応募者にDM送信
    try:
        await member.send(embed=embed)
    except:
        pass

    await interaction.response.send_message("募集を投稿しました！", ephemeral=True)

async def setup(bot: commands.Bot):
    pass  # ViewはRecruitment時点で永続Viewとして登録されるのでここでは不要
