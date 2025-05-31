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
    async def setup_hook(self):
        db_pool = await DB.init_pool()
        self.profile_db_pool = db_pool
        print("✅ DB プールを初期化しました。")

        initial_extensions = [
            "cogs.recruitment",
            "cogs.modals",
            "cogs.handlers"
        ]
        for ext in initial_extensions:
            await self.load_extension(ext)
        print("✅ Cogs を登録しました。")

        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)
        print("✅ ギルドコマンドを同期しました。")

        from cogs.recruitment import RecruitmentView
        from cogs.profile import ProfileCog
        self.add_view(RecruitmentView())
        await self.add_cog(ProfileCog(self))
        print(f"✅ DB プール初期化済: {self.profile_db_pool is not None}")


# 正しく MyBot を使用
bot = MyBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ ログインしました: {bot.user}")

bot.run(TOKEN)
