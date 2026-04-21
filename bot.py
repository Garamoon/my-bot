import discord
from discord.ext import commands
import json
import os
import threading
from flask import Flask

# ===== Keep-Alive (Hugging Face) =====
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ CAS Ticket Bot is alive!", 200

@app.route("/health")
def health():
    return "OK", 200

def run_web():
    app.run(host="0.0.0.0", port=7860, debug=False, use_reloader=False)

# ===== ENV =====
TOKEN = os.environ.get("TOKEN")

SUPPORT_ROLE_ID =  os.environ.get("SUPPORT_ROLE_ID")
EXTRA_ROLE_ID = os.environ.get("EXTRA_ROLE_ID")
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID")
PANEL_CHANNEL_ID = os.environ.get("PANEL_CHANNEL_ID")
CATEGORY_CHANNELS = {
    "shop": os.environ.get("Category_shop"),
    "lol": os.environ.get("Category_lol"),
    "valorant": os.environ.get("Category_valorant"),
    "marvel": os.environ.get("Category_marvel"),
}

CATEGORY_RULES = {
    "shop":    os.environ.get("Rules_Shop"),
    "lol":     os.environ.get("Rules_lol"),
    "valorant": os.environ.get("Rules_valorant"),
    "marvel": os.environ.get("Rules_marvel"),
}

# ===== Descriptions =====
DESCRIPTIONS_FILE = "descriptions.json"
VALID_CATEGORIES  = ["shop", "lol", "valorant", "marvel"]

def load_descriptions():
    if os.path.exists(DESCRIPTIONS_FILE):
        with open(DESCRIPTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {cat: "" for cat in VALID_CATEGORIES}

def save_descriptions(data):
    with open(DESCRIPTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===== Pending setdesc =====
pending_setdesc = {}

# ===== Ticket Counters =====
COUNTER_FILE = "tickets.json"
if os.path.exists(COUNTER_FILE):
    with open(COUNTER_FILE, "r") as f:
        ticket_counters = json.load(f)
else:
    ticket_counters = {"shop": 16, "lol": 275, "valorant": 60, "marvel": 66}

def save_counters():
    with open(COUNTER_FILE, "w") as f:
        json.dump(ticket_counters, f)

# ===== Ticket Owners (thread_id -> member_id) =====
OWNERS_FILE = "ticket_owners.json"

def load_owners():
    if os.path.exists(OWNERS_FILE):
        with open(OWNERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_owner(thread_id: int, member_id: int):
    owners = load_owners()
    owners[str(thread_id)] = member_id
    with open(OWNERS_FILE, "w") as f:
        json.dump(owners, f)

def get_owner(thread_id: int):
    owners = load_owners()
    return owners.get(str(thread_id))

def remove_owner(thread_id: int):
    owners = load_owners()
    owners.pop(str(thread_id), None)
    with open(OWNERS_FILE, "w") as f:
        json.dump(owners, f)

# ===== Bot =====
intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="cas", intents=intents, help_command=None)


# ===== Close Reason Modal =====
class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):

    reason = discord.ui.TextInput(
        label="Reason for closing | سبب الإغلاق",
        placeholder="Enter the reason...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, thread: discord.Thread):
        super().__init__()
        self.thread = thread

    async def on_submit(self, interaction: discord.Interaction):
        thread      = self.thread
        guild       = interaction.guild
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        reason_text = self.reason.value.strip()

        log_embed = discord.Embed(title="🔒 Ticket Closed", color=discord.Color.green())
        log_embed.add_field(name="Ticket",    value=thread.name)
        log_embed.add_field(name="Opened By", value=f"<@{thread.owner_id}>")
        log_embed.add_field(name="Closed By", value=interaction.user.mention)
        log_embed.add_field(name="Reason",    value=reason_text, inline=False)
        log_embed.add_field(name="Time",      value=discord.utils.format_dt(discord.utils.utcnow()))

        link_view = discord.ui.View()
        link_view.add_item(discord.ui.Button(label="View Thread", url=thread.jump_url))

        if log_channel:
            await log_channel.send(embed=log_embed, view=link_view)

        # DM the ticket owner with ticket name, number, and reason
        try:
            owner_id = get_owner(thread.id)
            owner = guild.get_member(owner_id) if owner_id else None
            if owner:
                dm_embed = discord.Embed(
                    title="🔒 تم إغلاق تيكتك",
                    color=discord.Color.red()
                )
                dm_embed.add_field(name="📋 اسم التيكت",  value=thread.name, inline=True)
                dm_embed.add_field(name="🔢 رقم التيكت",  value=thread.name.split("-")[-1], inline=True)
                dm_embed.add_field(name="❌ سبب الإغلاق", value=reason_text, inline=False)
                dm_embed.add_field(name="👤 أغلقه",       value=interaction.user.display_name, inline=True)
                dm_embed.add_field(name="🕐 الوقت",       value=discord.utils.format_dt(discord.utils.utcnow()), inline=True)
                dm_embed.set_footer(text="شكراً لتواصلك مع 𝗖𝗶𝗴𝗮𝗿𝗲𝘁𝘁𝗲𝘀 𝗔𝗳𝘁𝗲𝗿 𝗦𝗲𝗹𝗹 Stores ❤️")
                await owner.send(embed=dm_embed)
            remove_owner(thread.id)
        except Exception:
            pass

        await interaction.response.send_message("✅ Ticket closed", ephemeral=True)
        await thread.edit(archived=True)


# ===== Ticket Buttons (Claim / Close) =====
class TicketButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, custom_id="ticket_claim_button")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📌 Claimed by {interaction.user.mention}", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket_close_button")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CloseReasonModal(thread=interaction.channel))


