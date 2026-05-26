import asyncio
import logging
import os
import re
from pathlib import Path

import yaml
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from src.service_search_phim import ServiceSearchPhim
from src.history_manager import HistoryManager

# ─── Load config ──────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# BOT_TOKEN: ưu tiên biến môi trường, fallback sang config.yaml
BOT_TOKEN  = os.environ.get("BOT_TOKEN") or config["telegram"].get("bot_token", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN chưa được đặt. Dùng biến môi trường BOT_TOKEN hoặc config.yaml.")

MAX_SLUGS  = config["search"].get("max_slugs", 3)
TIMEOUT    = config["search"].get("timeout", 10)
DONATE_CFG = config.get("donate", {})

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Service ──────────────────────────────────────────────────────────────────
service = ServiceSearchPhim(timeout=TIMEOUT, max_slugs=MAX_SLUGS)
history = HistoryManager(
    file_path=config.get("history", {}).get("file_path", "data/history.json"),
    max_per_user=config.get("history", {}).get("max_per_user", 50),
)

# ─── Constants ────────────────────────────────────────────────────────────────
STATUS_MAP = {
    "completed": "✅ Hoàn thành",
    "ongoing":   "🔄 Đang chiếu",
    "trailer":   "🎞 Trailer",
}
TYPE_MAP = {
    "single":   "🎬 Phim lẻ",
    "series":   "📺 Phim bộ",
    "hoathinh": "🎨 Hoạt hình",
    "tvshows":  "📡 TV Shows",
}

EP_PAGE_SIZE = 10  # số tập mỗi trang (kể cả trang đầu trong message phim)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def esc(text) -> str:
    """Escape ký tự đặc biệt cho MarkdownV2."""
    if text is None:
        return ""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', str(text))


def get_donate_text() -> str:
    bank     = DONATE_CFG.get("bank_name", "")
    acc_num  = DONATE_CFG.get("account_number", "")
    acc_name = DONATE_CFG.get("account_name", "")
    msg      = DONATE_CFG.get("message", "Cảm ơn bạn đã ủng hộ!")
    return (
        "☕ *Ủng hộ Bot Xem Phim*\n\n"
        "Nếu bot hữu ích với bạn, hãy ủng hộ mình một ly cà phê nhé\\! 😊\n\n"
        f"🏦 *Ngân hàng:* {esc(bank)}\n"
        f"💳 *Số tài khoản:* `{esc(acc_num)}`\n"
        f"👤 *Chủ tài khoản:* {esc(acc_name)}\n\n"
        f"_{esc(msg)}_"
    )


def get_qr_path():
    qr_rel = DONATE_CFG.get("qr_image_path", "")
    if not qr_rel:
        return None
    p = Path(__file__).parent / qr_rel
    return p if p.exists() else None


def fmt_list(items: list, limit: int = 3) -> str:
    if not items:
        return ""
    shown = [esc(x) for x in items[:limit]]
    text  = ", ".join(shown)
    if len(items) > limit:
        text += f" _\\+{len(items) - limit}_"
    return text


def build_movie_message(movie: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    name        = movie.get("name", "Không rõ")
    origin_name = movie.get("origin_name", "")

    lines = [f"🎬 *{esc(name)}*"]
    if origin_name and origin_name.lower() != name.lower():
        lines.append(f"📝 _{esc(origin_name)}_")

    lines.append("")

    year    = movie.get("year")
    quality = movie.get("quality")
    lang    = movie.get("lang")
    time_   = movie.get("time")
    status  = STATUS_MAP.get(movie.get("status", ""), "")
    type_   = TYPE_MAP.get(movie.get("type", ""), "")

    if year:    lines.append(f"📅 *Năm:* {esc(year)}")
    if type_:   lines.append(type_)
    if status:  lines.append(status)
    if quality: lines.append(f"🎞 *Chất lượng:* {esc(quality)}")
    if lang:    lines.append(f"🗣 *Ngôn ngữ:* {esc(lang)}")
    if time_:   lines.append(f"⏱ *Thời lượng:* {esc(time_)}")

    ep_current = movie.get("episode_current", "")
    ep_total   = movie.get("episode_total", "")
    ep_count   = len(movie.get("episodes", []))
    if ep_current or ep_total:
        ep_info = esc(ep_current)
        if ep_total and ep_total != "1":
            ep_info += f"/{esc(ep_total)} tập"
        lines.append(f"📺 *Tập:* {ep_info} \\({ep_count} link\\)")

    view = movie.get("view", 0)
    if view:
        lines.append(f"👁 *Lượt xem:* {view:,}".replace(",", "\\."))

    rating  = movie.get("rating")
    imdb_id = movie.get("imdb_id")
    if rating:
        stars = "⭐" * min(5, round(rating / 2))
        lines.append(f"⭐ *Đánh giá:* {esc(rating)}/10 {stars}")
        if imdb_id:
            lines.append(f"[Xem trên IMDB](https://www.imdb.com/title/{imdb_id})")

    categories = movie.get("categories", [])
    countries  = movie.get("countries", [])
    if categories: lines.append(f"🎭 *Thể loại:* {', '.join(esc(c) for c in categories)}")
    if countries:  lines.append(f"🌍 *Quốc gia:* {', '.join(esc(c) for c in countries)}")

    directors = movie.get("directors", [])
    actors    = movie.get("actors", [])
    if directors: lines.append(f"🎥 *Đạo diễn:* {fmt_list(directors)}")
    if actors:    lines.append(f"🎭 *Diễn viên:* {fmt_list(actors, limit=4)}")

    description = movie.get("description", "")
    if description:
        clean = (
            description
            .replace("<br>", "\n").replace("<br/>", "\n")
            .replace("<p>", "").replace("</p>", " ")
            .strip()
        )
        short = clean[:350] + ("..." if len(clean) > 350 else "")
        lines.append(f"\n📖 _{esc(short)}_")

    text = "\n".join(lines)

    # Keyboard: trang đầu (EP_PAGE_SIZE tập)
    episodes = movie.get("episodes", [])
    slug     = movie.get("slug", "")
    total    = len(episodes)

    buttons = []
    for ep in episodes[:EP_PAGE_SIZE]:
        label = f"Tập {ep.get('name')} - {ep.get('server_name')}"
        link  = ep.get("link")
        if link:
            buttons.append(InlineKeyboardButton(f"▶️ {label}", url=link))

    rows = [[btn] for btn in buttons]

    if total > EP_PAGE_SIZE and slug:
        ep_to = min(EP_PAGE_SIZE * 2, total)
        rows.append([
            InlineKeyboardButton(
                f"Trang tiếp ▶▶  ({EP_PAGE_SIZE + 1}–{ep_to} / {total} tập)",
                callback_data=f"ep_{slug}_{EP_PAGE_SIZE}",
            )
        ])

    markup = InlineKeyboardMarkup(rows) if rows else None
    return text, markup


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "👋 *Chào mừng bạn đến với Bot Xem Phim\\!* 🎬\n\n"
        "🔍 Tìm phim nhanh với lệnh:\n"
        "`/search <tên phim>`\n\n"
        "Ví dụ:\n"
        "`/search Doraemon`\n"
        "`/search Avengers`\n\n"
        "📌 *Các lệnh:*\n"
        "/search       — Tìm kiếm phim 🔍\n"
        "/history      — Lịch sử tìm kiếm 📋\n"
        "/clearhistory — Xoá lịch sử 🗑\n"
        "/donate       — Ủng hộ tác giả ☕\n"
        "/help         — Hướng dẫn chi tiết"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN_V2)


async def donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qr_path     = get_qr_path()
    donate_text = get_donate_text()
    if qr_path:
        with open(qr_path, "rb") as f:
            await update.message.reply_photo(
                photo=f,
                caption=donate_text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    else:
        await update.message.reply_text(
            donate_text + "\n\n⚠️ _Ảnh QR chưa được cấu hình\\._",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *Hướng dẫn sử dụng:*\n\n"
        "1️⃣ Dùng `/search <tên phim>` để tìm\n"
        "    Ví dụ: `/search Naruto`\n\n"
        "2️⃣ Bot trả về thông tin chi tiết từng phim:\n"
        "    năm · chất lượng · ngôn ngữ · rating\n"
        "    đạo diễn · diễn viên · thể loại · mô tả\n\n"
        "3️⃣ Nhấn nút ▶️ để phát tập phim qua link m3u8\n\n"
        "⚠️ *Lưu ý:* Link m3u8 cần trình phát hỗ trợ HLS\n"
        "_\\(VLC, IINA, trình duyệt \\+ HLS Player extension,\\.\\.\\.\\)_\n\n"
        "📋 Lịch sử tìm kiếm: `/history`\n"
        "🗑 Xoá lịch sử: `/clearhistory`\n"
        "☕ Thích bot? Dùng `/donate` để ủng hộ tác giả\\!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ Vui lòng nhập tên phim sau lệnh\\.\n\nVí dụ: `/search Doraemon`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    query   = " ".join(context.args).strip()
    waiting = await update.message.reply_text(
        f"🔍 Đang tìm kiếm: *{esc(query)}*\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    try:
        # Chạy trong thread pool để không block event loop
        results = await asyncio.to_thread(service.run, query)
    except Exception as e:
        logger.exception("Lỗi khi tìm kiếm '%s': %s", query, e)
        await waiting.delete()
        await update.message.reply_text(
            "❌ Đã xảy ra lỗi khi tìm kiếm\\. Vui lòng thử lại sau\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    await waiting.delete()

    if not results:
        await update.message.reply_text(
            f"😕 Không tìm thấy phim nào cho: *{esc(query)}*\n\nThử từ khóa khác nhé\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    await update.message.reply_text(
        f"✅ Tìm thấy *{len(results)}* kết quả cho: _{esc(query)}_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    user = update.effective_user
    history.add(
        user_id=user.id,
        username=user.username or user.full_name or "",
        query=query,
        results_count=len(results),
    )

    for movie in results:
        text, markup = build_movie_message(movie)
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=markup,
            disable_web_page_preview=True,
        )


async def episodes_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Phân trang tập phim. callback_data = ep_{slug}_{offset}"""
    query = update.callback_query
    await query.answer()

    # Dùng regex để tách slug (có thể chứa dấu gạch ngang) và offset
    m = re.match(r'^ep_(.+)_(\d+)$', query.data)
    if not m:
        return
    slug   = m.group(1)
    offset = int(m.group(2))

    try:
        movie = await asyncio.to_thread(service.get_detail, slug)
    except Exception as e:
        logger.exception("Lỗi khi lấy chi tiết '%s': %s", slug, e)
        await query.message.reply_text("❌ Lỗi khi tải dữ liệu\\. Thử lại sau\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    if not movie:
        await query.message.reply_text("⚠️ Không tìm thấy dữ liệu phim\\. Hãy tìm lại\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    all_episodes = movie.get("episodes", [])
    total        = len(all_episodes)
    page_eps     = all_episodes[offset : offset + EP_PAGE_SIZE]

    if not page_eps:
        await query.message.reply_text("Không có tập nào ở trang này\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    movie_name = movie.get("name", "")
    ep_from    = offset + 1
    ep_to      = min(offset + EP_PAGE_SIZE, total)
    page_num   = offset // EP_PAGE_SIZE + 1

    buttons = []
    for ep in page_eps:
        label = f"Tập {ep.get('name')} - {ep.get('server_name')}"
        link  = ep.get("link")
        if link:
            buttons.append(InlineKeyboardButton(f"▶️ {label}", url=link))

    rows = [[btn] for btn in buttons]

    # Nút điều hướng: prev chỉ hiện khi trang trước không phải trang 1 (đã có trong message gốc)
    nav = []
    if offset > EP_PAGE_SIZE:
        prev = offset - EP_PAGE_SIZE
        nav.append(InlineKeyboardButton(f"◀◀ {prev + 1}–{prev + EP_PAGE_SIZE}", callback_data=f"ep_{slug}_{prev}"))
    if offset + EP_PAGE_SIZE < total:
        nxt    = offset + EP_PAGE_SIZE
        nxt_to = min(nxt + EP_PAGE_SIZE, total)
        nav.append(InlineKeyboardButton(f"{nxt + 1}–{nxt_to} ▶▶", callback_data=f"ep_{slug}_{nxt}"))
    if nav:
        rows.append(nav)

    await query.message.reply_text(
        f"📺 *{esc(movie_name)}* — Trang {page_num} \\({ep_from}–{ep_to} / {total} tập\\):",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user              = update.effective_user
    records, stats    = history.get_with_stats(user.id, limit=10)

    if not records:
        await update.message.reply_text(
            "📋 Bạn chưa có lịch sử tìm kiếm nào\\.\n\nDùng `/search <tên phim>` để bắt đầu\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    lines = [
        "📋 *Lịch sử tìm kiếm của bạn*",
        f"🔢 Tổng: *{stats['total']}* lượt tìm",
        "",
    ]

    for i, rec in enumerate(records, 1):
        found      = f"✅ {rec['results_count']} phim" if rec["results_count"] else "😕 Không tìm thấy"
        safe_query = esc(rec["query"])
        lines.append(f"{i}\\. `{safe_query}` — {found}")
        lines.append(f"    🕐 {esc(rec['timestamp'])}")

    if stats.get("top_queries"):
        lines.append("")
        lines.append("🔥 *Tìm nhiều nhất:*")
        lines.append(", ".join(f"`{esc(q)}`" for q in stats["top_queries"]))

    lines.append("")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Xác nhận xoá", callback_data="confirm_clear_history"),
        InlineKeyboardButton("❌ Huỷ",          callback_data="cancel_clear_history"),
    ]])
    await update.message.reply_text(
        "⚠️ Bạn có chắc muốn xoá toàn bộ lịch sử tìm kiếm không?",
        reply_markup=markup,
    )


async def clear_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user  = update.effective_user

    if query.data == "confirm_clear_history":
        history.clear(user.id)
        await query.edit_message_text("✅ Đã xoá toàn bộ lịch sử tìm kiếm của bạn\\.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text("❌ Đã huỷ\\. Lịch sử của bạn vẫn được giữ nguyên\\.", parse_mode=ParseMode.MARKDOWN_V2)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("donate",       donate))
    app.add_handler(CommandHandler("help",         help_command))
    app.add_handler(CommandHandler("search",       search_movie))
    app.add_handler(CommandHandler("history",      history_command))
    app.add_handler(CommandHandler("clearhistory", clear_history_command))
    app.add_handler(CallbackQueryHandler(episodes_page_callback,  pattern=r"^ep_.+_\d+$"))
    app.add_handler(CallbackQueryHandler(clear_history_callback,  pattern=r"^(confirm|cancel)_clear_history$"))

    logger.info("🤖 Bot đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
