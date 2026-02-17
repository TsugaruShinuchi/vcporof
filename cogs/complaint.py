# cogs/complaint.py
import os
import discord
from discord.ext import commands
from discord import app_commands

# =========================
# 設定（envから読む）
# =========================
COMPLAINT_FORM_CHANNEL_ID = 1473181878214463528


# =========================
# Embed helpers
# =========================
def build_form_embed() -> discord.Embed:
    return discord.Embed(
        title="苦情フォーム",
        description=(
            "相手を指定して苦情を送れます。\n"
            "送った内容はDMで確認できます。\n"
            "原則は連絡しませんが、\n"
            "苦情内容についてDMで質問がくる\n"
            "場合もあります。"
        ),
        color=discord.Color.dark_red(),
    )


def build_complaint_embed(
    target: discord.abc.User,
    reporter: discord.abc.User,
    complaint_text: str,
) -> discord.Embed:
    e = discord.Embed(
        title=f"{target.display_name}さんへの苦情",
        description=complaint_text,
        color=discord.Color.red(),
    )
    e.add_field(name="対象", value=f"{target.mention}（`{target.id}`）", inline=False)
    e.add_field(name="投稿者", value=f"{reporter.mention}（`{reporter.id}`）", inline=False)
    e.set_author(
        name=f"{reporter.display_name}（{reporter.id}）",
        icon_url=reporter.display_avatar.url,
    )
    e.set_thumbnail(url=target.display_avatar.url)
    return e


def build_dm_receipt_embed(
    target: discord.abc.User,
    complaint_text: str,
) -> discord.Embed:
    e = discord.Embed(
        title="送信内容の控え",
        description=complaint_text,
        color=discord.Color.blurple(),
    )
    e.add_field(
        name="対象アカウント",
        value=f"{target.mention}\n`{target.display_name}`\n`{target.id}`",
        inline=False,
    )
    e.set_thumbnail(url=target.display_avatar.url)
    return e


# =========================
# Modal（② 苦情内容）
# =========================
class ComplaintModal(discord.ui.Modal):
    # Discord側でモーダル入力時間は上限がある。timeout=Noneでも無限にはならない。人類の限界。
    def __init__(self, bot: commands.Bot, target: discord.abc.User):
        super().__init__(title="苦情内容の入力", timeout=None)
        self.bot = bot
        self.target = target

        self.body = discord.ui.TextInput(
            label="苦情内容",
            style=discord.TextStyle.long,
            required=True,
            max_length=2000,
            placeholder="具体的に、何が、いつ、どう問題だったか（事実ベース推奨）",
        )
        self.add_item(self.body)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("ギルド内で実行してください。", ephemeral=True)
            return

        if COMPLAINT_FORM_CHANNEL_ID == 0:
            await interaction.followup.send("COMPLAINT_FORM_CHANNEL が未設定です。", ephemeral=True)
            return

        reporter = interaction.user
        target = self.target
        complaint_text = self.body.value.strip()

        # ===== DB: thread_id 取得 =====
        pool = getattr(self.bot, "db", None)
        if pool is None:
            await interaction.followup.send("DBプールが見つかりません（bot.db が未設定）。", ephemeral=True)
            return

        thread_id = await pool.fetchval(
            "SELECT thread_id FROM complaint WHERE user_id = $1",
            target.id,
        )

        # ===== 集約チャンネル取得 =====
        parent = guild.get_channel(COMPLAINT_FORM_CHANNEL_ID)
        if parent is None:
            await interaction.followup.send("COMPLAINT_FORM_CHANNEL が見つかりません。ID確認して。", ephemeral=True)
            return

        # ===== スレッド取得 =====
        thread = None
        if thread_id:
            thread = guild.get_thread(int(thread_id))
            if thread is None:
                try:
                    thread = await guild.fetch_channel(int(thread_id))  # type: ignore
                except (discord.NotFound, discord.Forbidden):
                    thread = None

        # ===== ない場合：作成してDBへ登録 =====
        if thread is None:
            thread_name = f"{target.mention}（{target.display_name}）さん苦情フォーム"

            if isinstance(parent, discord.ForumChannel):
                created = await parent.create_thread(
                    name=thread_name,
                    content="苦情一覧",
                    reason="create complaint thread",
                )
                thread = created.thread

            elif isinstance(parent, discord.TextChannel):
                starter = await parent.send("苦情一覧")
                thread = await starter.create_thread(
                    name=thread_name,
                    reason="create complaint thread",
                )
            else:
                await interaction.followup.send(
                    "COMPLAINT_FORM_CHANNEL は Forum か Text チャンネルにしてください。",
                    ephemeral=True
                )
                return

            # DB upsert
            await pool.execute(
                """
                INSERT INTO complaint (user_id, thread_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id)
                DO UPDATE SET thread_id = EXCLUDED.thread_id
                """,
                target.id,
                thread.id,
            )

        # ===== スレッドへ苦情投稿 =====
        embed = build_complaint_embed(target=target, reporter=reporter, complaint_text=complaint_text)
        try:
            await thread.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("スレッドへ投稿する権限がありません。Bot権限を確認して。", ephemeral=True)
            return

        # ===== ④ DMで控え送付 =====
        dm_embed = build_dm_receipt_embed(target=target, complaint_text=complaint_text)
        try:
            await reporter.send(embed=dm_embed)
        except discord.Forbidden:
            # DM拒否はよくある。世界は冷たい。
            pass

        await interaction.followup.send("送信しました。DMに控えを送りました（DM拒否だと届きません）。", ephemeral=True)


# =========================
# View（① User Select）
# =========================
class TargetSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, requester_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.requester_id = requester_id

        self.user_select = discord.ui.UserSelect(
            placeholder="苦情の対象ユーザーを選択",
            min_values=1,
            max_values=1,
        )
        self.user_select.callback = self.on_select  # type: ignore
        self.add_item(self.user_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.requester_id

    async def on_select(self, interaction: discord.Interaction) -> None:
        target = self.user_select.values[0]

        if target.id == interaction.user.id:
            await interaction.response.send_message("自分を対象にはできません。", ephemeral=True)
            return

        await interaction.response.send_modal(ComplaintModal(bot=self.bot, target=target))


# =========================
# 永続View（ボタン: custom_id=complaint_button）
# =========================
class ComplaintEntryView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="🖕 物申す",
        style=discord.ButtonStyle.danger,
        custom_id="complaint_button",
    )
    async def complaint_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = TargetSelectView(bot=self.bot, requester_id=interaction.user.id)
        await interaction.response.send_message("対象ユーザーを選んでください。", view=view, ephemeral=True)


# =========================
# Cog本体
# =========================
class ComplaintCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # 永続ビュー登録（再起動してもcustom_idで復活）
        self.bot.add_view(ComplaintEntryView(bot=self.bot))

    async def cog_load(self) -> None:
        # テーブル作成
        pool = getattr(self.bot, "db", None)
        if pool is None:
            return

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS complaint (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL UNIQUE,
                thread_id BIGINT NOT NULL UNIQUE
            );
            """
        )

    @app_commands.command(name="名指し苦情フォーム", description="苦情フォーム（ボタン）を投稿します")
    @app_commands.default_permissions(administrator=True)
    async def complaint_form(self, interaction: discord.Interaction) -> None:
        embed = build_form_embed()
        view = ComplaintEntryView(bot=self.bot)  # 送信時にも付ける
        
        await interaction.response.send_message("設置完了。", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(ComplaintCog(bot))
