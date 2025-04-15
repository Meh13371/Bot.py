import discord
from discord.ext import commands, tasks
import asyncio
import json
import os
import datetime

# --- INTENTS SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# --- BOT SETUP ---
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FILES ---
data_file = "data.json"
message_file = "message_id.txt"
last_cleared_date = None  # For daily clearing logic

# --- LOAD USER DATA ---
data = {}
if os.path.exists(data_file):
    with open(data_file, 'r') as f:
        data = json.load(f)

def save_data():
    try:
        with open(data_file, 'w') as f:
            json.dump(data, f, indent=4)
        print("✅ Data saved:", data)
    except Exception as e:
        print(f"❌ Error saving data: {e}")

# --- CLEAR DATA DAILY ---
def clear_protection_data_if_needed():
    global last_cleared_date
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    if last_cleared_date != today:
        for user_id in data:
            data[user_id]["protected_days"] = []
        last_cleared_date = today
        save_data()
        print(f"🧹 Protection data cleared for {today}.")

@tasks.loop(hours=24)
async def daily_clear_task():
    clear_protection_data_if_needed()

# --- UPDATE RAID PROTECTION LIST MESSAGE ---
async def update_protection_list(guild):
    if not guild:
        print("❌ No guild context.")
        return

    channel = discord.utils.get(guild.text_channels, name="raid-protected-elites")

    if not channel:
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False)
            }
            channel = await guild.create_text_channel("raid-protected-elites", overwrites=overwrites)
            print(f"[RaidBot] Created channel in {guild.name}")
        except discord.Forbidden:
            print("❌ Can't create channel (missing permissions).")
            return

    lines = ["🛡️ **Current Raid Protection List** (for today) 🛡️\n"]
    for user_id, info in data.items():
        if info["protected_days"]:
            member = guild.get_member(int(user_id))
            if member:
                lines.append(f"**{info['character_name']}** ({member.display_name})")

    message_text = "\n".join(lines) if len(lines) > 1 else "No players are protected today."

    if os.path.exists(message_file):
        with open(message_file, 'r') as f:
            try:
                msg_id = int(f.read())
                msg = await channel.fetch_message(msg_id)
                await msg.edit(content=message_text)
                return
            except:
                pass

    msg = await channel.send(message_text)
    with open(message_file, 'w') as f:
        f.write(str(msg.id))
    await msg.pin()

@bot.event
async def on_ready():
    print(f"[RaidBot] Logged in as {bot.user}")
    if not daily_clear_task.is_running():
        daily_clear_task.start()
    for guild in bot.guilds:
        await update_protection_list(guild)

# --- REGISTER ---
@bot.command()
async def register(ctx, character_name: str = None):
    user_id = str(ctx.author.id)
    if not character_name:
        await ctx.send("⚠️ Please provide a character name. `!register [Name]`")
        return

    if ctx.guild:
        try:
            await ctx.message.delete()
        except:
            pass

    if user_id in data:
        await ctx.author.send("⚠️ You're already registered. Use `!status` or `!protect`.")
        return

    data[user_id] = {"character_name": character_name, "protected_days": []}
    save_data()

    if ctx.guild:
        try:
            await ctx.author.edit(nick=character_name)
        except:
            pass

    await ctx.author.send(
        f"✅ Registered as **{character_name}**!\n\n"
        "Use these DM commands:\n"
        "`!protect`\n`!status`\n`!unprotect`\n`!unregister`\n"
        "`!helpRP` for help."
    )

# --- PROTECT ---
@bot.command()
async def protect(ctx):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("⚠️ Use this command in DMs.")
        return

    user_id = str(ctx.author.id)
    if user_id not in data:
        await ctx.send("⚠️ You're not registered. Use `!register [Name]`.")
        return

    # Get today's day (UTC)
    today = datetime.datetime.now(datetime.timezone.utc).strftime('%A')

    # Set protection just for today
    data[user_id]["protected_days"] = [today]
    save_data()

    # Update raid list in all guilds
    for guild in bot.guilds:
        member = guild.get_member(int(user_id))
        if member:
            await update_protection_list(guild)
            break

    await ctx.send(f"✅ You are now protected for **{today}**.")

# --- UNPROTECT ---
@bot.command()
async def unprotect(ctx):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("⚠️ Use this command in DMs.")
        return

    user_id = str(ctx.author.id)
    if user_id not in data:
        await ctx.send("⚠️ You're not registered.")
        return

    data[user_id]["protected_days"] = []
    save_data()

    for guild in bot.guilds:
        member = guild.get_member(int(user_id))
        if member:
            await update_protection_list(guild)
            break

    await ctx.send("🗑️ Your raid protection has been removed.")

# --- UNREGISTER ---
@bot.command()
async def unregister(ctx):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("⚠️ Use this command in DMs.")
        return

    user_id = str(ctx.author.id)
    if user_id not in data:
        await ctx.send("⚠️ You're not registered.")
        return

    del data[user_id]
    save_data()

    for guild in bot.guilds:
        member = guild.get_member(int(user_id))
        if member:
            try:
                await member.edit(nick=None)
            except:
                pass
            break

    await ctx.send("✅ You’ve been unregistered.")

# --- STATUS ---
@bot.command()
async def status(ctx):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("⚠️ Use this command in DMs.")
        return

    user_id = str(ctx.author.id)
    if user_id not in data:
        await ctx.send("⚠️ You are not registered.")
        return

    tribe_name = data[user_id]["tribe_name"] if "tribe_name" in data[user_id] else data[user_id]["character_name"]

    for guild in bot.guilds:
        member = guild.get_member(int(user_id))
        if member:
            channel = discord.utils.get(guild.text_channels, name="raid-protected-elites")
            if not channel:
                await ctx.send("⚠️ Protection list channel not found.")
                return

            # Fetch the last pinned message (the list)
            pinned = await channel.pins()
            if pinned:
                message = pinned[0]
                if tribe_name.lower() in message.content.lower() or member.display_name.lower() in message.content.lower():
                    await ctx.send(f"✅ Your tribe **{tribe_name}** is protected today.")
                    return
                else:
                    await ctx.send(f"❌ Your tribe **{tribe_name}** is not on the protection list for today.")
                    return

    await ctx.send("⚠️ Could not verify your protection status.")

# --- HELP ---
@bot.command(name="helpRP")
async def helpRP(ctx):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("⚠️ Use this command in DMs.")
        return

    await ctx.send("""
**🛡️ Raid Protection Bot Help**

Commands:
- `!register [Name]` – Register your character
- `!protect` – Choose protection days
- `!unprotect` – Remove protection days
- `!status` – View your protection status
- `!unregister` – Remove your registration
""")

# --- RUN THE BOT ---
bot.run("")