# ===== Ticket Modal =====
class TicketModal(discord.ui.Modal, title="CAS Ticket Questions"):

    # السؤال 1: رقم المحفظة
    wallet = discord.ui.TextInput(
        label="E-wallet number | رقم المحفظة",
        placeholder="01XXXXXXXXX",
        required=True,
        max_length=20
    )
    # السؤال 2: المحفظة باسم مين
    wallet_owner = discord.ui.TextInput(
        label="ألمحفظة دي باسم مين ؟",
        placeholder="اكتب الاسم هنا...",
        required=True,
        max_length=50
    )
    # السؤال 3: قرأت القواعد
    read_rules = discord.ui.TextInput(
        label="Read the Rules? | قرأت القواعد؟",
        placeholder="yes / no",
        required=True,
        max_length=10
    )

    def __init__(self, category: str):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        category    = self.category
        guild       = interaction.guild
        member      = interaction.user
        read_yes    = self.read_rules.value.strip().lower() == "yes"

        channel = guild.get_channel(CATEGORY_CHANNELS.get(category))
        if not channel:
            return await interaction.followup.send("❌ Category channel not found", ephemeral=True)

        ticket_counters[category] += 1
        save_counters()

        ticket_name = f"{category}-{str(ticket_counters[category]).zfill(3)}"

        thread = await channel.create_thread(
            name=ticket_name,
            type=discord.ChannelType.private_thread,
            auto_archive_duration=1440
        )

        save_owner(thread.id, member.id)

        await thread.send(f"{member.mention} <@&{SUPPORT_ROLE_ID}> <@&{EXTRA_ROLE_ID}>")

        answers_embed = discord.Embed(
            title="🎫 CAS Ticket Questions",
            color=discord.Color.purple()
        )
        answers_embed.set_footer(text="⚠️ This form was submitted to 𝗖𝗶𝗴𝗮𝗿𝗲𝘁𝘁𝗲𝘀 𝗔𝗳𝘁𝗲𝗿 𝗦𝗲𝗹𝗹 Stores. Do not share passwords or other sensitive information.")
        answers_embed.add_field(name="💳 E-wallet number | رقم المحفظة", value=self.wallet.value, inline=False)
        answers_embed.add_field(name="👤 ألمحفظة دي باسم مين ؟", value=self.wallet_owner.value, inline=False)
        answers_embed.add_field(name="Read the Rules? | قرأت القواعد؟", value="✅ yes" if read_yes else "❌ no", inline=True)
        await thread.send(embed=answers_embed, view=TicketButtons())

        if not read_yes:
            rules_channel_id = CATEGORY_RULES.get(category)
            if rules_channel_id:
                rules_embed = discord.Embed(
                    title="📋 اقرأ القواعد الأول!",
                    description=(
                        f"يا {member.mention} لازم تقرأ القواعد الأول في <#{int(rules_channel_id)}> ✅\n"
                        "خش اقرأ ولو في حاجة انت مش فاهمها في الرولز قبل ما تاخد شغل عرف الادمن وهو هيفهمك."
                    ),
                    color=discord.Color.red()
                )
                await thread.send(embed=rules_embed)

        description_text = load_descriptions().get(category, "")
        if description_text:
            await thread.send(embed=discord.Embed(
                title="📋 تعليمات",
                description=description_text,
                color=discord.Color.blurple()
            ))

        await interaction.followup.send(f"✅ Ticket created: {thread.mention}", ephemeral=True)


