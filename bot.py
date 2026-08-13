"""
بوت تيليجرام لتحميل مقاطع تيك توك بدون علامة مائية.

الفكرة:
- المستخدم يرسل رابط تيك توك للبوت.
- البوت يستخدم مكتبة yt-dlp لتحميل الفيديو (النسخة الأصلية بدون شعار تيك توك).
- البوت يرسل الفيديو للمستخدم مباشرة داخل تيليجرام.

قبل التشغيل:
1. ثبّت المتطلبات:
   pip install -r requirements.txt
2. تأكد إن ffmpeg مثبت على جهازك (مطلوب لدمج الصوت والفيديو أحيانًا).
   - ويندوز: حمّل من https://ffmpeg.org وأضفه للـ PATH
   - لينكس: sudo apt install ffmpeg
   - ماك: brew install ffmpeg
3. احصل على توكن البوت من @BotFather في تيليجرام.
4. ضع التوكن في متغير البيئة BOT_TOKEN أو عدّله مباشرة بالأسفل.
5. شغّل الملف: python bot.py
"""

import os
import re
import logging
import tempfile
import shutil

import yt_dlp
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------------------

# ضع التوكن هنا مباشرة أو استخدم متغير بيئة BOT_TOKEN (يفضل الأخير للأمان)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# الحد الأقصى لحجم الملف الذي يسمح تيليجرام برفعه عبر البوت (50 ميجا تقريبًا للبوتات العادية)
MAX_FILE_SIZE_MB = 50

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TIKTOK_URL_REGEX = re.compile(
    r"(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/\S+", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# دوال المساعدة
# ---------------------------------------------------------------------------

def extract_tiktok_url(text: str) -> str | None:
    """يستخرج رابط تيك توك من نص الرسالة إن وُجد."""
    match = TIKTOK_URL_REGEX.search(text)
    return match.group(0) if match else None


def download_tiktok_video(url: str, download_dir: str) -> str:
    """
    يحمّل فيديو تيك توك بدون علامة مائية باستخدام yt-dlp.
    يرجع مسار الملف المحمّل.
    """
    output_template = os.path.join(download_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "mp4/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
        return filepath


# ---------------------------------------------------------------------------
# معالجات البوت (Handlers)
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً! 👋\n\n"
        "أرسل لي رابط أي مقطع من تيك توك وراح أحمّله لك بدون العلامة المائية.\n\n"
        "مثال:\n"
        "https://www.tiktok.com/@username/video/1234567890"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    url = extract_tiktok_url(text)

    if not url:
        await update.message.reply_text(
            "ما لقيت رابط تيك توك صحيح في رسالتك. تأكد إنك أرسلت رابط المقطع كامل."
        )
        return

    status_msg = await update.message.reply_text("⏳ جاري تحميل المقطع...")
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VIDEO
    )

    temp_dir = tempfile.mkdtemp()
    try:
        filepath = download_tiktok_video(url, temp_dir)

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            await status_msg.edit_text(
                f"⚠️ حجم الفيديو ({size_mb:.1f} ميجا) أكبر من الحد المسموح "
                f"({MAX_FILE_SIZE_MB} ميجا) لإرساله عبر البوت."
            )
            return

        with open(filepath, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption="✅ تفضل، بدون علامة مائية!",
            )
        await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        logger.error("خطأ تحميل: %s", e)
        await status_msg.edit_text(
            "❌ ما قدرت أحمّل المقطع. تأكد إن الرابط صحيح وإن المقطع غير خاص/محذوف."
        )
    except Exception as e:
        logger.exception("خطأ غير متوقع")
        await status_msg.edit_text(f"❌ صار خطأ غير متوقع: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# نقطة التشغيل
# ---------------------------------------------------------------------------

def main():
    if not BOT_TOKEN or BOT_TOKEN == "ضع_توكن_البوت_هنا":
        raise SystemExit(
            "الرجاء ضبط توكن البوت أولاً (متغير BOT_TOKEN أو داخل الكود مباشرة)."
        )

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("البوت شغال...")
    app.run_polling()


if __name__ == "__main__":
    main()
