"""
بوت تيليجرام لتحميل مقاطع تيك توك (بدون علامة مائية)، يوتيوب، والانستغرام.

الفكرة:
- المستخدم يرسل رابط تيك توك أو يوتيوب أو انستغرام للبوت.
- البوت يستخدم مكتبة yt-dlp لتحميل الفيديو/الصور/Reels (النسخة الأصلية بدون شعار).
- البوت يرسل المحتوى للمستخدم مباشرة داخل تيليجرام.

قبل التشغيل:
1. ثبّت المتطلبات:
   pip install -r requirements.txt
2. تأكد إن ffmpeg مثبت على جهازك (مطلوب لدمج الصوت والفيديو أحيانًا).
3. احصل على توكن البوت من @BotFather في تيليجرام.
4. ضع التوكن في متغير البيئة BOT_TOKEN (لا تكتبه أبدًا مباشرة هنا بالكود).
5. شغّل الملف: python bot.py
"""

import os
import re
import logging
import tempfile
import shutil
from pathlib import Path

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------------------

# ⚠️ التوكن يُقرأ حصريًا من متغير البيئة BOT_TOKEN — لا تكتبه أبدًا هنا مباشرة
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "8675217264")

MAX_FILE_SIZE_MB = 50

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

users_awaiting_support = set()
pending_downloads = {}

TIKTOK_URL_REGEX = re.compile(
    r"(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/\S+", re.IGNORECASE
)

YOUTUBE_URL_REGEX = re.compile(
    r"(https?://)?(www\.|m\.)?(youtube\.com/\S+|youtu\.be/\S+)", re.IGNORECASE
)

INSTAGRAM_URL_REGEX = re.compile(
    r"(https?://)?(www\.)?instagram\.com/[^\s?]+", re.IGNORECASE
)

PINTEREST_URL_REGEX = re.compile(
    r"(https?://)?(www\.)?pinterest\.com/[^\s?]+", re.IGNORECASE
)


def extract_supported_url(text: str) -> "tuple[str, str] | tuple[None, None]":
    pinterest_match = PINTEREST_URL_REGEX.search(text)
    if pinterest_match:
        return pinterest_match.group(0), "pinterest"

    instagram_match = INSTAGRAM_URL_REGEX.search(text)
    if instagram_match:
        return instagram_match.group(0), "instagram"

    tiktok_match = TIKTOK_URL_REGEX.search(text)
    if tiktok_match:
        return tiktok_match.group(0), "tiktok"

    youtube_match = YOUTUBE_URL_REGEX.search(text)
    if youtube_match:
        return youtube_match.group(0), "youtube"

    return None, None


