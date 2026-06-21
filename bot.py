"""
GST 102 Study Bot
-----------------
A personal Telegram quiz bot for GST 102 (Communication in English II).

Flow:
  /start  -> serves a question with A/B/C/D inline buttons
  tap     -> "Correct!" or "Wrong, the answer is X"
  missed questions resurface after 20-50 other questions (spaced repetition)
  progress is tracked (e.g. "12% done") and persisted to disk

Designed for: Render Web Service (polling) + UptimeRobot keep-alive ping.
"""

import os
import json
import random
import logging
import threading

import telebot
from telebot import types

from keep_alive import keep_alive

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gstbot")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is missing. Set it in Render > Environment.")

# Spaced repetition window: a missed question comes back after this many
# other questions have been shown (random within the range each time).
REQUEUE_MIN = 20
REQUEUE_MAX = 50

PROGRESS_FILE = os.environ.get("PROGRESS_FILE", "progress.json")
QUESTIONS_FILE = os.environ.get("QUESTIONS_FILE", "questions.json")

LETTERS = "ABCDEF"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ----------------------------------------------------------------------------
# Load questions
# ----------------------------------------------------------------------------
with open(QUESTIONS_FILE, encoding="utf-8") as f:
    DATA = json.load(f)

QUESTIONS = {q["id"]: q for q in DATA["questions"]}
ALL_IDS = list(QUESTIONS.keys())
TOTAL = len(ALL_IDS)
log.info("Loaded %d questions", TOTAL)

# ----------------------------------------------------------------------------
# Per-user state (single user, but keyed by chat_id so it's safe either way)
# ----------------------------------------------------------------------------
# state = {
#   chat_id: {
#       "queue": [ids not yet asked, shuffled],
#       "answered_correct": set(ids),    # mastered
#       "seen": set(ids),                # ever served
#       "missed": {id: due_counter},     # id -> show again when counter <= served_count
#       "served_count": int,             # total questions served so far
#       "current": id or None,           # awaiting an answer
#       "right": int, "wrong": int       # tally for the session
#   }
# }
STATE = {}
_lock = threading.Lock()


def _load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return {}
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    restored = {}
    for cid, s in raw.items():
        restored[int(cid)] = {
            "queue": s.get("queue", []),
            "answered_correct": set(s.get("answered_correct", [])),
            "seen": set(s.get("seen", [])),
            "missed": {int(k): v for k, v in s.get("missed", {}).items()},
            "served_count": s.get("served_count", 0),
            "current": s.get("current"),
            "right": s.get("right", 0),
            "wrong": s.get("wrong", 0),
        }
    return restored


def _save_progress():
    serializable = {}
    for cid, s in STATE.items():
        serializable[str(cid)] = {
            "queue": s["queue"],
            "answered_correct": sorted(s["answered_correct"]),
            "seen": sorted(s["seen"]),
            "missed": {str(k): v for k, v in s["missed"].items()},
            "served_count": s["served_count"],
            "current": s["current"],
            "right": s["right"],
            "wrong": s["wrong"],
        }
    tmp = PROGRESS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(serializable, f)
    os.replace(tmp, PROGRESS_FILE)


STATE = _load_progress()


def fresh_state():
    ids = ALL_IDS[:]
    random.shuffle(ids)
    return {
        "queue": ids,
        "answered_correct": set(),
        "seen": set(),
        "missed": {},
        "served_count": 0,
        "current": None,
        "right": 0,
        "wrong": 0,
    }


def get_state(chat_id):
    if chat_id not in STATE:
        STATE[chat_id] = fresh_state()
    return STATE[chat_id]


# ----------------------------------------------------------------------------
# Question selection
# ----------------------------------------------------------------------------
def pick_next(s):
    """Pick the next question id. Missed questions that are 'due' take priority."""
    served = s["served_count"]

    # 1) Any missed question whose re-queue time has arrived?
    due = [qid for qid, due_at in s["missed"].items() if served >= due_at]
    if due:
        qid = random.choice(due)
        del s["missed"][qid]
        return qid

    # 2) Otherwise pull from the fresh queue
    while s["queue"]:
        qid = s["queue"].pop(0)
        if qid in s["answered_correct"]:
            continue  # already mastered, skip
        return qid

    # 3) Queue exhausted. If there are still missed ones pending, force the soonest.
    if s["missed"]:
        qid = min(s["missed"], key=s["missed"].get)
        del s["missed"][qid]
        return qid

    return None  # everything mastered


def build_keyboard(q):
    kb = types.InlineKeyboardMarkup()
    for i, opt in enumerate(q["options"]):
        letter = LETTERS[i]
        # callback: ans|<qid>|<chosen_index>
        kb.add(types.InlineKeyboardButton(
            text=f"{letter}. {opt}"[:64],
            callback_data=f"ans|{q['id']}|{i}"
        ))
    return kb


