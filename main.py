import os
import asyncio
from aiohttp import web
from highrise import BaseBot, __main__
from highrise.__main__ import BotDefinition
from highrise.models import SessionMetadata, User

# 1. Highrise Bot Logic
class Bot(BaseBot):
    async def on_start(self, session_metadata: SessionMetadata):
        print("Bot is online and running on Render!")

    async def on_chat(self, user: User, message: str):
        print(f"{user.username}: {message}")

# 2. Keep-Alive Web Server for Render Health Checks
async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render assigns a dynamic port via environment variable PORT
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server running on port {port}")

# 3. Main Entry Point
async def main():
    room_id = os.environ.get("6894bd39e3e4a405517cb530")
    token = os.environ.get("cfeae7e59e084ceef7c10f09424870c0b66b9b12b30cde66b5caf69517bd385a")

    # Start both the web ping server and the Highrise bot concurrently
    await start_web_server()
    
    definitions = [BotDefinition(Bot(), room_id, token)]
    await __main__.main(definitions)

if __name__ == "__main__":
    asyncio.run(main())
