import asyncio
import os
import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from discord import app_commands
from dotenv import load_dotenv
from discord import app_commands

load_dotenv()

ENCOUNT_LOG_TC_ID = int(os.getenv("ENCOUNT_LOG_TC_ID"))
ENCOUNT_RECRUITMENT_TC_ID = int(os.getenv("ENCOUNT_RECRUITMENT_TC_ID"))
WAITING_HERO_ROLE_ID = int(os.getenv("WAITING_HERO_ROLE_ID"))
WAITING_PRINCESS_ROLE_ID = int(os.getenv("WAITING_PRINCESS_ROLE_ID"))
ENCOUNT_CATEGORY_ID = int(os.getenv("ENCOUNT_CATEGORY_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))  # ギルドコマンド登録用

class RescueSession:
    """VC と募集情報を管理する構造体"""
    def __init__(self, owner: discord.Member, vc: discord.VoiceChannel, created_at: float):
        self.owner = owner
        self.vc = vc
        self.created_at = created_at
        self.joined = False
        self.recruit_view: View | None = None
        self.recruit_msg: discord.Message | None = None

class RescueRequestView(View):
    """①『救助要請』ボタン永続ビュー"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🚨 救助要請", style=discord.ButtonStyle.danger, custom_id="rescue_request")
    async def rescue_request(self, interaction: discord.Interaction, button: Button):
        try:
            print("✅ ボタンクリックイベント受信！")

            member = interaction.user
            guild = interaction.guild
            print(f"🟡 guild/user 取得OK → user={member.display_name}, guild={guild.name}")

            await interaction.response.send_message("VCを生成します！", ephemeral=True)
            print("🟡 メッセージ送信OK")

            category = guild.get_channel(ENCOUNT_CATEGORY_ID)
            if not category or not isinstance(category, discord.CategoryChannel):
                raise ValueError(f"カテゴリーID {ENCOUNT_CATEGORY_ID} が見つかりません！")

            vc = await guild.create_voice_channel(
                name=f"救助：{member.display_name}",
                category=category,
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    member: discord.PermissionOverwrite(
                        view_channel=True,
                        connect=True,
                        speak=True,
                        use_voice_activation=True,
                        send_messages=True,
                        attach_files=True,
                        read_message_history=True
                    ),
                    guild.me: discord.PermissionOverwrite(view_channel=True, connect=True)
                },
                reason="救助要請による仮VC生成"
            )
            print(f"✅ VC生成成功！ → {vc.name}")

        except Exception as e:
            import traceback
            print("❌ rescue_request 内で例外発生！")
            traceback.print_exc()
            try:
                await interaction.followup.send(f"❌ エラー発生: {type(e).__name__}: {e}", ephemeral=True)
            except:
                pass

        # 成功後のフォローアップ
        await interaction.followup.send("✅ VCを生成しました。5分以内に入室してください。", ephemeral=True)

        # ログ送信など以降の処理...
        log_ch = guild.get_channel(ENCOUNT_LOG_TC_ID)
        try:
            embed = discord.Embed(color=discord.Color.green(), description=f"{member.mention} がVCを生成しました。")
            await log_ch.send(embed=embed)
        except Exception as e:
            print("❌ ログ送信でエラー:", type(e).__name__, e)

        sess = RescueSession(owner=member, vc=vc, created_at=asyncio.get_event_loop().time())
        self.bot.active_sessions.setdefault(guild.id, []).append(sess)
        self.bot.loop.create_task(self._wait_for_join(sess, guild.id))

    async def _wait_for_join(self, sess: RescueSession, guild_id: int):
        await asyncio.sleep(5 * 60)
        if not sess.joined:
            try:
                await sess.vc.delete(reason="入室なしのため削除")
            except:
                pass
            guild = self.bot.get_guild(guild_id)
            log_ch = guild.get_channel(ENCOUNT_LOG_TC_ID)
            embed = discord.Embed(color=discord.Color.red(), description=f"{sess.owner.mention} がVCに入室しませんでした。")
            await log_ch.send(embed=embed)
            self.bot.active_sessions[guild_id].remove(sess)

class RecruitView(View):
    """④ 募集通知『立候補』ボタン"""
    def __init__(self, bot, session: RescueSession):
        super().__init__(timeout=3600)
        self.bot = bot
        self.session = session

    @discord.ui.button(label="🙋‍♀️ 立候補", style=discord.ButtonStyle.success, custom_id="rescue_apply")
    async def apply_button(self, interaction: discord.Interaction, button: Button):
        applicant = interaction.user
        vc = self.session.vc
        owner = self.session.owner
        guild = interaction.guild

        print(f"✅ 立候補ボタン押下 → applicant={applicant.display_name}, owner={owner.display_name}, vc={vc.name}")

        # --- 🔹 応答（ユーザーに通知）
        await interaction.response.send_message(
            f"🙋‍♀️ 立候補しました！",
            ephemeral=True
        )

        # --- 🔹 VCチャットに許可ボタン付きメッセージ送信 ---
        try:
            view = PermitView(self.bot, self.session, applicant)
            msg = await vc.send(
                f"🚨 **救助要請VC**\n"
                f"{owner.mention} さん！ {applicant.mention} さんが立候補しました！\n"
                f"5分以内に許可してください👇",
                view=view
            )
            print(f"💬 PermitView送信成功 → msg.id={msg.id}, vc={vc.name}")
            self.session.recruit_msg = msg
            self.session.recruit_view_message = interaction.message  # 自身のメッセージを保存

        except Exception as e:
            print(f"❌ VCチャット送信失敗: {type(e).__name__}: {e}")
            await interaction.followup.send(f"❌ VCチャット送信失敗: {e}", ephemeral=True)

        # --- 🔹 ログ送信 ---
        log_ch = guild.get_channel(ENCOUNT_LOG_TC_ID)
        embed = discord.Embed(
            color=discord.Color.yellow(),
            description=f"{applicant.mention} が {owner.mention} に立候補しました。"
        )
        await log_ch.send(embed=embed)
        print("🪵 ログ送信完了")

class PermitView(View):
    """⑤ 『許可』ボタン"""
    def __init__(self, bot, session: RescueSession, applicant: discord.Member):
        super().__init__(timeout=300)
        self.bot = bot
        self.session = session
        self.applicant = applicant
        print(f"🧩 PermitView生成: applicant={applicant.display_name}, vc={session.vc.name}")

    @discord.ui.button(
        label="✅ 許可",
        style=discord.ButtonStyle.primary,
        custom_id="permit_button_dynamic"
    )
    async def permit_button(self, interaction: discord.Interaction, button: Button):
        vc = self.session.vc
        guild = interaction.guild
        owner = self.session.owner

        print(f"🟢 Permitボタン押下検知: applicant={self.applicant.display_name}, vc={vc.name}")

        # --- 🔹 VC権限付与 ---
        await vc.set_permissions(
            self.applicant,
            view_channel=True,
            connect=True,
            speak=True,
            use_voice_activation=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True
        )
        print("✅ VC権限追加成功！")

        # --- 🔹 VC URLを生成 ---
        vc_url = f"https://ptb.discord.com/channels/{guild.id}/{vc.id}"
        print(f"🔗 VC URL: {vc_url}")

        # --- 🔹 DM通知 ---
        try:
            await self.applicant.send(
                f"✅ 運命の扉が開かれました！🚪\n"
                f"🎧 VCに入室してください：\n{vc_url}"
            )
            dm_status = "📨 DM送信完了"
            print("📩 DM送信成功！")
        except discord.Forbidden:
            dm_status = "⚠️ ユーザーがDMを拒否しています。"
            print("⚠️ DM拒否設定のため送信不可。")
        except Exception as e:
            dm_status = f"⚠️ DM送信中にエラー: {e}"
            print(f"❌ DM送信エラー: {type(e).__name__}: {e}")

        # --- 🔹 公開通知 ---
        try:
            await interaction.response.send_message(
                f"{self.applicant.mention} に救出を許可しました。{dm_status}",
                ephemeral=True
            )
        except discord.InteractionResponded:
            await interaction.followup.send(
                f"{self.applicant.mention} に救出を許可しました。{dm_status}",
                ephemeral=True
            )
        print("✅ 許可メッセージ送信完了")

        # --- 🔹 許可ボタン削除 ---
        try:
            await interaction.message.edit(view=None)
            print("🗑️ 許可ボタン（自分のメッセージ）削除完了")
        except Exception as e:
            print(f"⚠️ 許可ボタン削除失敗: {e}")

        # --- 🔹 募集通知（立候補ボタン）削除 ---
        try:
            if hasattr(self.session, "recruit_view_message"):
                await self.session.recruit_view_message.edit(view=None)
                print("🗑️ 募集通知の立候補ボタン削除完了")
        except Exception as e:
            print(f"⚠️ 募集通知ボタン削除失敗: {e}")

        # --- 🔹 ログ送信 ---
        log_ch = guild.get_channel(ENCOUNT_LOG_TC_ID)
        embed = discord.Embed(
            color=discord.Color.yellow(),
            description=(
                f"{owner.mention} が {self.applicant.mention} とマッチングしました。\n"
            )
        )
        await log_ch.send(embed=embed)
        print("🪵 ログ送信完了")

class EncountCog(commands.Cog):
    """NEW ENCOUNT COG"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.active_sessions= {}  # dict[int, list[RescueSession]] 
        self.cleanup_empty_vcs.start()

    def cog_unload(self):
        self.cleanup_empty_vcs.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(RescueRequestView(self.bot))
        print("🟢 RescueRequestView 永続ビューを登録しました。")

    # ==========================
    # 🆕 /エンカウント コマンド
    # ==========================
    @app_commands.command(name="エンカウント", description="救助要請ボタンを設置します（管理者専用）")
    @app_commands.checks.has_permissions(administrator=True)
    async def encount(self, interaction: discord.Interaction):
        view = RescueRequestView(self.bot)
        await interaction.response.send_message(
            "🚨 **救助要請はこちらから！**",
            view=view,
            ephemeral=False
        )
        await interaction.followup.send("✅ 救助要請ボタンを設置しました。", ephemeral=True)

    @encount.error
    async def encount_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ このコマンドは管理者のみが実行できます。",
                ephemeral=True
            )
        else:
            raise error

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # ③ VC入室検知
        if before.channel is None and after.channel is not None:
            sessions = self.bot.active_sessions.get(member.guild.id, [])
            for sess in sessions:
                if sess.owner.id == member.id and after.channel.id == sess.vc.id:
                    sess.joined = True
                    await self.start_recruit(sess)
                    break

    async def start_recruit(self, sess: RescueSession):
        """④ 募集開始処理"""
        guild = sess.vc.guild
        recruit_ch = guild.get_channel(ENCOUNT_RECRUITMENT_TC_ID)
        owner = sess.owner

        # 募集先ロール判定
        has_princess = any(r.id == WAITING_PRINCESS_ROLE_ID for r in owner.roles)
        target_role_id = WAITING_HERO_ROLE_ID if has_princess else WAITING_PRINCESS_ROLE_ID

        view = RecruitView(self.bot, sess)
        sess.recruit_view = view
        msg = await recruit_ch.send(f"<@&{target_role_id}> 各位、立候補はこちら！", view=view)
        sess.recruit_msg = msg

        await owner.send("募集開始しました！")

        log_ch = guild.get_channel(ENCOUNT_LOG_TC_ID)
        embed = discord.Embed(color=discord.Color.blue(), description=f"{owner.mention} が募集開始。")
        await log_ch.send(embed=embed)

    @tasks.loop(seconds=60)
    async def cleanup_empty_vcs(self):
        """⑦ VCが空なら削除"""
        for guild_id, sessions in list(self.bot.active_sessions.items()):
            guild = self.bot.get_guild(guild_id)
            for sess in sessions.copy():
                if len(sess.vc.members) == 0:
                    try:
                        await sess.vc.delete(reason="VCが空になったため削除")
                    except:
                        pass
                    sessions.remove(sess)

    @cleanup_empty_vcs.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(EncountCog(bot))
    # ギルドスラッシュコマンド同期
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f"✅ /エンカウント コマンドをギルド({GUILD_ID})に同期しました。")
