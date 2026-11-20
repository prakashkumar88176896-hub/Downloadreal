import os
import re
import glob
import asyncio
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ["BOT_TOKEN"]
MAX_SIZE = 49 * 1024 * 1024  # Telegram bot limit ~50MB
URL_RE = re.compile(r"https?://\S+")


# ---- Render ke liye chhota health-check server (Web Service ke liye) ----
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), Health).serve_forever()


# ---- Download logic ----
def download_video(url: str, out_dir: str) -> str:
    opts = {
        "format": "b[filesize<49M][ext=mp4]/b[filesize<49M]/bv*[height<=480]+ba/b[height<=480]/w",
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "max_filesize": MAX_SIZE,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = glob.glob(os.path.join(out_dir, "*"))
    if not files:
        raise RuntimeError("File download nahi hui")
    return files[0]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Namaste! 👋 Mujhe kisi video ka link bhejo, main download karke de dunga.")


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match = URL_RE.search(update.message.text or "")
    if not match:
        await update.message.reply_text("Please valid video link bhejo.")
        return

    url = match.group(0)
    status = await update.message.reply_text("⏳ Download ho raha hai...")

    with tempfile.TemporaryDirectory() as tmp:
        try:
            loop = asyncio.get_running_loop()
            path = await loop.run_in_executor(None, download_video, url, tmp)

            if os.path.getsize(path) > MAX_SIZE:
                await status.edit_text("❌ Video 50MB se badi hai, Telegram bot bhej nahi sakta.")
                return

            await status.edit_text("📤 Upload ho raha hai...")
            with open(path, "rb") as f:
                await update.message.reply_video(video=f, supports_streaming=True, read_timeout=300, write_timeout=300)
            await status.delete()
        except Exception as e:
            await status.edit_text(f"❌ Error: {str(e)[:300]}")


def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.run_polling()


if __name__ == "__main__":
    main()
