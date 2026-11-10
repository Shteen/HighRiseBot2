import os
import sys
import asyncio
import random
from aiohttp import web
from highrise import BaseBot, __main__
from highrise.__main__ import BotDefinition
from highrise.models import SessionMetadata, User, Position, CurrencyItem
from emotes import EMOTES

class HighriseBot(BaseBot):
    def __init__(self):
        super().__init__()
        # Role Management
        self.owners = {"astraeaclaire"}       # Add user IDs or usernames in string form
        self.mods = set()
        self.vips = set()
        self.bot_id = "cfeae7e59e084ceef7c10f09424870c0b66b9b12b30cde66b5caf69517bd385a"
        
        # State Tracking
        self.frozen_users = set()       # Set of frozen user IDs
        self.muted_users = set()        # Set of muted user IDs
        self.user_loops = {}            # {user_id: asyncio.Task}
        self.jail_location = None       # Position object for jail
        self.bail_location = None       # Position object for bail
        self.spawn_location = None      # Position object for custom spawn
        self.flash_mode = set()         # Users with flash click-teleport active

        # Teleport Dictionaries by Role Tier
        self.teleports = {}          # Public
        self.vip_teleports = {}      # VIP+
        self.mod_teleports = {}      # Mod+
        self.owner_teleports = {}    # Owner only
        
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
            "kiss": "emote-kiss",
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

        # ============================================================================================================
        # 🛡️ MODERATION CONTROL
        # ============================================================================================================
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


        # 1. Kick User: !kick @username (Mod / Owner)
        elif cmd == "!kick" and (self.is_mod(user) or self.is_owner(user)) and len(args) > 1:
            target_username = args[1].replace("@", "").lower()

            # Prevent staff members from kicking the Owner or themselves
            if target_username == "astraeaclaire" or target_username == user.username.lower():
                await self.highrise.chat("❌ Cannot kick this user.")
                return

            # Find target user in room
            room_users = await self.highrise.get_room_users()
            target_user = None
            for room_user, _ in room_users.content:
                if room_user.username.lower() == target_username:
                    target_user = room_user
                    break

            if not target_user:
                await self.highrise.chat(f"⚠️ User @{target_username} not found in room.")
                return

            try:
                # Moderate action: kick
                await self.highrise.moderate_room(target_user.id, "kick")
                await self.highrise.chat(f"👢 Kicked @{target_username} from the room.")
            except Exception as e:
                print(f"Kick error: {e}")
                await self.highrise.chat(f"❌ Failed to kick user. (Check bot permissions)")
            return

        # 2. Ban User: !ban @username [duration_seconds] (Owner Only or Mod)
        # Duration optional; defaults to 300s (5 min) or pass seconds (e.g., 3600 for 1 hr)
        elif cmd == "!ban" and (self.is_mod(user) or self.is_owner(user)) and len(args) > 1:
            target_username = args[1].replace("@", "").lower()
            
            # Default ban length (seconds). Standard options: 300 (5 min), 3600 (1hr), 86400 (1 day)
            ban_duration = 300
            if len(args) > 2 and args[2].isdigit():
                ban_duration = int(args[2])

            if target_username == "astraeaclaire" or target_username == user.username.lower():
                await self.highrise.chat("❌ Cannot ban this user.")
                return

            room_users = await self.highrise.get_room_users()
            target_user = None
            for room_user, _ in room_users.content:
                if room_user.username.lower() == target_username:
                    target_user = room_user
                    break

            if not target_user:
                await self.highrise.chat(f"⚠️ User @{target_username} not found in room.")
                return

            try:
                # Moderate action: ban (requires user ID, action, and duration in seconds)
                await self.highrise.moderate_room(target_user.id, "ban", ban_duration)
                await self.highrise.chat(f"🚫 Banned @{target_username} for {ban_duration} seconds.")
            except Exception as e:
                print(f"Ban error: {e}")
                await self.highrise.chat(f"❌ Failed to ban user. Ensure bot has room designer/host rights.")
            return


        # 3. Unban User ID: !unban [user_id] (Mod / Owner)
        elif cmd == "!unban" and (self.is_mod(user) or self.is_owner(user)) and len(args) > 1:
            target_id = args[1]
            try:
                await self.highrise.moderate_room(target_id, "unban")
                await self.highrise.chat(f"✅ Unbanned user ID {target_id}.")
            except Exception as e:
                await self.highrise.chat(f"❌ Failed to unban: {e}")
            return
        

        # ============================================================================================================
        # 💃 EMOTES & FUN ZONE
        # ============================================================================================================
       
        # Trigger an emote on the bot: !emote [name]
        elif cmd == "!emote" and len(args) > 1:
            keyword = args[1].lower()

            if not hasattr(self, 'bot_id') or not self.bot_id:
                await self.highrise.chat("❌ Bot ID not initialized. Hardcode self.bot_id in __init__.")
                return

            if keyword in EMOTES:
                emote_data = EMOTES[keyword]
                emote_id = emote_data["id"]
                try:
                    # Explicitly using keyword arguments to prevent positional mismatch
                    await self.highrise.send_emote(emote_id=emote_id, user_id=self.bot_id)
                    await self.highrise.chat(f"🎭 Bot performing emote: {keyword}")
                except Exception as e:
                    print(f"Emote error details: {e}")
                    await self.highrise.chat(f"❌ Failed to perform emote: {e}")
            else:
                await self.highrise.chat(f"❌ Unknown emote name.")
            return

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


        # Copy a user's outfit to the bot: !fit @username (Owner / Mod)
        elif cmd == "!fit" and (self.is_owner(user) or self.is_mod(user)) and len(args) > 1:
            target_username = args[1].replace("@", "").lower()

            # 1. Find target user in the room
            room_users = await self.highrise.get_room_users()
            target_user = None
            for room_user, _ in room_users.content:
                if room_user.username.lower() == target_username:
                    target_user = room_user
                    break

            if not target_user:
                await self.highrise.chat(f"⚠️ User @{target_username} not found in the room.")
                return

            try:
                # 2. Get the target user's current outfit
                target_outfit = await self.highrise.get_user_outfit(target_user.id)
                
                # 3. Apply outfit to the bot
                await self.highrise.set_outfit(outfit=target_outfit.outfit)
                await self.highrise.chat(f"✨ Successfully cloned @{target_username}'s outfit!")
            except Exception as e:
                print(f"Outfit copy error: {e}")
                await self.highrise.chat(f"❌ Failed to copy outfit: {e}")
            return

        # ============================================================================================================
        # 🚀 TELEPORTATION SYSTEM (WITH ROLES)
        # ============================================================================================================
        
        # 1. Public Keyword Teleport: !setkw [keyword] (Mod / Owner)
        elif cmd == "!setkw" and self.is_mod(user) and len(args) > 1:
            kw = args[1].lower()
            room_users = await self.highrise.get_room_users()
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    self.public_teleports[kw] = pos
                    await self.highrise.chat(f"📍 Public keyword warp '{kw}' saved!")
                    return

        # 2. VIP Keyword Teleport: !setvipkw [keyword] (VIP / Mod / Owner)
        elif cmd == "!setvipkw" and (self.is_vip(user) or self.is_mod(user)) and len(args) > 1:
            kw = args[1].lower()
            room_users = await self.highrise.get_room_users()
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    self.vip_teleports[kw] = pos
                    await self.highrise.chat(f"⭐ VIP keyword warp '{kw}' saved!")
                    return

        # 3. Mod Keyword Teleport: !setmodkw [keyword] (Mod / Owner)
        elif cmd == "!setmodkw" and self.is_mod(user) and len(args) > 1:
            kw = args[1].lower()
            room_users = await self.highrise.get_room_users()
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    self.mod_teleports[kw] = pos
                    await self.highrise.chat(f"🛡️ Mod keyword warp '{kw}' saved!")
                    return

        # 4. Owner Keyword Teleport: !setownerkw [keyword] (Owner Only)
        elif cmd == "!setownerkw" and self.is_owner(user) and len(args) > 1:
            kw = args[1].lower()
            room_users = await self.highrise.get_room_users()
            for room_user, pos in room_users.content:
                if room_user.id == user.id and isinstance(pos, Position):
                    self.owner_teleports[kw] = pos
                    await self.highrise.chat(f"👑 Owner keyword warp '{kw}' saved!")
                    return

        # Teleport a selected user to a keyword warp: !telekw @username [keyword] (Mod / Owner)
        elif cmd == "!telekw" and (self.is_mod(user) or self.is_owner(user)) and len(args) > 2:
            target_username = args[1].replace("@", "").lower()
            keyword = args[2].lower()
            
            # Find target user in the room
            room_users = await self.highrise.get_room_users()
            target_id = None
            for room_user, _ in room_users.content:
                if room_user.username.lower() == target_username:
                    target_id = room_user.id
                    break
            
            if not target_id:
                await self.highrise.chat(f"⚠️ User @{target_username} not found in the room.")
                return

            # Check and execute teleport based on where the keyword is stored
            if hasattr(self, 'public_teleports') and keyword in self.public_teleports:
                await self.highrise.teleport(target_id, self.public_teleports[keyword])
                await self.highrise.chat(f"✨ Teleported @{target_username} to public warp '{keyword}'.")
            elif hasattr(self, 'vip_teleports') and keyword in self.vip_teleports:
                await self.highrise.teleport(target_id, self.vip_teleports[keyword])
                await self.highrise.chat(f"✨ Teleported @{target_username} to VIP warp '{keyword}'.")
            elif hasattr(self, 'mod_teleports') and keyword in self.mod_teleports:
                await self.highrise.teleport(target_id, self.mod_teleports[keyword])
                await self.highrise.chat(f"✨ Teleported @{target_username} to Mod warp '{keyword}'.")
            elif hasattr(self, 'owner_teleports') and keyword in self.owner_teleports:
                await self.highrise.teleport(target_id, self.owner_teleports[keyword])
                await self.highrise.chat(f"✨ Teleported @{target_username} to Owner warp '{keyword}'.")
            else:
                await self.highrise.chat(f"❌ Keyword warp '{keyword}' does not exist.")
            return

            # Find target user ID and move them
            room_users = await self.highrise.get_room_users()
            target_user_id = None
            for room_user, _ in room_users.content:
                if room_user.username.lower() == target_username:
                    target_user_id = room_user.id
                    break

            if target_user_id and target_pos:
                await self.highrise.teleport(target_user_id, target_pos)
                await self.highrise.chat(f"✨ Teleported @{target_username} to '{loc_name}'.")
            else:
                await self.highrise.chat(f"⚠️ User @{target_username} not found in room.")

       # Secret Staff Teleport List: !alltele (Mod / Owner Only - Whispered)
        elif cmd == "!alltele" and (self.is_mod(user) or self.is_owner(user)):
            pub_list = ", ".join(self.public_teleports.keys()) if hasattr(self, 'public_teleports') and self.public_teleports else "None"
            vip_list = ", ".join(self.vip_teleports.keys()) if hasattr(self, 'vip_teleports') and self.vip_teleports else "None"
            mod_list = ", ".join(self.mod_teleports.keys()) if hasattr(self, 'mod_teleports') and self.mod_teleports else "None"
            owner_list = ", ".join(self.owner_teleports.keys()) if hasattr(self, 'owner_teleports') and self.owner_teleports else "None"

            whisper_msg = (
                "🔒 --- ALL AVAILABLE TELEPORTS ---\n"
                f"• Public: {pub_list}\n"
                f"• VIP: {vip_list}\n"
                f"• Mod: {mod_list}\n"
                f"• Owner: {owner_list}"
            )
            
            try:
                await self.highrise.send_whisper(user.id, whisper_msg)
            except Exception as e:
                print(f"Failed to send whisper: {e}")
            return

        # Remove a teleport keyword from any tier: !remtele [keyword] (Mod / Owner)
        elif cmd == "!remtele" and (self.is_mod(user) or self.is_owner(user)) and len(args) > 1:
            keyword = args[1].lower()
            removed = False

            # Check and delete from all tier dictionaries
            for tele_dict in [self.public_teleports, self.vip_teleports, self.mod_teleports, self.owner_teleports]:
                if keyword in tele_dict:
                    del tele_dict[keyword]
                    removed = True

            if removed:
                await self.highrise.chat(f"🗑️ Successfully removed teleport keyword '{keyword}'.")
            else:
                await self.highrise.chat(f"❌ Teleport keyword '{keyword}' not found in any tier.")
            return


        # --- DIRECT KEYWORD TELEPORT HANDLER ---
        kw_input = message.strip().lower()

        # Check Public Warps
        if hasattr(self, 'public_teleports') and kw_input in self.public_teleports:
            await self.highrise.teleport(user.id, self.public_teleports[kw_input])
            return

        # Check VIP Warps
        if hasattr(self, 'vip_teleports') and kw_input in self.vip_teleports:
            if self.is_vip(user) or self.is_mod(user) or self.is_owner(user):
                await self.highrise.teleport(user.id, self.vip_teleports[kw_input])
            else:
                await self.highrise.chat(f"❌ '{kw_input}' is a VIP-only location.")
            return

        # Check Mod Warps
        if hasattr(self, 'mod_teleports') and kw_input in self.mod_teleports:
            if self.is_mod(user) or self.is_owner(user):
                await self.highrise.teleport(user.id, self.mod_teleports[kw_input])
            else:
                await self.highrise.chat(f"❌ '{kw_input}' is a Mod-only location.")
            return

        # Check Owner Warps
        if hasattr(self, 'owner_teleports') and kw_input in self.owner_teleports:
            if self.is_owner(user):
                await self.highrise.teleport(user.id, self.owner_teleports[kw_input])
            else:
                await self.highrise.chat(f"❌ '{kw_input}' is an Owner-only location.")
            return

        # ============================================================================================================
        # 👥 STAFF & ACCESS CONTROL
        # ============================================================================================================
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

       # View All Assigned Roles (Prints names to Console & Chat)
        elif cmd == "!rolelist":
            owners_list = ", ".join(self.owners) if self.owners else "None"
            mods_list = ", ".join(self.mods) if self.mods else "None"
            vips_list = ", ".join(self.vips) if self.vips else "None"

            # 🖥️ Print detailed list of users by role to Render Console
            print("\n--- 📋 ROLE LIST MEMBERS ---")
            print(f"👑 Owners ({len(self.owners)}): {owners_list}")
            print(f"🛡️ Mods ({len(self.mods)}): {mods_list}")
            print(f"⭐ VIPs ({len(self.vips)}): {vips_list}")
            print("----------------------------\n")

            # Reply in game chat
            await self.highrise.chat(
                f"📋 Roles:\n"
                f"👑 Owners ({len(self.owners)}): {owners_list}\n"
                f"🛡️ Mods ({len(self.mods)}): {mods_list}\n"
                f"⭐ VIPs ({len(self.vips)}): {vips_list}"
            )

        elif cmd == "!setjoin" and self.is_owner(user) and len(args) > 1:
            self.welcome_message = " ".join(args[1:])
            await self.highrise.chat("Set room welcome message.")

        # ============================================================================================================
        # 🤖 BOT & ROOM FEATURES
        # ============================================================================================================


        # 1. Check Bot Wallet Balance: !wallet (Owner Only)
        elif cmd == "!wallet" and self.is_owner(user):
            try:
                wallet_info = await self.highrise.get_wallet()
                gold_balance = 0
                
                # Parse wallet content for gold currency
                for currency in wallet_info.content:
                    if currency.type == "gold":
                        gold_balance = currency.amount
                        break
                
                # Send private whisper to owner only
                await self.highrise.send_whisper(user.id, f"💰 Bot Wallet Balance: {gold_balance} Gold")
            except Exception as e:
                await self.highrise.chat(f"❌ Failed to fetch wallet balance: {e}")
            return

        # 2. Tip Specific User: !tip @username [amount] (Owner Only)
        elif cmd == "!tip" and self.is_owner(user) and len(args) > 2:
            target_username = args[1].replace("@", "").lower()
            amount_input = args[2].lower()
            
            amount_map = {
                "1": "gold_bar_1", "5": "gold_bar_5", "10": "gold_bar_10",
                "50": "gold_bar_50", "100": "gold_bar_100", "500": "gold_bar_500",
                "1k": "gold_bar_1k", "5000": "gold_bar_5000", "10k": "gold_bar_10k"
            }
            tip_amount = amount_map.get(amount_input, amount_input)
            
            if tip_amount not in amount_map.values():
                await self.highrise.chat("❌ Invalid amount. Options: 1, 5, 10, 50, 100, 500, 1k, 5000, 10k")
                return

            room_users = await self.highrise.get_room_users()
            target_id = None
            for room_user, _ in room_users.content:
                if room_user.username.lower() == target_username:
                    target_id = room_user.id
                    break

            if not target_id:
                await self.highrise.chat(f"⚠️ User @{target_username} not found in the room.")
                return

            try:
                await self.highrise.tip_user(target_id, tip_amount)
                await self.highrise.chat(f"💸 Tipped @{target_username} {amount_input} Gold!")
            except Exception as e:
                await self.highrise.chat(f"❌ Tip failed: {e}")
            return

        # 3. Tip ALL Users in the Room: !tipall [amount] (Owner Only)
        elif cmd == "!tipall" and self.is_owner(user) and len(args) > 1:
            amount_input = args[1].lower()
            amount_map = {
                "1": "gold_bar_1", "5": "gold_bar_5", "10": "gold_bar_10",
                "50": "gold_bar_50", "100": "gold_bar_100", "500": "gold_bar_500",
                "1k": "gold_bar_1k", "5000": "gold_bar_5000", "10k": "gold_bar_10k"
            }
            tip_amount = amount_map.get(amount_input, amount_input)

            if tip_amount not in amount_map.values():
                await self.highrise.chat("❌ Invalid amount. Options: 1, 5, 10, 50, 100, 500, 1k, 5000, 10k")
                return

            room_users = await self.highrise.get_room_users()
            tipped_count = 0

            for room_user, _ in room_users.content:
                # Skip tipping the bot itself
                if hasattr(self, 'bot_id') and room_user.id == self.bot_id:
                    continue
                try:
                    await self.highrise.tip_user(room_user.id, tip_amount)
                    tipped_count += 1
                except Exception as e:
                    print(f"Failed to tip {room_user.username}: {e}")

            await self.highrise.chat(f"🎉 Tipped {amount_input} Gold to all {tipped_count} users in the room!")
            return

        # 4. Tip a Random User in the Room: !tiprandom [amount] (Owner Only)
        elif cmd == "!tiprandom" and self.is_owner(user) and len(args) > 1:
            import random
            amount_input = args[1].lower()
            amount_map = {
                "1": "gold_bar_1", "5": "gold_bar_5", "10": "gold_bar_10",
                "50": "gold_bar_50", "100": "gold_bar_100", "500": "gold_bar_500",
                "1k": "gold_bar_1k", "5000": "gold_bar_5000", "10k": "gold_bar_10k"
            }
            tip_amount = amount_map.get(amount_input, amount_input)

            if tip_amount not in amount_map.values():
                await self.highrise.chat("❌ Invalid amount. Options: 1, 5, 10, 50, 100, 500, 1k, 5000, 10k")
                return

            room_users = await self.highrise.get_room_users()
            # Filter out the bot
            eligible_users = [
                u for u, _ in room_users.content 
                if not (hasattr(self, 'bot_id') and u.id == self.bot_id)
            ]

            if not eligible_users:
                await self.highrise.chat("⚠️ No eligible users in the room to tip.")
                return

            chosen_user = random.choice(eligible_users)

            try:
                await self.highrise.tip_user(chosen_user.id, tip_amount)
                await self.highrise.chat(f"🎲 Random winner! Tipped @{chosen_user.username} {amount_input} Gold!")
            except Exception as e:
                await self.highrise.chat(f"❌ Failed to tip random user: {e}")
            return

