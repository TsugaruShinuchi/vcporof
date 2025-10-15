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
        self.profile_db_pool = db_pool
        print("✅ DB プールを初期化しました。")

        initial_extensions = [
            # "cogs.recruitment",
            # "cogs.modals",
            # "cogs.handlers",
            "cogs.profile",
            "cogs.encount"
        ]
        for ext in initial_extensions:
            await self.load_extension(ext)
        print("✅ Cogs を登録しました。")

        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)
        print("✅ ギルドコマンドを同期しました。")

        # from cogs.recruitment import RecruitmentView
        # self.add_view(RecruitmentView())
        # print(f"✅ DB プール初期化済: {self.profile_db_pool is not None}")

        # from cogs.handlers import DMDeleteButton
        # rows = await DB.get_all_recruit_messages()
        # for row in rows:
        #     view = discord.ui.View(timeout=None)
        #     view.add_item(DMDeleteButton(row["message_id"], row["channel_id"]))
        #     bot.add_view(view)

# 正しく MyBot を使用
bot = MyBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ ログインしました: {bot.user}")

bot.run(TOKEN)
