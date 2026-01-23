import os
import discord
from discord.ext import tasks, commands
from discord import app_commands
from dotenv import load_dotenv
import asyncpg

load_dotenv()

class VCCounter(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_vc_names.start()

    def cog_unload(self):
        self.update_vc_names.cancel()

    async def _update(self, guild: discord.Guild):
        # チャンネル取得（Noneガード）
        matching_ch = guild.get_channel(1464186246535315564)
        if matching_ch is None:
            print("⚠️ matching channel not found")
            return

        # DB（Pool想定で acquire。Connectionならそのままでも動くように分岐）
        db = self.bot.db
        try:
            if isinstance(db, asyncpg.Pool):
                async with db.acquire() as conn:
                    matching_total = await conn.fetchval("SELECT COUNT(*) FROM matching_choose")
                    matching_kotsu = await conn.fetchval('SELECT COUNT(*) FROM matching_choose WHERE "check" = 1')
            else:
                conn: asyncpg.Connection = db
                matching_total = await conn.fetchval("SELECT COUNT(*) FROM matching_choose")
                matching_kotsu = await conn.fetchval('SELECT COUNT(*) FROM matching_choose WHERE "check" = 1')
        except Exception as e:
            print(f"❌ DB error: {e}")
            return

        new_name = f"👩‍❤️‍💋‍👨マッチ：{matching_total}回｜個通数：{matching_kotsu}"

        # 変更があるときだけ編集（レート制限＆無駄API削減）
        try:
            if matching_ch.name != new_name:
                await matching_ch.edit(name=new_name)
            print(f"✅ {guild.name} のVC名を更新しました。")
        except discord.Forbidden:
            print("❌ 権限不足でチャンネル名を変更できません")
        except discord.HTTPException as e:
            print(f"❌ Discord API error: {e}")

    @tasks.loop(hours=1)
    async def update_vc_names(self):
        # 1ギルド運用なら、ここは最初の1個だけ取ればOK
        if not self.bot.guilds:
            return
        await self._update(self.bot.guilds[0])

    @update_vc_names.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    @app_commands.guilds(discord.Object(id=int(os.getenv("GUILD_ID"))))
    @app_commands.command(name="人数更新", description="人数を手動更新します（管理者限定）")
    @app_commands.checks.has_permissions(administrator=True)
    async def update_vc_command(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self._update(interaction.guild)
        await interaction.followup.send("✅ VCの名前を更新しました。")

    @update_vc_command.error
    async def update_vc_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.followup.send("❌ このコマンドは管理者のみ使用できます。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(VCCounter(bot))

