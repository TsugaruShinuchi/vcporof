import os
import discord
from discord import app_commands, Embed, Color
from discord.ext import commands
from utils.profile_repo import set_profile, set_color, get_profile
from utils.color import determine_color

GUILD_ID = int(os.getenv("GUILD_ID"))

class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.PROFILE_TC_IDS = [int(x) for x in os.getenv("PROFILE_TC_IDS", "").split(",") if x]
        self.IGNORE_VC_CHANNEL_IDS = [int(x) for x in os.getenv("IGNORE_VC_CHANNEL_IDS", "").split(",") if x]
        self.IGNORE_VC_CATEGORY_IDS = [int(x) for x in os.getenv("IGNORE_VC_CATEGORY_IDS", "").split(",") if x]
        self.embed_cache = {}
        print("🧪 ProfileCog インスタンス化された")

    @app_commands.command(name="プロフ登録", description="プロフィールチャンネル内の全ユーザーの投稿を登録します")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    async def register_all_profiles(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ あなたは管理者ではありません。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)  # ← ここで先に応答！

        updated = 0
        seen_users = set()

        for tc_id in self.PROFILE_TC_IDS:
            channel = interaction.guild.get_channel(tc_id)
            if not channel:
                continue
            async for msg in channel.history(limit=None, oldest_first=True):
                if msg.author.bot or msg.author.id in seen_users:
                    continue
                await set_profile(self.bot.profile_db_pool, msg.author.id, msg.id)
                seen_users.add(msg.author.id)
                updated += 1


        await interaction.followup.send(f"✅ {updated} 件のプロフィールを登録しました。", ephemeral=True)

    @app_commands.command(name="プロフカラー登録", description="プロフィールカラーを登録")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    async def register_color(self, interaction: discord.Interaction, user: discord.User, color: str):
        await set_color(self.bot.profile_db_pool, user.id, color)
        await interaction.response.send_message("✅ カラーを更新しました。", ephemeral=True)


    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        def ignored(ch):
            return ch and (ch.id in self.IGNORE_VC_CHANNEL_IDS or (ch.category and ch.category.id in self.IGNORE_VC_CATEGORY_IDS))

        if self.bot.profile_db_pool is None:
            print("❗ profile_db_pool is not initialized yet.")
            return
        # ミュートなどの状態変化のみは無視
        if before.channel == after.channel:
            return

        # print(f"🎧 VCチャンネル変化検出: {member} | before={before.channel} | after={after.channel}")

        # VC入室
        if not before.channel and after.channel:
            if ignored(after.channel):
                return

            key = (member.guild.id, member.id)
            if key in self.embed_cache:
                print(f"⚠️ 二重送信防止: {member}")
                return

            await self.send_profile_embed(member, after.channel)
            return


        # VC移動
        if before.channel and after.channel and before.channel != after.channel:
            if ignored(before.channel) and ignored(after.channel):
                return

            # 前VCのembed削除
            key = (member.guild.id, member.id)
            msg_id = self.embed_cache.pop(key, None)
            if msg_id and not ignored(before.channel):
                try:
                    msg = await before.channel.fetch_message(msg_id)
                    await msg.delete()
                    # print(f"🗑️ Embed削除: message_id={msg_id}")
                except Exception as e:
                    print(f"⚠️ Embed削除失敗: {e}")

            if ignored(after.channel):
                return
            await self.send_profile_embed(member, after.channel)
            return

        # VC退出
        if before.channel and not after.channel:
            if ignored(before.channel):
                return
            key = (member.guild.id, member.id)
            msg_id = self.embed_cache.pop(key, None)
            if msg_id:
                try:
                    msg = await before.channel.fetch_message(msg_id)
                    await msg.delete()
                    # print(f"🗑️ Embed削除: message_id={msg_id}")
                except Exception as e:
                    print(f"⚠️ Embed削除失敗: {e}")
            return

    async def send_profile_embed(self, member, channel):
        prof = await get_profile(self.bot.profile_db_pool, member.id)
        if not prof:
            return

        msg_id, col = prof["bio"], prof["color"]
        msg = None

        for tc_id in self.PROFILE_TC_IDS:
            ch = member.guild.get_channel(tc_id)
            if ch:
                try:
                    msg = await ch.fetch_message(msg_id)
                except Exception as e:
                    async for m in ch.history(limit=100):
                        if m.author.id == member.id and not m.author.bot:
                            await set_profile(self.bot.profile_db_pool, member.id, m.id)
                            msg = m
                            break
                    if not msg:
                        continue

                link = msg.jump_url
                embed = Embed(
                    description=f"{msg.content}\n\n[▷リアクションはこちら]({link})\n\n👤 <@{member.id}>",
                    color=determine_color(col, member)
                )
                embed.set_author(
                    name=member.display_name,
                    icon_url=member.display_avatar.url
                )
                try:
                    sent = await channel.send(embed=embed)
                    # print(f"✅ Embed送信完了: message_id={sent.id}")
                    self.embed_cache[(member.guild.id, member.id)] = sent.id
                except Exception as e:
                    print(f"❌ Embed送信失敗: {e}")
                return  # 一回送信したら抜ける


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
