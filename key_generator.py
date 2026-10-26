from datetime import datetime, timedelta
import os
import sqlite3
import threading
import uuid
import telebot
from flask import Flask, jsonify, request

# ടെലഗ്രാം ബോട്ട് ടോക്കൻ (Render-ൽ Environment Variable ആയി നൽകുക)
TOKEN = os.environ.get("BOT_TOKEN", "8615503680:AAEGns_9BY8PKk6tX_yaOfTCJJnQrEjILo0")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)


# ഡാറ്റാബേസ് സെറ്റപ്പ്
def init_db():
  conn = sqlite3.connect("keys.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            expiry_time TEXT,
            device_id TEXT
        )
    """)
  conn.commit()
  conn.close()


init_db()


# 1. ടെലഗ്രാം ബോട്ട് കമാൻഡ്: /genkey <മണിക്കൂർ> <ഡിവൈസ്_ഐഡി>
@bot.message_handler(commands=["genkey"])
def generate_key(message):
  try:
    args = message.text.split()
    # ഉദാഹരണത്തിന്: /genkey 24 abc123xyz
    hours = int(args[1]) if len(args) > 1 else 24
    device_id = args[2] if len(args) > 2 else None

    if not device_id:
      bot.reply_to(
          message,
          "⚠️ **ശ്രദ്ധിക്കുക:** ദയവായി ഡിവൈസ് ഐഡിയും കൂടി ചേർക്കുക!\n\nഉപയോഗിക്കേണ്ട"
          " വിധം:\n`/genkey <മണിക്കൂർ> <ഡിവൈസ്_ഐഡി>`\nഉദാഹരണത്തിന്: `/genkey 24"
          " abc123xyz`",
          parse_mode="Markdown",
      )
      return

    # യുണീക്കായ കീ ഉണ്ടാക്കുന്നു
    key = "ELITE-" + str(uuid.uuid4())[:8].upper()

    expiry = datetime.now() + timedelta(hours=hours)
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("keys.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO keys (key, expiry_time, device_id) VALUES (?, ?, ?)",
        (key, expiry_str, device_id),
    )
    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        f"✅ **Device-Locked Key Generated!**\n\n🔑 Key: `{key}`\n📱 Device ID:"
        f" `{device_id}`\n⏳ Validity: {hours} Hours\n📅 Expires At:"
        f" {expiry_str}",
        parse_mode="Markdown",
    )
  except Exception as e:
    bot.reply_to(
        message,
        "⚠️ ഉപയോഗ രീതി തെറ്റാണ്. `/genkey 24 <device_id>` എന്ന് ഉപയോഗിക്കുക.",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["start"])
def send_welcome(message):
  bot.reply_to(
      message,
      "👋 ഹായ്! എലൈറ്റ് ലൈസൻസ് ബോത്തിലേക്ക് സ്വാഗതം.\nഡിവൈസ് ഐഡിയോടെ കീ ഉണ്ടാക്കാൻ"
      " `/genkey <hours> <device_id>` എന്ന് ടൈപ്പ് ചെയ്യുക.",
  )


# 2. വെബ് സർവർ & വെരിഫിക്കേഷൻ API
@app.route("/")
def home():
  return "Elite License Server is Running & Active!"


@app.route("/verify", methods=["GET"])
def verify_key():
  key = request.args.get("key")
  device_id = request.args.get("device_id")

  if not key or not device_id:
    return (
        jsonify({"status": "error", "message": "Missing key or device_id"}),
        400,
    )

  conn = sqlite3.connect("keys.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT expiry_time, device_id FROM keys WHERE key = ?", (key,)
  )
  row = cursor.fetchone()

  if not row:
    conn.close()
    return jsonify({"status": "invalid", "message": "തെറ്റായ കീ (Invalid Key)!"}), 200

  expiry_str, registered_device = row
  expiry_time = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")

  # സമയം കഴിഞ്ഞോ എന്ന് പരിശോധിക്കുന്നു
  if datetime.now() > expiry_time:
    conn.close()
    return jsonify({"status": "expired", "message": "കീയുടെ കാലാവധി കഴിഞ്ഞു!"}), 200

  # ഡിവൈസ് ലോക്ക് പരിശോധിക്കുന്നു
  if registered_device is None:
    cursor.execute(
        "UPDATE keys SET device_id = ? WHERE key = ?", (device_id, key)
    )
    conn.commit()
    conn.close()
    return (
        jsonify({
            "status": "success",
            "message": "കീ വിജയകരമായി ആക്ടിവേറ്റ് ചെയ്തു!",
        }),
        200,
    )
  elif registered_device == device_id:
    conn.close()
    return jsonify({"status": "success", "message": "കീ വെരിഫൈ ചെയ്തു!"}), 200
  else:
    conn.close()
    return (
        jsonify({
            "status": "blocked",
            "message": "ഈ കീ വേറെയൊരു ഫോണിൽ ഉപയോഗത്തിലുള്ളതാണ്!",
        }),
        200,
    )


# ബോട്ട് റൺ ചെയ്യാനുള്ള ഫംഗ്ഷൻ
def run_bot():
  bot.infinity_polling()


if __name__ == "__main__":
  # ബോട്ട് ബാക്ക്ഗ്രൗണ്ടിൽ റൺ ചെയ്യാൻ ത്രെഡ് സ്റ്റാർട്ട് ചെയ്യുന്നു
  t = threading.Thread(target=run_bot)
  t.daemon = True
  t.start()

  # ഫ്ലാസ്ക് സർവർ സ്റ്റാർട്ട് ചെയ്യുന്നു
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)