def progress_line(s):
    mastered = len(s["answered_correct"])
    pct = round(mastered / TOTAL * 100, 1)
    return f"📊 Progress: <b>{pct}%</b> ({mastered}/{TOTAL} mastered)"


def send_question(chat_id):
    s = get_state(chat_id)
    qid = pick_next(s)
    if qid is None:
        bot.send_message(
            chat_id,
            "🎉 You've mastered every question in the bank!\n\n"
            "Send /reset to start a fresh run, or /stats to review."
        )
        s["current"] = None
        _save_progress()
        return

    q = QUESTIONS[qid]
    s["current"] = qid
    s["seen"].add(qid)
    s["served_count"] += 1

    header = progress_line(s)
    body = f"<b>Q{s['served_count']}</b>  <i>({q['source']})</i>\n\n{q['question']}"
    bot.send_message(chat_id, f"{header}\n\n{body}", reply_markup=build_keyboard(q))
    _save_progress()


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def cmd_start(m):
    s = get_state(m.chat.id)
    if s["served_count"] == 0:
        bot.send_message(
            m.chat.id,
            "👋 <b>GST 102 Study Bot</b>\n\n"
            f"{TOTAL} questions loaded. Tap an option to answer.\n"
            "Missed questions come back later automatically.\n\n"
            "Commands: /stats  /reset  /skip"
        )
    send_question(m.chat.id)


@bot.message_handler(commands=["skip"])
def cmd_skip(m):
    s = get_state(m.chat.id)
    s["current"] = None
    send_question(m.chat.id)


@bot.message_handler(commands=["stats"])
def cmd_stats(m):
    s = get_state(m.chat.id)
    total_ans = s["right"] + s["wrong"]
    acc = round(s["right"] / total_ans * 100, 1) if total_ans else 0
    msg = (
        f"{progress_line(s)}\n\n"
        f"✅ Correct: {s['right']}\n"
        f"❌ Wrong: {s['wrong']}\n"
        f"🎯 Accuracy: {acc}%\n"
        f"🔁 Queued for review: {len(s['missed'])}\n"
        f"📥 Remaining unseen: {len([i for i in s['queue'] if i not in s['answered_correct']])}"
    )
    bot.send_message(m.chat.id, msg)


@bot.message_handler(commands=["reset"])
def cmd_reset(m):
    STATE[m.chat.id] = fresh_state()
    _save_progress()
    bot.send_message(m.chat.id, "🔄 Progress reset. Send /start to begin again.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("ans|"))
def on_answer(c):
    chat_id = c.message.chat.id
    s = get_state(chat_id)

    try:
        _, qid_str, chosen_str = c.data.split("|")
        qid = int(qid_str)
        chosen = int(chosen_str)
    except (ValueError, IndexError):
        bot.answer_callback_query(c.id, "Invalid response.")
        return

    # Ignore taps on stale questions (e.g. after /skip)
    if s["current"] != qid:
        bot.answer_callback_query(c.id, "That question is no longer active. Here's a new one 👇")
        send_question(chat_id)
        return

    q = QUESTIONS[qid]
    correct_idx = q["answer_index"]
    correct_letter = LETTERS[correct_idx]
    correct_text = q["options"][correct_idx]

    with _lock:
        if chosen == correct_idx:
            s["right"] += 1
            s["answered_correct"].add(qid)
            s["missed"].pop(qid, None)
            result = f"✅ <b>Correct!</b>  ({correct_letter}. {correct_text})"
            bot.answer_callback_query(c.id, "Correct! ✅")
        else:
            s["wrong"] += 1
            s["answered_correct"].discard(qid)
            # schedule for review after 20-50 more questions
            due_at = s["served_count"] + random.randint(REQUEUE_MIN, REQUEUE_MAX)
            s["missed"][qid] = due_at
            chosen_letter = LETTERS[chosen] if chosen < len(LETTERS) else "?"
            result = (
                f"❌ <b>Wrong.</b>\n"
                f"You chose {chosen_letter}.\n"
                f"Correct answer: <b>{correct_letter}. {correct_text}</b>\n"
                f"<i>(will reappear later for review)</i>"
            )
            bot.answer_callback_query(c.id, "Wrong ❌")

    # Lock the answered message (remove buttons, show result)
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=c.message.message_id,
            text=f"{c.message.html_text}\n\n{result}",
            reply_markup=None,
        )
    except Exception as e:  # message edit can fail on rare races; not fatal
        log.warning("edit failed: %s", e)

    s["current"] = None
    _save_progress()
    send_question(chat_id)


# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    keep_alive()  # start Flask server so Render keeps the service alive
    log.info("Bot polling started.")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
