# studybot
# GST 102 Study Bot

A personal Telegram quiz bot for **GST 102 – Communication in English II**.
Serves multiple-choice questions with A/B/C/D buttons, tells you if you're right
or gives you the correct answer, tracks your progress (e.g. "12% done"), and
brings missed questions back later for review (spaced repetition).

Built to run on **Render (Web Service, free tier) + UptimeRobot** keep-alive,
same pattern as a standard always-on Telegram bot.

---

## What it does

- `/start` — serves a question with tappable A/B/C/D options
- Tap an option → **Correct!** or **Wrong — the answer is X** (with the full correct option)
- Wrong answers are re-queued and reappear after **20–50** other questions
- Progress bar on every question: `📊 Progress: 12% (81/675 mastered)`
- Progress is saved to `progress.json` so it survives restarts
- `/stats` — accuracy, correct/wrong tally, how many are queued for review
- `/skip` — skip the current question
- `/reset` — wipe progress and start fresh

**675 questions** are bundled in `questions.json`, compiled from your four
lecturer sources (the 500 FUOYE CBT set, the 51-question MCQ set, the 100-question
forwarded set, and the 25-question writing-ethics set).

---

## Quick local test

```bash
pip install -r requirements.txt
export BOT_TOKEN="your_token_from_@BotFather"
python bot.py
```

Then message your bot `/start` on Telegram.

---

## Deploy on Render

1. Push this folder to a **GitHub repo**.
2. On [render.com](https://render.com) → **New** → **Web Service** → connect the repo.
3. Settings:
   - **Runtime:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python bot.py`
   - **Instance type:** Free
4. **Environment → Add Environment Variable:**
   - Key: `BOT_TOKEN`  ·  Value: *(your BotFather token)*
5. Deploy. The log should show `Bot polling started.`

`render.yaml` is included, so you can also use Render's **Blueprint** deploy and
it'll pick up the settings automatically (you still add `BOT_TOKEN` manually,
since secrets aren't committed).

---

## Keep it awake with UptimeRobot

Render's free Web Service sleeps when idle. The bot runs a tiny Flask server so
UptimeRobot can ping it:

1. Copy your Render URL (e.g. `https://gst102-study-bot.onrender.com`).
2. On [uptimerobot.com](https://uptimerobot.com) → **Add New Monitor**:
   - **Type:** HTTP(s)
   - **URL:** your Render URL (the `/` route returns "alive")
   - **Interval:** 5 minutes
3. Save. That ping keeps Render from spinning down.

Health endpoints: `/` and `/health`.

---

## Editing / adding questions

All questions live in **`questions.json`**. Each entry:

```json
{
  "id": 1,
  "source": "FUOYE CBT (500)",
  "question": "Communication can best be defined as:",
  "options": ["Sleeping and eating", "The exchange of information and ideas", "...", "..."],
  "answer_index": 1,
  "answer_letter": "B",
  "answer_text": "The exchange of information and ideas"
}
```

To fix or add a question, edit that file. `answer_index` is 0-based
(0=A, 1=B, 2=C, 3=D). Keep `answer_index`, `answer_letter`, and `answer_text`
consistent. Restart the service to load changes.

---

## ⚠️ Notes on the answer keys

The answers follow the **lecturer-provided keys**. A few spots were adjusted or
flagged (also recorded under `meta.notes` in `questions.json`):

- **51-set Q3** ("the ___ transmits the message") — source answer was **blank**;
  filled in as **sender**.
- **51-set** "a ___ indicates the action done by the subject" — source key said
  *Adverb*; corrected to **Verb** (a verb shows the action).
- **100-set Q82** (plural forms: Louse→Lice, Basis→Bases, etc.) was an open-ended
  fill-in, not multiple choice, so it's **not** in the quiz pool.

A handful of the original keys have other likely typos. If you hit an answer that
looks wrong while studying, it's probably the source key — easy to fix in
`questions.json`.

---

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Main bot: quiz flow, spaced repetition, progress |
| `keep_alive.py` | Flask server for Render + UptimeRobot |
| `questions.json` | All 675 questions + answers |
| `requirements.txt` | Dependencies |
| `Procfile` / `render.yaml` / `runtime.txt` | Deploy config |
