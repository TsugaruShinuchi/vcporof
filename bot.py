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
print("📦 POSTGRES_URI =", os.getenv("POSTGRES_URI"))
class MyBot(commands.Bot):
    async def setup_hook(self):
        db_pool = await DB.init_pool()

        self.db = db_pool                  # bump_count 用
        self.profile_db_pool = db_pool     # 既存COG互換用
        print("✅ DB プールを初期化しました。")

        initial_extensions = [
            "cogs.buddy_recruitment",
            "cogs.buddy_modals",
            "cogs.buddy_handlers",
            "cogs.profile",
            "cogs.encount",
            "cogs.bump_count",
            "cogs.gacha",
            "cogs.vc_counter",
            "cogs.complaint"
        ]
        for ext in initial_extensions:
            await self.load_extension(ext)
        print("✅ Cogs を登録しました。")

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print("✅ ギルドコマンドを同期しました。")

# 正しく MyBot を使用
bot = MyBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ ログインしました: {bot.user}")

bot.run(TOKEN)