def download_video(url: str, download_dir: str, audio_only: bool = False, platform: str = "unknown"):
    output_template = os.path.join(download_dir, "%(id)s.%(ext)s")

    if audio_only:
        ydl_opts = {
            "outtmpl": output_template,
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                }
            },
        }
    else:
        if platform in ["instagram", "pinterest"]:
            ydl_opts = {
                "outtmpl": output_template,
                "format": "best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": False,
                "writeinfojson": False,
            }
        else:
            ydl_opts = {
                "outtmpl": output_template,
                "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "merge_output_format": "mp4",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"],
                    }
                },
            }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if isinstance(info, dict):
            if "entries" in info and info["entries"]:
                filepaths = []
                for entry in info["entries"]:
                    filepath = ydl.prepare_filename(entry)
                    if audio_only:
                        base, _ = os.path.splitext(filepath)
                        filepath = base + ".mp3"
                    filepaths.append(filepath)
                return filepaths if len(filepaths) > 1 else filepaths[0]
            else:
                filepath = ydl.prepare_filename(info)
                if audio_only:
                    base, _ = os.path.splitext(filepath)
                    filepath = base + ".mp3"
                return filepath
        else:
            filepath = ydl.prepare_filename(info)
            if audio_only:
                base, _ = os.path.splitext(filepath)
                filepath = base + ".mp3"
            return filepath


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك. 👋\n\n"
        "أرسل رابط مقطع من تيك توك أو يوتيوب أو انستغرام أو بنترست وسيتم تحميله لك بأعلى جودة متاحة.\n\n"
        "أمثلة:\n"
        "https://www.tiktok.com/@username/video/1234567890\n"
        "https://www.youtube.com/watch?v=xxxxxxxxxxx\n"
        "https://www.instagram.com/p/xxxxxxxxxxx\n"
        "https://www.pinterest.com/pin/xxxxxxxxxxx\n\n"
        "لمعرفة إمكانيات البوت: /about\n"
        "للدعم الفني: /support"
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 نبذة عن البوت\n\n"
        "هذا البوت مخصص لتحميل المقاطع من المنصات التالية:\n\n"
        "• تيك توك — بدون علامة مائية\n"
        "• يوتيوب\n"
        "• انستغرام (صور، فيديوهات، Reels، Stories)\n"
        "• بنترست (صور، فيديوهات)\n\n"
        "المميزات:\n"
        "— جودة مطابقة للنسخة الأصلية دون أي ضغط أو تعديل إضافي\n"
        "— بدون علامات مائية إضافية من البوت نفسه\n"
        "— خيار تحميل الصوت فقط (MP3)\n"
        "— تحميل عدة صور من Carousel\n"
        "— معالجة مباشرة وسريعة\n\n"
        "الأوامر المتاحة:\n"
        "/start — رسالة البداية\n"
        "/help — طريقة الاستخدام\n"
        "/about — هذه الرسالة\n"
        "/support — التواصل مع الدعم الفني"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔹 طريقة الاستخدام\n\n"
        "1. انسخ رابط مقطع من تيك توك أو يوتيوب أو انستغرام أو بنترست\n"
        "2. أرسله في هذه المحادثة\n"
        "3. انتظر قليلاً وسيتم إرسال المحتوى بأعلى جودة متاحة\n\n"
        "الأوامر المتاحة:\n"
        "/start — رسالة البداية\n"
        "/about — إمكانيات البوت\n"
        "/help — هذه الرسالة\n"
        "/support — التواصل مع الدعم الفني"
    )


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_awaiting_support.add(update.effective_user.id)
    await update.message.reply_text(
        "🛠️ الدعم الفني\n\n"
        "يرجى وصف المشكلة أو الاستفسار في رسالة واحدة، "
        "وستصل مباشرة إلى فريق الدعم للمتابعة."
    )


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    replied_message = update.message.reply_to_message
    if not replied_message or not replied_message.text:
        return

    match = re.search(r"معرف المستخدم:\s*(\d+)", replied_message.text)
    if not match:
        return

    target_user_id = int(match.group(1))
    reply_text = update.message.text or ""

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 رد من فريق الدعم:\n\n{reply_text}",
        )
        await update.message.reply_text("✅ تم إرسال الرد للمستخدم.")
    except Exception:
        logger.exception("فشل إرسال رد الأدمن للمستخدم")
        await update.message.reply_text(
            "❌ تعذّر إرسال الرد. قد يكون المستخدم حظر البوت أو حذف المحادثة."
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    user = update.effective_user

    if (
        str(user.id) == str(ADMIN_CHAT_ID)
        and update.message.reply_to_message is not None
    ):
        await handle_admin_reply(update, context)
        return

    if user.id in users_awaiting_support:
        users_awaiting_support.discard(user.id)

        username_display = f"@{user.username}" if user.username else "بدون يوزرنيم"
        forward_text = (
            f"📩 رسالة دعم جديدة\n\n"
            f"من: {user.full_name} ({username_display})\n"
            f"معرف المستخدم: {user.id}\n\n"
            f"الرسالة:\n{text}\n\n"
            f"↩️ للرد: اعمل Reply على هذه الرسالة واكتب ردك مباشرة"
        )

        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=forward_text)
            await update.message.reply_text(
                "✅ تم إرسال رسالتك لفريق الدعم، سيتم التواصل معك في أقرب وقت."
            )
        except Exception:
            logger.exception("فشل توجيه رسالة الدعم")
            await update.message.reply_text(
                "❌ حدث خطأ أثناء إرسال رسالتك، حاول مرة أخرى لاحقًا."
            )
        return

    url, platform = extract_supported_url(text)

    if not url:
        await update.message.reply_text(
            "ما لقيت رابط مدعوم في رسالتك. أرسل رابط من تيك توك أو يوتيوب أو انستغرام أو بنترست."
        )
        return

    pending_downloads[user.id] = (url, platform)

    if platform in ["instagram", "pinterest"]:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📥 تحميل", callback_data="download_video"),
                    InlineKeyboardButton("🎵 صوت (MP3)", callback_data="download_audio"),
                ]
            ]
        )
        await update.message.reply_text(
            "اختر ما تريد تحميله:",
            reply_markup=keyboard,
        )
    else:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎥 فيديو", callback_data="download_video"),
                    InlineKeyboardButton("🎵 صوت (MP3)", callback_data="download_audio"),
                ]
            ]
        )
        await update.message.reply_text(
            "اختر صيغة التحميل المطلوبة:",
            reply_markup=keyboard,
        )


