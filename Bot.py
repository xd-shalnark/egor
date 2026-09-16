import os
import re
import time
import logging
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web  
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("egor-kreed-bot")

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "Не найден DISCORD_TOKEN. Скопируй .env.example в .env и вставь туда токен."
    )

KEYWORDS_FILE = Path(__file__).parent / "keywords.txt"

COOLDOWN_SECONDS = 30

intents = discord.Intents.default()
intents.message_content = True  

bot = commands.Bot(command_prefix="!", intents=intents)

last_warned: dict[int, float] = {}

keyword_pattern: re.Pattern | None = None


def load_keywords() -> list[str]:
    """Читает keywords.txt и возвращает список слов/фраз (без пустых строк)."""
    if not KEYWORDS_FILE.exists():
        log.warning("Файл %s не найден, создаю пустой.", KEYWORDS_FILE)
        KEYWORDS_FILE.write_text("", encoding="utf-8")
        return []

    lines = KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
    words = [line.strip() for line in lines if line.strip()]
    return words


def build_pattern(words: list[str]) -> re.Pattern | None:
    """
    Собирает единый regex из списка слов/фраз.
    Использует границы слов (\\b), чтобы "крид" не сработал внутри
    случайного другого слова, и re.IGNORECASE для регистронезависимости.
    """
    if not words:
        return None

    escaped = sorted((re.escape(w) for w in words), key=len, reverse=True)
    pattern_str = r"\b(" + "|".join(escaped) + r")\b"
    return re.compile(pattern_str, re.IGNORECASE)


def reload_keywords() -> int:
    """Перечитывает файл и пересобирает regex. Возвращает количество слов."""
    global keyword_pattern
    words = load_keywords()
    keyword_pattern = build_pattern(words)
    log.info("Загружено %d ключевых слов.", len(words))
    return len(words)


async def handle_health(request):
    return web.Response(text="OK")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("Health-check сервер запущен на порту %s", port)

@bot.event
async def on_ready():
    reload_keywords()
    log.info("Бот запущен как %s (id: %s)", bot.user, bot.user.id)
    await start_health_server()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if keyword_pattern is None:
        return

    content = message.content
    if not keyword_pattern.search(content):
        return

    user_id = message.author.id
    now = time.time()
    last_time = last_warned.get(user_id, 0)

    if now - last_time < COOLDOWN_SECONDS:
        return  

    last_warned[user_id] = now

    try:
        await message.channel.send(
            f"⚠️ {message.author.mention}, тут про Крида ни слова! Ты предупреждён."
        )
    except discord.Forbidden:
        log.warning("Нет прав отправить сообщение в канал %s", message.channel.id)

@bot.command(name="reload")
@commands.has_permissions(manage_messages=True)
async def reload_cmd(ctx: commands.Context):
    """Перезагружает список слов из keywords.txt без перезапуска бота."""
    count = reload_keywords()
    await ctx.send(f"✅ Список слов обновлён, слов в списке: {count}")


@bot.command(name="addword")
@commands.has_permissions(manage_messages=True)
async def addword_cmd(ctx: commands.Context, *, word: str):
    """Добавляет новое слово/фразу в keywords.txt и сразу применяет."""
    words = load_keywords()
    if word.lower() in (w.lower() for w in words):
        await ctx.send(f"Слово «{word}» уже есть в списке.")
        return

    with KEYWORDS_FILE.open("a", encoding="utf-8") as f:
        f.write(word + "\n")

    reload_keywords()
    await ctx.send(f"✅ Добавил «{word}» в список.")


@bot.command(name="delword")
@commands.has_permissions(manage_messages=True)
async def delword_cmd(ctx: commands.Context, *, word: str):
    """Удаляет слово/фразу из keywords.txt."""
    words = load_keywords()
    new_words = [w for w in words if w.lower() != word.lower()]

    if len(new_words) == len(words):
        await ctx.send(f"Слово «{word}» не найдено в списке.")
        return

    KEYWORDS_FILE.write_text("\n".join(new_words) + "\n", encoding="utf-8")
    reload_keywords()
    await ctx.send(f"✅ Удалил «{word}» из списка.")


@bot.command(name="wordlist")
async def wordlist_cmd(ctx: commands.Context):
    """Показывает текущий список отслеживаемых слов."""
    words = load_keywords()
    if not words:
        await ctx.send("Список слов пуст.")
        return
    await ctx.send("Отслеживаемые слова:\n" + ", ".join(words))


if __name__ == "__main__": 
    bot.run(TOKEN)