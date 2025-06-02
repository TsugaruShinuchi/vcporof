import discord
from discord.ext import commands
import os
from utils.db import DB

# 環境変数
GUILD_ID = int(os.getenv("GUILD_ID"))
HERO_ROLE_ID = int(os.getenv("ROLE_HERO_ID"))
PRINCESS_ROLE_ID = int(os.getenv("ROLE_PRINCESS_ID"))
HERO_TARGET_ROLE_ID = int(os.getenv("ROLE_HERO_TARGET_ID"))
PRINCESS_TARGET_ROLE_ID = int(os.getenv("ROLE_PRINCESS_TARGET_ID"))

CHANNEL_HERO_ID = int(os.getenv("CHANNEL_HERO_RECRUITMENT_ID"))
CHANNEL_PRINCESS_ID = int(os.getenv("CHANNEL_PRINCESS_RECRUITMENT_ID"))
CHANNEL_LOG_ID = int(os.getenv("CHANNEL_LOG_ID"))

# モーダルを先に定義
class ApplyCommentModal(discord.ui.Modal, title="応募メッセージを送信"):
    comment = discord.ui.TextInput(
        label="応募メッセージ（相手に送られます）",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500,
        placeholder="よろしくお願いします！など"
    )

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        from cogs.handlers import handle_application_submission
        await handle_application_submission(interaction, self.author_id, self.comment.value)

class ApplyButton(discord.ui.Button):
    def __init__(self, author_id: int):
        super().__init__(label="✋応募", style=discord.ButtonStyle.success, custom_id=f"apply_{author_id}")
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplyCommentModal(author_id=self.author_id))

class ApplyView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.add_item(ApplyButton(author_id))

class DMDeleteButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🗑 募集を削除", style=discord.ButtonStyle.danger, custom_id="delete_recruitment")

    async def callback(self, interaction: discord.Interaction):
        data = await DB.get_recruitment_by_user_id(interaction.user.id)
        if not data:
            await interaction.response.send_message("削除情報が見つかりませんでした。", ephemeral=True)
            return

        guild = interaction.client.get_guild(GUILD_ID)
        channel = guild.get_channel(data["channel_id"])
        if not channel:
            await interaction.response.send_message("チャンネルが見つかりません。", ephemeral=True)
            return

        try:
            message = await channel.fetch_message(data["message_id"])
            await message.delete()
            await DB.delete_recruit_message(data["message_id"])
        except:
            await interaction.response.send_message("メッセージの削除に失敗しました。", ephemeral=True)
            return

        self.disabled = True
        self.label = "✅ 削除済み"
        view = discord.ui.View()
        view.add_item(self)
        await interaction.response.edit_message(view=view)

async def post_final_recruitment(interaction: discord.Interaction, date: str, content: str, appeal: str):
    guild = interaction.client.get_guild(GUILD_ID)
    if not guild:
        await interaction.response.send_message("ギルドが見つかりません。", ephemeral=True)
        return

    try:
        member = await guild.fetch_member(interaction.user.id)
    except:
        await interaction.response.send_message("メンバー情報の取得に失敗しました。", ephemeral=True)
        return

    is_hero = discord.utils.get(member.roles, id=HERO_ROLE_ID) is not None
    is_princess = discord.utils.get(member.roles, id=PRINCESS_ROLE_ID) is not None

    if not is_hero and not is_princess:
        await interaction.response.send_message("ロールが設定されていません（勇者またはお姫様）。", ephemeral=True)
        return

    profile_link = await DB.get_profile_message_link(member)

    embed = discord.Embed(
        title="🤝 バディ募集",
        color=discord.Color.blue() if is_hero else discord.Color.red()
    )
    embed.set_author(name=f"募集主：{member.display_name}", icon_url=member.display_avatar.url)
    embed.add_field(name="【日時】", value=date, inline=False)
    embed.add_field(name="【内容】", value=content, inline=False)
    embed.add_field(name="【抱負】", value=appeal, inline=False)
    embed.add_field(
        name="\u200b",
        value=f"[プロフィールを見る]({profile_link})" if profile_link else "プロフィールが見つかりませんでした。",
        inline=False
    )

    mention_role_id = HERO_TARGET_ROLE_ID if is_hero else PRINCESS_TARGET_ROLE_ID
    channel_id = CHANNEL_HERO_ID if is_hero else CHANNEL_PRINCESS_ID

    recruitment_channel = guild.get_channel(channel_id)
    if recruitment_channel is None:
        await interaction.response.send_message("募集チャンネルが見つかりません。", ephemeral=True)
        return

    view = ApplyView(member.id)
    msg = await recruitment_channel.send(content=f"<@&{mention_role_id}>", embed=embed, view=view)

    # DBに保存
    await DB.save_recruitment(user_id=member.id, message_id=msg.id, channel_id=recruitment_channel.id)


    # DMに削除ボタン付きで送信
    try:
        dm_view = discord.ui.View()
        dm_view.add_item(DMDeleteButton(msg.id, recruitment_channel.id))
        await member.send(embed=embed, view=dm_view)
    except Exception as e:
        print(f"DM送信失敗: {e}")
    
    await interaction.response.send_message("募集を投稿しました！", ephemeral=True)

async def setup(bot: commands.Bot):
    pass

async def handle_application_submission(interaction: discord.Interaction, author_id: int, comment: str):
    author = await interaction.guild.fetch_member(author_id)
    profile_link = await DB.get_profile_message_link(interaction.user)

    is_hero = discord.utils.get(interaction.user.roles, id=HERO_ROLE_ID) is not None
    embed_color = discord.Color.blue() if is_hero else discord.Color.red()

    embed_to_author = discord.Embed(
        title="📝 バディ応募",
        description=f"{interaction.user.mention} からバディの応募がありました✨\nDMでお返事してあげてください！",
        color=embed_color
    )
    embed_to_author.add_field(
        name="\u200b",
        value=f"[プロフィールを見る]({profile_link})" if profile_link else "プロフィールが見つかりませんでした。",
        inline=False
    )
    embed_to_author.add_field(name="🗨 応募メッセージ", value=comment, inline=False)
    embed_to_author.set_thumbnail(url=interaction.user.display_avatar.url)

    try:
        await author.send(embed=embed_to_author)
    except:
        await interaction.response.send_message("募集主にDMを送れませんでした。", ephemeral=True)
        return

    embed_to_applicant = discord.Embed(
        description=(
            f"{author.display_name} さんの募集に応募しました！\n"
            "採用された場合DMが来ます。\n"
            "しばらく、お待ちください✨\n\n"
            "⚠応募者からDMを送るのは禁止です。⚠"
        ),
        color=discord.Color.orange()
    )
    embed_to_applicant.add_field(name="🗨 あなたのメッセージ", value=comment, inline=False)
    embed_to_applicant.set_thumbnail(url=author.display_avatar.url)

    try:
        await interaction.user.send(embed=embed_to_applicant)
    except:
        await interaction.followup.send("あなたへのDMが送信できませんでした。", ephemeral=True)

    log_channel = interaction.guild.get_channel(CHANNEL_LOG_ID)
    if log_channel:
        await log_channel.send(f"{author.mention} の募集に {interaction.user.mention} が応募しました！\n🗨 コメント: {comment}")

    await interaction.response.send_message("応募を送信しました！DMも確認してね！", ephemeral=True)
