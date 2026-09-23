import os
import sys
import asyncio
import random
from aiohttp import web
from highrise import BaseBot, __main__
from highrise.__main__ import BotDefinition
from highrise.models import SessionMetadata, User, Position, CurrencyItem

class HighriseBot(BaseBot):
    def __init__(self):
        super().__init__()
        # Role Management
        self.owners = set()       # Add user IDs or usernames in string form
        self.mods = set()
        self.vips = set()
        
        # State Tracking
        self.frozen_users = set()       # Set of frozen user IDs
        self.muted_users = set()        # Set of muted user IDs
        self.user_loops = {}            # {user_id: asyncio.Task}
        self.jail_location = None       # Position object for jail
        self.bail_location = None       # Position object for bail
        self.spawn_location = None      # Position object for custom spawn
        self.teleports = {}             # {name: Position}
        self.vip_teleports = {}
        self.mod_teleports = {}
        self.owner_teleports = {}
        self.flash_mode = set()         # Users with flash click-teleport active
        
        # Room Settings & Custom Messages
        self.welcome_message = "Welcome to the room, {username}!"
        self.user_welcomes = {}         # {user_id: "custom message"}
        
        # Trivia State
        self.trivia_active = False
        self.trivia_question = None
        self.trivia_answer = None
        self.trivia_scores = {}         # {username: score}
        
        # Emotes & Reactions Dict
        self.emotes = {
            "dance": "dance-casual",
            "sing": "idle-singing",
            "wave": "emote-wave",
            "laugh": "emote-laugh",
            "kiss": "emote-kiss"
        }

    # Helper: Permission Checks
    def is_owner(self, user: User) -> bool:
        return user.username.lower() in self.owners or user.id in self.owners

    def is_mod(self, user: User) -> bool:
        return self.is_owner(user) or user.username.lower() in self.mods or user.id in self.mods

    def is_vip(self, user: User) -> bool:
        return self.is_mod(user) or user.username.lower() in self.vips or user.id in self.vips

    async def on_start(self, session_metadata: SessionMetadata):
        print("Bot online and ready!")
        # Automatically add the room owner from session metadata if available
        if session_metadata.room_info and session_metadata.room_info.owner_id:
            self.owners.add(session_metadata.room_info.owner_id)

    async def on_user_join(self, user: User, position: Position):
        # Spawn override if set
        if self.spawn_location:
            await self.highrise.teleport(user.id, self.spawn_location)
        
        # Welcome message priority: Custom personal welcome -> Room welcome
        if user.id in self.user_welcomes:
            await self.highrise.chat(self.user_welcomes[user.id].format(username=user.username))
        elif self.welcome_message:
            await self.highrise.chat(self.welcome_message.format(username=user.username))

    async def on_user_move(self, user: User, position: Position):
        # Freeze enforcement: Teleport user back to jail/frozen position if moved
        if user.id in self.frozen_users:
            if self.jail_location:
                await self.highrise.teleport(user.id, self.jail_location)

    async def on_chat(self, user: User, message: str):
        # Mute check: Ignore chat from muted users
        if user.id in self.muted_users:
            return

        msg = message.strip()
        args = msg.split()
        cmd = args[0].lower() if args else ""

        print(f"[{user.username}]: {message}")

        # --- Trivia Answer Handler ---
        if self.trivia_active and self.trivia_answer:
            if msg.lower() == self.trivia_answer.lower():
                await self.highrise.chat(f"🎉 Correct @{user.username}! The answer was '{self.trivia_answer}'.")
                self.trivia_scores[user.username] = self.trivia_scores.get(user.username, 0) + 1
                self.trivia_active = False
                self.trivia_answer = None

        # ==========================================
        # 🛡️ MODERATION CONTROL
        # ==========================================
        if cmd == "!freeze" and self.is_mod(user) and len(args) > 1:
            target = args[1].replace("@", "")
            # Lock target in frozen list
            self.frozen_users.add(target)
            await self.highrise.chat(f"🔒 @{target} has been frozen.")

        elif cmd == "!unfreeze" and self.is_mod(user) and len(args) > 1:
            target = args[1].replace("@", "")
            self.frozen_users.discard(target)
            await self.highrise.chat(f"🔓 @{target} has been unfrozen.")

        elif cmd == "!mute" and self.is_mod(user) and len(args) > 1:
            target = args[1].replace("@", "")
            self.muted_users.add(target)
            await self.highrise.chat(f"🔇 @{target} has been muted.")

        elif cmd == "!unmute" and self.is_mod(user) and len(args) > 1:
            target = args[1].replace("@", "")
            self.muted_users.discard(target)
            await self.highrise.chat(f"🔊 @{target} has been unmuted.")

        elif cmd == "!kick" and self.is_mod(user) and len(args) > 1:
            target = args[1].replace("@", "")
            try:
                await self.highrise.kick(target)
                await self.highrise.chat(f"👢 Kicked @{target} from the room.")
            except Exception as e:
                await self.highrise.chat(f"Failed to kick user: {e}")

        elif cmd == "!jail" and self.is_mod(user) and len(args) > 1:
            target = args[1].replace("@", "")
            if self.jail_location:
                self.frozen_users.add(target)
                await self.highrise.teleport(target, self.jail_location)
                await self.highrise.chat(f"⛓️ Sent @{target} to jail.")
            else:
                await self.highrise.chat("Jail location has not been set yet using !createjail.")

        elif cmd == "!bail" and self.is_mod(user) and len(args) > 1:
            target = args[1].replace("@", "")
            self.frozen_users.discard(target)
            if self.bail_location:
                await self.highrise.teleport(target, self.bail_location)
            await self.highrise.chat(f"🔓 @{target} was bailed from jail.")

        elif cmd == "!createjail" and self.is_owner(user):
            room_users = await self.highrise.get_room_users()
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    self.jail_location = pos
                    await self.highrise.chat("⛓️ Jail location set to your current position.")

        elif cmd == "!createbail" and self.is_owner(user):
            room_users = await self.highrise.get_room_users()
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    self.bail_location = pos
                    await self.highrise.chat("🔓 Bail location set to your current position.")

        elif cmd == "!setspawn" and self.is_mod(user):
            room_users = await self.highrise.get_room_users()
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    self.spawn_location = pos
                    await self.highrise.chat("📍 Custom room spawn location set.")

        elif cmd == "!stop":
            if user.id in self.user_loops:
                self.user_loops[user.id].cancel()
                del self.user_loops[user.id]
                await self.highrise.chat(f"Stopped active loops for @{user.username}.")

        elif cmd == "!stopall" and self.is_mod(user):
            for task in self.user_loops.values():
                task.cancel()
            self.user_loops.clear()
            await self.highrise.chat("Stopped all room loops.")

        # ==========================================
        # 💃 EMOTES & FUN ZONE
        # ==========================================
        elif cmd == "!emotelist":
            emote_names = ", ".join(self.emotes.keys())
            await self.highrise.chat(f"Available emotes: {emote_names}")

        elif cmd == "!trivia":
            if not self.trivia_active:
                questions = [
                    ("What is the chemical symbol for Gold?", "Au"),
                    ("Which planet is known as the Red Planet?", "Mars"),
                    ("How many sides does a hexagon have?", "6")
                ]
                q, a = random.choice(questions)
                self.trivia_question = q
                self.trivia_answer = a
                self.trivia_active = True
                await self.highrise.chat(f"❓ TRIVIA: {q} (Type !answer or type the answer directly)")

        elif cmd == "!stoptrivia" and self.is_mod(user):
            self.trivia_active = False
            self.trivia_answer = None
            await self.highrise.chat("Trivia game stopped.")

        elif cmd == "!triviascores":
            scores = ", ".join([f"{u}: {s}" for u, s in self.trivia_scores.items()])
            await self.highrise.chat(f"🏆 Scores: {scores if scores else 'No scores yet.'}")

        # ==========================================
        # 🚀 TELEPORTATION SYSTEM
        # ==========================================
        # 1. Create a Public Teleport Location (Mod/Owner)
        elif cmd == "!create" and len(args) > 2 and args[1].lower() == "tele" and self.is_mod(user):
            loc_name = args[2].lower()
            room_users = await self.highrise.get_room_users()
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    self.teleports[loc_name] = pos
                    await self.highrise.chat(f"📍 Public warp '{loc_name}' created at your position!")

        # 2. Teleport a User to a Saved Location: !tele @username loc_name
        elif cmd == "!tele" and len(args) > 2:
            target_username = args[1].replace("@", "").lower()
            loc_name = args[2].lower()

            if loc_name not in self.teleports:
                await self.highrise.chat(f"❌ Location '{loc_name}' does not exist. Use !listtele to see saved warps.")
            else:
                target_position = self.teleports[loc_name]
                room_users = await self.highrise.get_room_users()
                
                # Find the target user's ID from room users
                target_user_id = None
                for room_user, _ in room_users.content:
                    if room_user.username.lower() == target_username:
                        target_user_id = room_user.id
                        break

                if target_user_id:
                    await self.highrise.teleport(target_user_id, target_position)
                    await self.highrise.chat(f"✨ Teleported @{target_username} to '{loc_name}'.")
                else:
                    await self.highrise.chat(f"⚠️ User @{target_username} was not found in this room.")

        # 3. Teleport Yourself to Another User: !goto @username
        elif cmd == "!goto" and len(args) > 1:
            target_username = args[1].replace("@", "").lower()
            room_users = await self.highrise.get_room_users()
            
            target_pos = None
            for room_user, pos in room_users.content:
                if room_user.username.lower() == target_username and isinstance(pos, Position):
                    target_pos = pos
                    break

            if target_pos:
                await self.highrise.teleport(user.id, target_pos)
                await self.highrise.chat(f"✨ Teleported to @{target_username}.")
            else:
                await self.highrise.chat(f"⚠️ Could not locate @{target_username} in the room.")

        # 4. Bring a User to You: !summon @username
        elif cmd == "!summon" and self.is_mod(user) and len(args) > 1:
            target_username = args[1].replace("@", "").lower()
            room_users = await self.highrise.get_room_users()
            
            my_pos = None
            target_user_id = None
            
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    my_pos = pos
                if room_user.username.lower() == target_username:
                    target_user_id = room_user.id

            if my_pos and target_user_id:
                await self.highrise.teleport(target_user_id, my_pos)
                await self.highrise.chat(f"✨ Summoned @{target_username} to your position.")
            else:
                await self.highrise.chat("⚠️ Could not execute summon command.")

        # 5. List All Created Teleport Locations
        elif cmd == "!listtele":
            if self.teleports:
                locations = ", ".join(self.teleports.keys())
                await self.highrise.chat(f"📍 Available warps: {locations}")
            else:
                await self.highrise.chat("No public warps have been set yet. Use !create tele [name]")

        # 6. Delete a Saved Location (Mod/Owner)
        elif cmd == "!remtele" and self.is_mod(user) and len(args) > 1:
            loc_name = args[1].lower()
            if loc_name in self.teleports:
                del self.teleports[loc_name]
                await self.highrise.chat(f"🗑️ Removed teleport location '{loc_name}'.")
            else:
                await self.highrise.chat(f"Location '{loc_name}' not found.")

        # ==========================================
        # 👥 STAFF & ACCESS CONTROL
        # ==========================================
        elif cmd == "!mod" and self.is_owner(user) and len(args) > 1:
            target = args[1].replace("@", "").lower()
            self.mods.add(target)
            await self.highrise.chat(f"👑 Added @{target} as Moderator.")

        elif cmd == "!remmod" and self.is_owner(user) and len(args) > 1:
            target = args[1].replace("@", "").lower()
            self.mods.discard(target)
            await self.highrise.chat(f"Removed @{target} from Moderators.")

        elif cmd == "!vip" and self.is_mod(user) and len(args) > 1:
            target = args[1].replace("@", "").lower()
            self.vips.add(target)
            await self.highrise.chat(f"⭐ Added @{target} as VIP.")

        elif cmd == "!rolelist":
            await self.highrise.chat(f"Owners: {len(self.owners)} | Mods: {len(self.mods)} | VIPs: {len(self.vips)}")

        elif cmd == "!setjoin" and self.is_owner(user) and len(args) > 1:
            self.welcome_message = " ".join(args[1:])
            await self.highrise.chat("Set room welcome message.")

        # ==========================================
        # 🤖 BOT & ROOM FEATURES
        # ==========================================
        elif cmd == "!wallet" and self.is_mod(user):
            try:
                wallet = await self.highrise.get_wallet()
                gold = 0
                for item in wallet.content:
                    if isinstance(item, CurrencyItem) and item.type == "gold":
                        gold = item.amount
                await self.highrise.chat(f"💰 Bot Wallet Balance: {gold} Gold")
            except Exception as e:
                await self.highrise.chat(f"Could not retrieve wallet: {e}")

async def on_start(self, session_metadata: SessionMetadata):
    print("Bot online and ready!")
    if session_metadata.room_info and session_metadata.room_info.owner_id:
        self.owners.add(session_metadata.room_info.owner_id)


# --- Render Keep-Alive Web Server ---
async def handle_ping(request):
    return web.Response(text="Bot service is running.")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Keep-alive web server active on port {port}")

async def main():
    room_id = os.environ.get("ROOM_ID")
    token = os.environ.get("BOT_TOKEN")

    if not room_id or not token:
        print("ERROR: Missing ROOM_ID or BOT_TOKEN Environment Variables!", file=sys.stderr)
        sys.exit(1)

    await start_web_server()
    
    definitions = [BotDefinition(HighriseBot(), room_id, token)]
    await __main__.main(definitions)

if __name__ == "__main__":
    asyncio.run(main())
