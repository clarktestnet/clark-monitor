import feedparser
import requests
import time
import json
import os
from datetime import datetime

# ─── CONFIG (Railway environment variables se aayega) ─────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")

# ─── Jin accounts ko track karna hai — yahan add/remove karo ─────────────────
ACCOUNTS = [
    "elonmusk",
    "naval",
    "paulg",
    "saylor",
    "balajis",
    # Aur accounts add karo yahan...
]

# ─── Nitter instances (agar ek down ho toh dusra try karega) ─────────────────
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
]

SEEN_FILE      = "seen_posts.json"
CHECK_INTERVAL = 120  # 2 minutes

# ─── SEEN POSTS (duplicate alert na aaye) ────────────────────────────────────
def load_seen():
    try:
        if os.path.exists(SEEN_FILE):
            return json.load(open(SEEN_FILE, "r"))
    except:
        pass
    return {}

def save_seen(seen):
    try:
        json.dump(seen, open(SEEN_FILE, "w"))
    except:
        pass

# ─── NITTER RSS FETCH (multiple fallbacks) ───────────────────────────────────
def fetch_latest_post(username):
    for instance in NITTER_INSTANCES:
        try:
            url  = f"{instance}/{username}/rss"
            feed = feedparser.parse(url)
            if feed.entries and len(feed.entries) > 0:
                entry = feed.entries[0]
                return {
                    "id":   entry.get("id", entry.get("link", "")),
                    "text": entry.get("title", ""),
                    "link": entry.get("link", f"https://x.com/{username}"),
                    "time": entry.get("published", ""),
                }
        except Exception as e:
            print(f"  ⚠ {instance} failed for @{username}: {e}")
            continue
    return None

# ─── GROQ AI SUMMARY ─────────────────────────────────────────────────────────
def get_ai_summary(text, username):
    if not GROQ_API_KEY:
        return {"summary": "AI summary unavailable.", "rewrite": text[:100]}
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model": "llama3-8b-8192",
                "max_tokens": 200,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Analyze this tweet by @{username}.\n"
                        f"Respond ONLY as valid JSON, no markdown, no explanation:\n"
                        f"{{\"summary\":\"one sentence key insight\","
                        f"\"rewrite\":\"fresh punchy rewrite in 1-2 sentences\"}}\n\n"
                        f"Tweet: \"{text}\""
                    )
                }]
            },
            timeout=10
        )
        content = res.json()["choices"][0]["message"]["content"]
        clean   = content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        print(f"  ⚠ Groq error: {e}")
        return {
            "summary": "New post from tracked account.",
            "rewrite": text[:120] + ("..." if len(text) > 120 else "")
        }

# ─── TELEGRAM ALERT ──────────────────────────────────────────────────────────
def send_telegram(username, post_text, post_link, summary, rewrite):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("  ⚠ Telegram not configured!")
        return

    # Truncate long posts
    display_text = post_text if len(post_text) <= 300 else post_text[:297] + "..."

    message = (
        f"⚡ <b>CLARK ALERT</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>@{username}</b>\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')} IST\n\n"
        f"📝 <b>Post:</b>\n"
        f"{display_text}\n\n"
        f"🤖 <b>AI Summary:</b>\n"
        f"<i>{summary}</i>\n\n"
        f"✏️ <b>Rewrite:</b>\n"
        f"<i>{rewrite}</i>\n\n"
        f"🔗 <a href='{post_link}'>View Original Post</a>"
    )

    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id":    CHAT_ID,
                "text":       message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=10
        )
        if res.status_code == 200:
            print(f"  ✅ Telegram alert sent for @{username}")
        else:
            print(f"  ❌ Telegram error: {res.text}")
    except Exception as e:
        print(f"  ❌ Telegram failed: {e}")

# ─── STARTUP MESSAGE ─────────────────────────────────────────────────────────
def send_startup_message():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    msg = (
        f"🚀 <b>CLARK Monitor Started!</b>\n\n"
        f"📡 Tracking <b>{len(ACCOUNTS)} accounts</b>:\n"
        + "\n".join([f"  • @{a}" for a in ACCOUNTS])
        + f"\n\n⏱ Polling every <b>{CHECK_INTERVAL // 60} minutes</b>\n"
        f"✅ System is live and monitoring!"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except:
        pass

# ─── MAIN CHECK LOOP ─────────────────────────────────────────────────────────
def check_all_accounts():
    seen = load_seen()
    new_count = 0

    for username in ACCOUNTS:
        print(f"  🔍 Checking @{username}...")
        post = fetch_latest_post(username)

        if not post:
            print(f"  ⚠ Could not fetch @{username}")
            continue

        last_seen = seen.get(username)

        if last_seen == post["id"]:
            print(f"  ✓ @{username} — no new post")
            continue

        # New post detected!
        print(f"  🔥 NEW POST from @{username}: {post['text'][:60]}...")
        seen[username] = post["id"]

        # Get AI summary
        print(f"  🤖 Getting AI summary...")
        ai = get_ai_summary(post["text"], username)

        # Send Telegram alert
        send_telegram(
            username  = username,
            post_text = post["text"],
            post_link = post["link"],
            summary   = ai["summary"],
            rewrite   = ai["rewrite"],
        )

        new_count += 1
        time.sleep(1)  # Rate limit protection

    save_seen(seen)
    return new_count

# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  🚀 CLARK Monitor v1.0")
    print(f"  📡 Tracking {len(ACCOUNTS)} accounts")
    print(f"  ⏱  Polling every {CHECK_INTERVAL}s")
    print("=" * 50)

    # Validate config
    if not TELEGRAM_TOKEN:
        print("❌ ERROR: TELEGRAM_TOKEN not set!")
        exit(1)
    if not CHAT_ID:
        print("❌ ERROR: CHAT_ID not set!")
        exit(1)
    if not GROQ_API_KEY:
        print("⚠  WARNING: GROQ_API_KEY not set — AI summaries disabled")

    # Send startup notification
    send_startup_message()
    print("✅ Startup message sent to Telegram!\n")

    # Main loop
    cycle = 0
    while True:
        cycle += 1
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{now}] Cycle #{cycle} — checking {len(ACCOUNTS)} accounts...")

        try:
            new = check_all_accounts()
            print(f"  📊 Done — {new} new post(s) detected")
        except Exception as e:
            print(f"  ❌ Cycle error: {e}")

        print(f"  ⏳ Next check in {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)
