from datetime import datetime, timedelta
import os
import sqlite3
import threading
import uuid
import telebot
from flask import Flask, jsonify, request

# നിങ്ങളുടെ ടെലഗ്രാം ബോട്ട് ടോക്കൻ ഇവിടെ നൽകുക (അല്ലെങ്കിൽ Render-ൽ Environment Variable ആയി വെക്കാം)
TOKEN = os.environ.get("BOT_TOKEN", "8615503680:AAEGns_9BY8PKk6tX_yaOfTCJJnQrEjILo0")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)


# ഡാറ്റാബേസ് സെറ്റപ്പ് (കീകളും സമയവും സേവ് ചെയ്യാൻ)
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


# 1. ടെലഗ്രാം ബോട്ട് കമാൻഡ്: /genkey <മണിക്കൂർ>
@bot.message_handler(commands=["genkey"])
def generate_key(message):
  try:
    args = message.text.split()
    # സമയം മണിക്കൂറിൽ നൽകാം (ഉദാഹരണത്തിന്: /genkey 24 - ഒരു ദിവസത്തേക്ക്)
    hours = int(args[1]) if len(args) > 1 else 24

    # യുണീക്കായ ഒരു കീ ഉണ്ടാക്കുന്നു
    key = "ELITE-" + str(uuid.uuid4())[:8].upper()

    expiry = datetime.now() + timedelta(hours=hours)
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("keys.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO keys (key, expiry_time, device_id) VALUES (?, ?, ?)",
        (key, expiry_str, None),
    )
    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        f"✅ **New Key Generated Successfully!**\n\n🔑 Key: `{key}`\n⏳ Validity:"
        f" {hours} Hours\n📅 Expires At: {expiry_str}",
        parse_mode="Markdown",
    )
  except Exception as e:
    bot.reply_to(
        message,
        "⚠️ ഉപയോഗിക്കേണ്ട വിധം: `/genkey 24` (24 മണിക്കൂറിന്) അല്ലെങ്കിൽ `/genkey"
        " 1` (1 മണിക്കൂറിന്)",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["start"])
def send_welcome(message):
  bot.reply_to(
      message,
      "👋 ഹായ്! എലൈറ്റ് ലൈസൻസ് ബോത്തിലേക്ക് സ്വാഗതം.\nകീ ഉണ്ടാക്കാൻ `/genkey"
      " <hours>` എന്ന് ടൈപ്പ് ചെയ്യുക.",
  )


# 2. ആപ്പ് കീ പരിശോധിക്കാൻ ഉപയോഗിക്കുന്ന വെബ് റൂട്ട് (API)
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
  cursor.execute("SELECT expiry_time, device_id FROM keys WHERE key = ?", (key,))
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

  # ഡിവൈസ് ലോക്ക് പരിശോധിക്കുന്നു (ഒരു ഡിവൈസിൽ മാത്രം വർക്ക് ചെയ്യാൻ)
  if registered_device is None:
    # ആദ്യമായി ഉപയോഗിക്കുന്ന ഡിവൈസ് ആയതിനാൽ ഈ കീ ആ ഡിവൈസിലേക്ക് ലോക്ക് ചെയ്യുന്നു
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
    return (
        jsonify({"status": "success", "message": "കീ വെരിഫൈ ചെയ്തു!"}),
        200,
    )
  else:
    conn.close()
    return (
        jsonify({
            "status": "blocked",
            "message": "ഈ കീ വേറെയൊരു ഫോണിൽ ഉപയോഗത്തിലുള്ളതാണ്!",
        }),
        200,
    )


# ബോട്ടും വെബ് സർവറും ഒരുമിച്ച് റൺ ചെയ്യാൻ
def run_bot():
  bot.infinity_polling()


if __name__ == "__main__":
  # ബോട്ട് റൺ ചെയ്യാൻ വേറൊരു ത്രെഡ് സ്റ്റാർട്ട് ചെയ്യുന്നു
  t = threading.Thread(target=run_bot)
  t.daemon = True
  t.start()

  # ഫ്ലാസ്ക് സർവർ സ്റ്റാർട്ട് ചെയ്യുന്നു
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)