async def handle_download_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    pending = pending_downloads.pop(user_id, None)

    if pending is None:
        await query.edit_message_text(
            "⚠️ انتهت صلاحية هذا الطلب. أرسل الرابط من جديد."
        )
        return

    url, platform = pending
    audio_only = query.data == "download_audio"

    await query.edit_message_text("⏳ جاري التحميل...")
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action=ChatAction.UPLOAD_AUDIO if audio_only else ChatAction.UPLOAD_VIDEO,
    )

    temp_dir = tempfile.mkdtemp()
    try:
        result = download_video(url, temp_dir, audio_only=audio_only, platform=platform)

        if isinstance(result, list):
            filepaths = result
        else:
            filepaths = [result]

        valid_files = []
        for filepath in filepaths:
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            if size_mb <= MAX_FILE_SIZE_MB:
                valid_files.append(filepath)
            else:
                logger.warning(f"ملف كبير جداً: {filepath} ({size_mb:.1f}MB)")

        if not valid_files:
            await query.edit_message_text(
                f"⚠️ جميع الملفات أكبر من الحد المسموح ({MAX_FILE_SIZE_MB} ميجا)."
            )
            return

        if audio_only:
            for i, filepath in enumerate(valid_files):
                with open(filepath, "rb") as audio_file:
                    caption = "✅ تفضل، الصوت جاهز!" if len(valid_files) == 1 else f"✅ الصوت {i+1}/{len(valid_files)}"
                    await context.bot.send_audio(
                        chat_id=query.message.chat_id,
                        audio=audio_file,
                        caption=caption,
                    )
        else:
            for i, filepath in enumerate(valid_files):
                caption = None
                if platform == "tiktok":
                    caption = "✅ تفضل، بدون علامة مائية!"
                elif platform == "youtube":
                    caption = "✅ تفضل، هذا المقطع من يوتيوب!"
                elif platform == "instagram":
                    caption = f"✅ تفضل ({i+1}/{len(valid_files)})" if len(valid_files) > 1 else "✅ تفضل من انستغرام!"
                elif platform == "pinterest":
                    caption = f"✅ تفضل ({i+1}/{len(valid_files)})" if len(valid_files) > 1 else "✅ تفضل من بنترست!"

                ext = Path(filepath).suffix.lower()

                if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                    with open(filepath, "rb") as photo_file:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=photo_file,
                            caption=caption,
                        )
                else:
                    with open(filepath, "rb") as video_file:
                        await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=video_file,
                            caption=caption,
                        )

        await query.delete_message()

    except yt_dlp.utils.DownloadError as e:
        logger.error("خطأ تحميل: %s", e)
        await query.edit_message_text(
            "❌ تعذّر تحميل المحتوى. تأكد من صحة الرابط ومن أن المحتوى غير خاص أو محذوف.\n\n"
            "إذا استمرت المشكلة، تواصل مع الدعم الفني عبر /support"
        )
    except Exception as e:
        logger.exception("خطأ غير متوقع")
        await query.edit_message_text(f"❌ صار خطأ غير متوقع: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def setup_commands(app):
    from telegram import BotCommand

    await app.bot.set_my_commands(
        [
            BotCommand("start", "بدء استخدام البوت"),
            BotCommand("about", "إمكانيات البوت"),
            BotCommand("help", "طريقة الاستخدام"),
            BotCommand("support", "التواصل مع الدعم الفني"),
        ]
    )


def main():
    if not BOT_TOKEN:
        raise SystemExit(
            "الرجاء ضبط توكن البوت أولاً عبر متغير البيئة BOT_TOKEN."
        )

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_commands).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CallbackQueryHandler(handle_download_choice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("البوت شغال...")
    app.run_polling()


if __name__ == "__main__":
    main()