# ===== Ticket Select =====
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Buy From Our Shop", value="shop",     emoji=discord.PartialEmoji(name="shop",     id=1475214748021948456)),
            discord.SelectOption(label="League of Legends", value="lol",      emoji=discord.PartialEmoji(name="lol",      id=1475214617511723128)),
            discord.SelectOption(label="Valorant",          value="valorant",  emoji=discord.PartialEmoji(name="valorant", id=1433440387074232330)),
            discord.SelectOption(label="Marvel Rivals",     value="marvel",   emoji=discord.PartialEmoji(name="marvel",   id=1475216899141795954)),
        ]
        super().__init__(placeholder="Choose a category", options=options, custom_id="ticket_category_select")

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        await interaction.response.send_modal(TicketModal(category=category))
        # reset select after modal opens
        for opt in self.options:
            opt.default = False
        try:
            await interaction.message.edit(content=PANEL_TEXT, view=self.view)
        except Exception:
            pass


# ===== Ticket View =====
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ===== Panel =====
PANEL_TEXT = "💎 اهلا بيك يا غالي اتفضل اختار الخدمة اللي انت عايزها 💎"

# ===== Commands =====

@bot.command(name="panel")
async def cas_panel(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admin only")
    await ctx.message.delete()
    await ctx.send(content=PANEL_TEXT, view=TicketView())


@bot.command(name="setdesc")
async def cas_setdesc(ctx, category: str = None):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admin only")
    if not category:
        return await ctx.send(f"❌ مثال: `cassetdesc lol` | الكاتيجوريز: `{', '.join(VALID_CATEGORIES)}`")
    category = category.lower()
    if category not in VALID_CATEGORIES:
        return await ctx.send(f"❌ كاتيجوري غلط. المتاحة: `{', '.join(VALID_CATEGORIES)}`")
    pending_setdesc[ctx.channel.id] = {"author_id": ctx.author.id, "category": category}
    await ctx.send(f"✏️ ابعت الرسالة اللي عايزها تتحط في تيكت **{category}** 👇\n*(ابعت `cancel` للإلغاء)*")




@bot.command(name="help")
async def cas_help_cmd(ctx):
    embed = discord.Embed(title="📋 أوامر البوت", color=discord.Color.purple())
    embed.add_field(name="🎫 caspanel", value="يبعت البانل في الشانل الحالي", inline=False)
    embed.add_field(name="✏️ cassetdesc [category]", value="يضيف تعليمات جوه التيكت\nمثال: cassetdesc lol\nالكاتيجوريز: shop / lol / valorant / marvel", inline=False)
    embed.add_field(name="👁️ casviewdesc [category]", value="يعرض التعليمات الحالية\nمثال: casviewdesc lol", inline=False)
    embed.add_field(name="🗑️ cascleardesc [category]", value="يمسح التعليمات من كاتيجوري\nمثال: cascleardesc lol", inline=False)
    embed.add_field(name="📋 caslistdesc", value="يعرض كل التعليمات لكل الكاتيجوريز", inline=False)
    embed.set_footer(text="⚠️ كل الأوامر دي للأدمن بس")
    await ctx.send(embed=embed)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.id in pending_setdesc:
        pending = pending_setdesc[message.channel.id]
        if message.author.id == pending["author_id"]:
            del pending_setdesc[message.channel.id]
            if message.content.strip().lower() == "cancel":
                return await message.channel.send("❌ تم إلغاء العملية.")
            category     = pending["category"]
            descriptions = load_descriptions()
            descriptions[category] = message.content.strip()
            save_descriptions(descriptions)
            embed = discord.Embed(
                title=f"✅ تم تحديث وصف **{category}**",
                description=message.content.strip(),
                color=discord.Color.green()
            )
            return await message.channel.send(embed=embed)
    await bot.process_commands(message)


@bot.command(name="viewdesc")
async def cas_viewdesc(ctx, category: str = None):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admin only")
    if not category:
        return await ctx.send("❌ مثال: `casviewdesc lol`")
    category = category.lower()
    if category not in VALID_CATEGORIES:
        return await ctx.send(f"❌ كاتيجوري غلط. المتاحة: `{', '.join(VALID_CATEGORIES)}`")
    descriptions = load_descriptions()
    desc = descriptions.get(category, "")
    await ctx.send(embed=discord.Embed(
        title=f"📋 وصف تيكت: {category}",
        description=desc if desc else "*(مفيش وصف متحط)*",
        color=discord.Color.blurple()
    ))


@bot.command(name="cleardesc")
async def cas_cleardesc(ctx, category: str = None):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admin only")
    if not category:
        return await ctx.send("❌ مثال: `cascleardesc lol`")
    category = category.lower()
    if category not in VALID_CATEGORIES:
        return await ctx.send(f"❌ كاتيجوري غلط. المتاحة: `{', '.join(VALID_CATEGORIES)}`")
    descriptions = load_descriptions()
    descriptions[category] = ""
    save_descriptions(descriptions)
    await ctx.send(f"🗑️ تم مسح وصف **{category}**.")


@bot.command(name="listdesc")
async def cas_listdesc(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admin only")
    descriptions = load_descriptions()
    embed = discord.Embed(title="📋 كل الوصفات", color=discord.Color.blurple())
    for cat in VALID_CATEGORIES:
        desc = descriptions.get(cat, "")
        embed.add_field(
            name=f"🔹 {cat}",
            value=desc[:200] + "..." if len(desc) > 200 else (desc if desc else "*(مفيش وصف)*"),
            inline=False
        )
    await ctx.send(embed=embed)


# ===== On Ready =====
@bot.event
async def on_ready():
    bot.add_view(TicketButtons())
    bot.add_view(TicketView())
    print(f"✅ Logged in as {bot.user}")

    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                for thread in channel.threads:
                    try:
                        await thread.join()
                    except Exception:
                        pass
                async for thread in channel.archived_threads(limit=None):
                    try:
                        await thread.unarchive()
                        await thread.join()
                        await thread.edit(archived=True)
                    except Exception:
                        pass
            except Exception:
                pass

        panel_channel = guild.get_channel(PANEL_CHANNEL_ID)
        if not panel_channel:
            continue

        async for msg in panel_channel.history(limit=1000):
            if msg.author == bot.user:
                try:
                    await msg.delete()
                except Exception:
                    pass

        await panel_channel.send(content=PANEL_TEXT, view=TicketView())
        print(f"Panel sent to #{panel_channel.name}")


# ===== Run =====
if __name__ == "__main__":
    # شغّل Flask في thread منفصل عشان Hugging Face يشوف web server ومش يعمل sleep
    t = threading.Thread(target=run_web, daemon=True)
    t.start()
    print("🌐 Web server started on port 7860")
    bot.run(TOKEN)
