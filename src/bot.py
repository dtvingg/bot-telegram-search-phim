import logging
from pathlib import Path

import yaml
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

BOT_TOKEN  = config["telegram"]["bot_token"]
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
    "completed":  "✅ Hoàn thành",
    "ongoing":    "🔄 Đang chiếu",
    "trailer":    "🎞 Trailer",
}
TYPE_MAP = {
    "single":  "🎬 Phim lẻ",
    "series":  "📺 Phim bộ",
    "hoathinh": "🎨 Hoạt hình",
    "tvshows":  "📡 TV Shows",
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_donate_text() -> str:
    bank     = DONATE_CFG.get("bank_name", "")
    acc_num  = DONATE_CFG.get("account_number", "")
    acc_name = DONATE_CFG.get("account_name", "")
    msg      = DONATE_CFG.get("message", "Cảm ơn bạn đã ủng hộ!")
    return (
        "☕ *Ủng hộ Bot Xem Phim*\n\n"
        "Nếu bot hữu ích với bạn, hãy ủng hộ mình một ly cà phê nhé! 😊\n\n"
        f"🏦 *Ngân hàng:* {bank}\n"
        f"💳 *Số tài khoản:* `{acc_num}`\n"
        f"👤 *Chủ tài khoản:* {acc_name}\n\n"
        f"_{msg}_"
    )


def get_qr_path():
    qr_rel = DONATE_CFG.get("qr_image_path", "")
    if not qr_rel:
        return None
    p = Path(__file__).parent / qr_rel
    return p if p.exists() else None


def fmt_list(items: list, limit: int = 3) -> str:
    """Hiển thị list, tối đa `limit` phần tử."""
    if not items:
        return ""
    shown = items[:limit]
    text  = ", ".join(shown)
    if len(items) > limit:
        text += f" _+{len(items) - limit} người_"
    return text


def build_movie_message(movie: dict, index: int) -> tuple[str, InlineKeyboardMarkup | None]:
    """Tạo tin nhắn + keyboard cho 1 bộ phim."""

    name        = movie.get("name", "Không rõ")
    origin_name = movie.get("origin_name", "")

    # ── Tiêu đề ───────────────────────────────────────────────────────────────
    lines = [f"🎬 *{name}*"]
    if origin_name and origin_name.lower() != name.lower():
        lines.append(f"📝 _{origin_name}_")

    lines.append("")  # dòng trống

    # ── Hàng thông tin nhanh ──────────────────────────────────────────────────
    year    = movie.get("year")
    quality = movie.get("quality")
    lang    = movie.get("lang")
    time_   = movie.get("time")
    status  = STATUS_MAP.get(movie.get("status", ""), "")
    type_   = TYPE_MAP.get(movie.get("type", ""), "")

    if year:      lines.append(f"📅 *Năm:* {year}")
    if type_:     lines.append(f"{type_}")
    if status:    lines.append(f"{status}")
    if quality:   lines.append(f"🎞 *Chất lượng:* {quality}")
    if lang:      lines.append(f"🗣 *Ngôn ngữ:* {lang}")
    if time_:     lines.append(f"⏱ *Thời lượng:* {time_}")

    # Số tập
    ep_current = movie.get("episode_current", "")
    ep_total   = movie.get("episode_total", "")
    ep_count   = len(movie.get("episodes", []))
    if ep_current or ep_total:
        ep_info = ep_current
        if ep_total and ep_total != "1":
            ep_info += f"/{ep_total} tập"
        lines.append(f"📺 *Tập:* {ep_info} ({ep_count} link)")

    # Lượt xem
    view = movie.get("view", 0)
    if view:
        lines.append(f"👁 *Lượt xem:* {view:,}")

    # ── Rating ────────────────────────────────────────────────────────────────
    rating  = movie.get("rating")
    imdb_id = movie.get("imdb_id")
    if rating:
        stars = "⭐" * min(5, round(rating / 2))
        imdb_link = f"[IMDB](https://www.imdb.com/title/{imdb_id})" if imdb_id else "IMDB"
        lines.append(f"⭐ *Đánh giá:* {rating}/10 {stars}")

    # ── Thể loại & Quốc gia ───────────────────────────────────────────────────
    categories = movie.get("categories", [])
    countries  = movie.get("countries", [])
    if categories: lines.append(f"🎭 *Thể loại:* {', '.join(categories)}")
    if countries:  lines.append(f"🌍 *Quốc gia:* {', '.join(countries)}")

    # ── Đạo diễn & Diễn viên ─────────────────────────────────────────────────
    directors = movie.get("directors", [])
    actors    = movie.get("actors", [])
    if directors: lines.append(f"🎥 *Đạo diễn:* {fmt_list(directors)}")
    if actors:    lines.append(f"🎭 *Diễn viên:* {fmt_list(actors, limit=4)}")

    # ── Mô tả ─────────────────────────────────────────────────────────────────
    description = movie.get("description", "")
    if description:
        clean = (
            description
            .replace("<br>", "\n").replace("<br/>", "\n")
            .replace("<p>", "").replace("</p>", " ")
            .strip()
        )
        short = clean[:350] + ("..." if len(clean) > 350 else "")
        lines.append(f"\n📖 _{short}_")

    text = "\n".join(lines)

    # ── Keyboard: tối đa 10 tập đầu ──────────────────────────────────────────
    episodes = movie.get("episodes", [])
    buttons  = []
    for i, ep in enumerate(episodes[:10]):
        # label = ep.get("filename") or f"Tập {i + 1}"
        label = f"Tập {ep.get('name')} - {ep.get('server_name')}"
        link  = ep.get("link")
        if link:
            buttons.append(InlineKeyboardButton(f"▶️ {label}", url=link))

    rows = [buttons[i:i + 1] for i in range(0, len(buttons), 1)]

    remaining = len(episodes) - 10
    if remaining > 0:
        rows.append([
            InlineKeyboardButton(
                f"📋 Xem thêm {remaining} tập còn lại",
                callback_data=f"more_{index}",
            )
        ])

    markup = InlineKeyboardMarkup(rows) if rows else None
    return text, markup


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "👋 *Chào mừng bạn đến với Bot Xem Phim!* 🎬\n\n"
        "🔍 Tìm phim nhanh với lệnh:\n"
        "`/search <tên phim>`\n\n"
        "Ví dụ:\n"
        "`/search Doraemon`\n"
        "`/search Avengers`\n\n"
        "📌 *Các lệnh:*\n"
        "/search  — Tìm kiếm phim 🔍\n"
        "/history — Lịch sử tìm kiếm 📋\n"
        "/donate  — Ủng hộ tác giả ☕\n"
        "/help    — Hướng dẫn chi tiết"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

    # # Tự động hiện donate kèm QR ngay sau welcome
    # qr_path    = get_qr_path()
    # donate_text = get_donate_text()
    # if qr_path:
    #     with open(qr_path, "rb") as f:
    #         await update.message.reply_photo(
    #             photo=f,
    #             caption=donate_text,
    #             parse_mode="Markdown",
    #         )
    # else:
    #     await update.message.reply_text(donate_text, parse_mode="Markdown")


async def donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qr_path    = get_qr_path()
    donate_text = get_donate_text()
    if qr_path:
        with open(qr_path, "rb") as f:
            await update.message.reply_photo(
                photo=f,
                caption=donate_text,
                parse_mode="Markdown",
            )
    else:
        await update.message.reply_text(
            donate_text + "\n\n⚠️ _Ảnh QR chưa được cấu hình._",
            parse_mode="Markdown",
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
        "_(VLC, IINA, trình duyệt + HLS Player extension,...)_\n\n"
        "☕ Thích bot? Dùng `/donate` để ủng hộ tác giả!\n\n"
        "📋 Xem lại những phim đã tìm: `/history`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ Vui lòng nhập tên phim sau lệnh.\n\nVí dụ: `/search Doraemon`",
            parse_mode="Markdown",
        )
        return

    query   = " ".join(context.args).strip()
    waiting = await update.message.reply_text(
        f"🔍 Đang tìm kiếm: *{query}*...",
        parse_mode="Markdown",
    )

    results = service.run(query)
    await waiting.delete()

    if not results:
        await update.message.reply_text(
            f"😕 Không tìm thấy phim nào cho: *{query}*\n\nThử từ khóa khác nhé!",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(
        f"✅ Tìm thấy *{len(results)}* kết quả cho: _{query}_",
        parse_mode="Markdown",
    )

    context.user_data["last_results"] = results

    # Lưu lịch sử
    user = update.effective_user
    history.add(
        user_id=user.id,
        username=user.username or user.full_name or "",
        query=query,
        results_count=len(results),
    )

    for i, movie in enumerate(results):
        text, markup = build_movie_message(movie, i)
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=False,  # Cho phép preview link IMDB
        )


async def more_episodes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()

    index   = int(query.data.split("_")[1])
    results = context.user_data.get("last_results", [])

    if index >= len(results):
        await query.message.reply_text("⚠️ Không tìm thấy dữ liệu. Hãy tìm lại.")
        return

    episodes = results[index].get("episodes", [])[10:]
    if not episodes:
        await query.message.reply_text("Không có tập nào thêm.")
        return

    buttons = []
    for i, ep in enumerate(episodes):
        # label = ep.get("filename") or f"Tập {10 + i + 1}"
        label = f"Tập {ep.get('name')} - {ep.get('server_name')}"
        link  = ep.get("link")
        if link:
            buttons.append(InlineKeyboardButton(f"▶️ {label}", url=link))

    rows       = [buttons[i:i + 1] for i in range(0, len(buttons), 1)]
    movie_name = results[index].get("name", "")

    await query.message.reply_text(
        f"📺 *{movie_name}* — Các tập còn lại ({len(episodes)} tập):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/history — Hiển thị lịch sử tìm kiếm của user."""
    user    = update.effective_user
    records = history.get(user.id, limit=10)
    stats   = history.stats(user.id)

    if not records:
        await update.message.reply_text(
            "📋 Bạn chưa có lịch sử tìm kiếm nào.\n\nDùng `/search <tên phim>` để bắt đầu!",
            parse_mode="Markdown",
        )
        return

    # Header thống kê
    lines = [
        "📋 *Lịch sử tìm kiếm của bạn*",
        f"🔢 Tổng: *{stats['total']}* lượt tìm",
        "",
    ]

    # Danh sách 10 lượt gần nhất
    for i, rec in enumerate(records, 1):
        found = f"✅ {rec['results_count']} phim" if rec["results_count"] else "😕 Không tìm thấy"
        safe_query = rec["query"].replace("`", "'").replace("*", "").replace("_", "")
        lines.append(f"{i}. `{safe_query}` — {found}")
        lines.append(f"    🕐 {rec['timestamp']}")

    # Top từ khoá
    if stats.get("top_queries"):
        lines.append("")
        lines.append("🔥 *Tìm nhiều nhất:*")
        safe_tops = [q.replace("`", "'").replace("*", "").replace("_", "") for q in stats["top_queries"]]
        lines.append(", ".join(f"`{q}`" for q in safe_tops))

    lines.append("")
    # lines.append("_Dùng /clearhistory để xoá lịch sử_")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
    )


async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/clearhistory — Xoá toàn bộ lịch sử tìm kiếm."""
    user = update.effective_user

    # Hỏi xác nhận qua inline button
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Xác nhận xoá", callback_data="confirm_clear_history"),
        InlineKeyboardButton("❌ Huỷ",          callback_data="cancel_clear_history"),
    ]])
    await update.message.reply_text(
        "⚠️ Bạn có chắc muốn xoá toàn bộ lịch sử tìm kiếm không?",
        reply_markup=markup,
    )


async def clear_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý xác nhận / huỷ xoá lịch sử."""
    query = update.callback_query
    await query.answer()
    user  = update.effective_user

    if query.data == "confirm_clear_history":
        history.clear(user.id)
        await query.edit_message_text("✅ Đã xoá toàn bộ lịch sử tìm kiếm của bạn.")
    else:
        await query.edit_message_text("❌ Đã huỷ. Lịch sử của bạn vẫn được giữ nguyên.")


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
    app.add_handler(CallbackQueryHandler(more_episodes_callback,  pattern=r"^more_\d+$"))
    app.add_handler(CallbackQueryHandler(clear_history_callback,  pattern=r"^(confirm|cancel)_clear_history$"))

    logger.info("🤖 Bot đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()