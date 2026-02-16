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
        matching_ch = guild.get_channel(1464186246535315564)
        gacha_ch = guild.get_channel(1459246559324668057)
        # blackjack_ch = guild.get_channel(1466648900768239722)
        # chohan_ch = guild.get_channel(1467317822056304640)

        if matching_ch is None or gacha_ch is None:
            print("⚠️ channel not found")
            return

        db = self.bot.db
        try:
            if isinstance(db, asyncpg.Pool):
                async with db.acquire() as conn:
                    row = await conn.fetchrow("""
                        SELECT
                        (SELECT COUNT(*) FROM matching_choose) AS matching_total,
                        (SELECT COUNT(*) FROM matching_choose WHERE "check" = 1) AS matching_kotsu,
                        (SELECT COUNT(*) FROM gacha_log) AS gacha_total,
                    """)
                    #     (SELECT SUM(amount) FROM blackjack_record) AS blackjack_total,
                    #     (SELECT SUM(amount) FROM hancho_record) AS chohan_total
                    # """)
            else:
                conn: asyncpg.Connection = db
                row = await conn.fetchrow("""
                    SELECT
                    (SELECT COUNT(*) FROM matching_choose) AS matching_total,
                    (SELECT COUNT(*) FROM matching_choose WHERE "check" = 1) AS matching_kotsu,
                    (SELECT COUNT(*) FROM gacha_log) AS gacha_total,
                """)
                #     (SELECT SUM(amount) FROM blackjack_record) AS blackjack_total,
                #     (SELECT SUM(amount) FROM hancho_record) AS chohan_total
                # """)
        except Exception as e:
            print(f"❌ DB error: {e}")
            return

        new_name = f"👩‍❤️‍💋‍👨マッチ：{row['matching_total']}回｜個通数：{row['matching_kotsu']}"
        gacha_name = f"🎰ガチャ：{row['gacha_total']}回"
        # blackjack_name = f"🃏ブラックジャック：{row['blackjack_total']}"
        # chohan_name = f"🎲チョーハン：{row['chohan_total']}"

        try:
            if matching_ch.name != new_name:
                await matching_ch.edit(name=new_name)
            if gacha_ch.name != gacha_name:
                await gacha_ch.edit(name=gacha_name)
            # if blackjack_ch.name != blackjack_name:
            #     await blackjack_ch.edit(name=blackjack_name)
            # if chohan_ch.name != chohan_name:
            #     await chohan_ch.edit(name=chohan_name)

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