async def on_start(self, session_metadata: SessionMetadata):
    print("Bot online and ready!")
    if session_metadata.room_info and session_metadata.room_info.owner_id:
        self.owners.add(session_metadata.room_info.owner_id)


async def on_start(self, session_metadata: SessionMetadata):
        print("Bot online and ready!")
        
        # 1. Automatically register room owner from session metadata
        if session_metadata.room_info and session_metadata.room_info.owner_id:
            self.owners.add(str(session_metadata.room_info.owner_id))
            print(f"Added room owner ID '{session_metadata.room_info.owner_id}' to self.owners.")

        # 2. Retrieve room details to resolve owner's username if available
        try:
            room_users = await self.highrise.get_room_users()
            for room_user, _ in room_users.content:
                if str(room_user.id) in self.owners:
                    self.owners.add(room_user.username.lower())
        except Exception as e:
            print(f"Could not retrieve initial room users for owner check: {e}")

        # Capture the bot's own user ID
        if session_metadata and session_metadata.user_id:
            self.bot_id = session_metadata.user_id
            print(f"Bot User ID registered: {self.bot_id}")

        # (Keep your existing room owner code here if you have it)
        if session_metadata.room_info and session_metadata.room_info.owner_id:
            self.owners.add(str(session_metadata.room_info.owner_id))


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
