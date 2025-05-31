import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
from utils.db import DB

# .env 読み込み
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(commands.Bot):
    async def setup_hook():
        # DB 初期化
        db_pool=await DB.init_pool()
        bot.profile_db_pool = db_pool
        
        print("✅ DB プールを初期化しました。")

        # Cog を追加
        initial_extensions = [
            "cogs.recruitment",
            "cogs.modals",
            "cogs.handlers"
        ]
        for ext in initial_extensions:
            await bot.load_extension(ext)
        print("✅ Cogs を登録しました。")

        # ギルドコマンドを同期
        guild = discord.Object(id=GUILD_ID)
        await bot.tree.sync(guild=guild)
        print("✅ ギルドコマンドを同期しました。")

        from cogs.recruitment import RecruitmentView
        from cogs.profile import ProfileCog
        bot.add_view(RecruitmentView())
        await bot.add_cog(ProfileCog(bot))

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ ログインしました: {bot.user}")

bot.run(TOKEN)
