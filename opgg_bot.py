import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import concurrent.futures
import logging
import random
import time
import os
import shutil

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE")
BOT_PREFIX     = "!"
MAX_WORKERS    = 5
MAX_QUEUE      = 10
SCRAPE_TIMEOUT = 160

executor    = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
semaphore   = None
queue_count = 0


# ─── Driver Factory ──────────────────────────────────────────────────────────
def create_driver() -> webdriver.Chrome:
    """
    بيكتشف تلقائياً هو شغال على Railway (Linux + Nix Chromium)
    أو على الجهاز المحلي (undetected-chromedriver).
    """
    # Railway بيحط chromium في /usr/bin/chromium أو /run/current-system
    chromium_path   = shutil.which("chromium") or shutil.which("chromium-browser")
    chromedriver_path = shutil.which("chromedriver")
    on_railway = bool(chromium_path and chromedriver_path)

    options = webdriver.ChromeOptions() if on_railway else uc.ChromeOptions()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-US,en;q=0.9")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    # إخفاء علامات الأتمتة
    options.add_experimental_option("excludeSwitches", ["enable-automation"]) if on_railway else None
    options.add_experimental_option("useAutomationExtension", False)          if on_railway else None

    if on_railway:
        options.binary_location = chromium_path
        service = Service(executable_path=chromedriver_path)
        driver  = webdriver.Chrome(service=service, options=options)
        log.info(f"Running on Railway → chromium={chromium_path}")
    else:
        driver = uc.Chrome(options=options)
        log.info("Running locally → undetected-chromedriver")

    # إزالة webdriver flag
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins',   { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
        window.chrome = { runtime: {} };
        const origQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (p) =>
            p.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : origQuery(p);
    """})
    return driver


def human_delay(mn=0.5, mx=1.5):
    time.sleep(random.uniform(mn, mx))


# ─── Scraper ─────────────────────────────────────────────────────────────────
def scrape_opgg(server: str, game_name: str, hashtag: str) -> dict:
    url = f"https://www.op.gg/lol/summoners/{server}/{game_name}-{hashtag}?queue_type=ARAM"
    log.info(f"Opening: {url}")
    driver = create_driver()
    wait   = WebDriverWait(driver, 20)
    try:
        driver.get(url)
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        human_delay(1.5, 2.5)

        if "Just a moment" in driver.title:
            log.warning("Cloudflare detected, waiting…")
            human_delay(8, 12)

        # Update button
        try:
            update_btn = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((
                By.XPATH, "//button[.//span[normalize-space()='Update']]"
            )))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", update_btn)
            human_delay(0.5, 1.0)
            update_btn.click()
            log.info("Clicked Update, waiting for refresh…")
            try:
                WebDriverWait(driver, 35).until(EC.staleness_of(update_btn))
            except TimeoutException:
                try:
                    WebDriverWait(driver, 10).until(EC.invisibility_of_element(update_btn))
                except TimeoutException:
                    log.warning("Update btn still visible – continuing.")
            human_delay(1.0, 2.0)
        except TimeoutException:
            log.info("No Update button – already fresh.")

        # Level
        level = wait.until(EC.presence_of_element_located((By.XPATH,
            "//span[contains(@class,'rounded-[10px]') and contains(@class,'bg-[var(--color-gray-900)]')]"
        ))).text.strip()

        # KDA
        kda_el  = wait.until(EC.presence_of_element_located((By.XPATH,
            "//div[contains(@data-tooltip-content,'/ D') and contains(text(),'KDA')]"
        )))
        kda     = kda_el.text.strip()
        kda_raw = kda_el.get_attribute("data-tooltip-content")

        # Win Rate
        win_rate = wait.until(EC.presence_of_element_located((By.XPATH,
            "//span[contains(@class,'text-gray-400') and contains(text(),'Win rate')]"
        ))).text.strip()

        log.info(f"Level={level} | KDA={kda} ({kda_raw}) | WR={win_rate}")
        return {"success": True, "summoner": f"{game_name}#{hashtag}",
                "server": server.upper(), "level": level,
                "kda": kda, "kda_raw": kda_raw,
                "win_rate": win_rate, "url": url}

    except TimeoutException:
        try: driver.save_screenshot("/tmp/opgg_debug.png")
        except: pass
        return {"success": False, "error": "⏱️ انتهى الوقت – تأكد إن الاسم صح أو جرّب بعدين."}
    except NoSuchElementException as e:
        log.error(e)
        return {"success": False, "error": "❌ مش لاقي العنصر – ممكن الموقع اتغير."}
    except Exception as e:
        log.error(e)
        return {"success": False, "error": f"❌ خطأ: {e}"}
    finally:
        driver.quit()


# ─── Queue Handler ────────────────────────────────────────────────────────────
async def handle_request(server: str, game_name: str, hashtag: str) -> dict:
    global queue_count
    if queue_count >= MAX_QUEUE:
        return {"success": False,
                "error": f"🚦 الطابور ممتلي ({MAX_QUEUE} طلب)، جرّب بعد شوية."}
    queue_count += 1
    log.info(f"Request queued (total={queue_count})")
    try:
        async with semaphore:
            queue_count -= 1
            loop = asyncio.get_event_loop()
            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(executor, scrape_opgg, server, game_name, hashtag),
                    timeout=SCRAPE_TIMEOUT
                )
            except asyncio.TimeoutError:
                return {"success": False, "error": "⏱️ استغرق وقت طويل جداً، جرّب تاني."}
    except Exception as e:
        queue_count -= 1
        return {"success": False, "error": f"❌ خطأ داخلي: {e}"}


# ─── Embeds ───────────────────────────────────────────────────────────────────
def build_embed(data: dict, requester: discord.User) -> discord.Embed:
    if not data["success"]:
        e = discord.Embed(title="❌ حصل خطأ", description=data["error"], color=discord.Color.red())
        e.set_footer(text=f"طلب من: {requester.display_name}")
        return e
    wr  = int(''.join(filter(str.isdigit, data["win_rate"])) or 0)
    col = discord.Color.green() if wr >= 60 else discord.Color.gold() if wr >= 50 else discord.Color.red()
    e   = discord.Embed(title=f"🎮  {data['summoner']}", url=data["url"], color=col)
    e.add_field(name="🌍 Server",   value=data["server"],   inline=True)
    e.add_field(name="⭐ Level",    value=data["level"],    inline=True)
    e.add_field(name="\u200b",      value="\u200b",         inline=True)
    e.add_field(name="⚔️ KDA",      value=f"{data['kda']}\n`{data.get('kda_raw','')}`", inline=True)
    e.add_field(name="📊 Win Rate", value=data["win_rate"], inline=True)
    e.add_field(name="\u200b",      value="\u200b",         inline=True)
    e.set_footer(text=f"Queue: ARAM  •  طلب من: {requester.display_name}",
                 icon_url=requester.display_avatar.url)
    e.set_thumbnail(url="https://opgg-static.akamaized.net/images/logo/2022/logo_dark.png")
    return e


def build_queue_embed(position: int, requester: discord.User) -> discord.Embed:
    e = discord.Embed(
        title="⏳ في الطابور",
        description=f"كل الـ workers شغالين.\nطلبك رقم **#{position}** في الطابور، استنى شوية... 🎮",
        color=discord.Color.blurple()
    )
    e.set_footer(text=f"طلب من: {requester.display_name}", icon_url=requester.display_avatar.url)
    return e


# ─── Bot ─────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)


@bot.event
async def on_ready():
    global semaphore
    semaphore = asyncio.Semaphore(MAX_WORKERS)
    await bot.tree.sync()
    log.info(f"✅ Bot online as {bot.user} | workers={MAX_WORKERS} | queue_limit={MAX_QUEUE}")


@bot.tree.command(name="opgg", description="اجيب stats من OP.GG (ARAM)")
@app_commands.describe(server="السيرفر (euw/na/eune/kr)", game_name="اسم اللاعب", hashtag="الهاشتاج بدون #")
async def opgg_slash(interaction: discord.Interaction, server: str, game_name: str, hashtag: str):
    global queue_count
    if queue_count >= MAX_QUEUE:
        await interaction.response.send_message(
            embed=build_embed({"success": False,
                "error": f"🚦 الطابور ممتلي ({MAX_QUEUE} طلب)، جرّب بعد شوية."}, interaction.user),
            ephemeral=True)
        return
    in_queue = queue_count > 0 and semaphore.locked()
    await interaction.response.defer(thinking=True)
    if in_queue:
        await interaction.followup.send(embed=build_queue_embed(queue_count + 1, interaction.user))
    data = await handle_request(server.lower(), game_name, hashtag)
    if in_queue:
        await interaction.edit_original_response(embed=build_embed(data, interaction.user))
    else:
        await interaction.followup.send(embed=build_embed(data, interaction.user))


@bot.command(name="opgg")
async def opgg_prefix(ctx: commands.Context, server: str, game_name: str, hashtag: str):
    """!opgg <server> <game_name> <hashtag>"""
    global queue_count
    if queue_count >= MAX_QUEUE:
        await ctx.reply(embed=build_embed({"success": False,
            "error": f"🚦 الطابور ممتلي ({MAX_QUEUE} طلب)، جرّب بعد شوية."}, ctx.author))
        return
    in_queue = queue_count > 0 and semaphore.locked()
    if in_queue:
        queue_msg = await ctx.reply(embed=build_queue_embed(queue_count + 1, ctx.author))
    async with ctx.typing():
        data = await handle_request(server.lower(), game_name, hashtag)
    if in_queue:
        await queue_msg.edit(embed=build_embed(data, ctx.author))
    else:
        await ctx.reply(embed=build_embed(data, ctx.author))


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
