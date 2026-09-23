import os
import sys
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

# 2. Keep-Alive Web Server for Render
async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server running on port {port}")

# 3. Main Entry Point
async def main():
    room_id = os.environ.get("ROOM_ID")
    token = os.environ.get("BOT_TOKEN")

    # Safety check: Verify variables are loaded
    if not room_id or not token:
        print("ERROR: ROOM_ID or BOT_TOKEN Environment Variables are missing in Render settings!", file=sys.stderr)
        sys.exit(1)

    await start_web_server()
    
    definitions = [BotDefinition(Bot(), room_id, token)]
    await __main__.main(definitions)

if __name__ == "__main__":
    asyncio.run(main())
