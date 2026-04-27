# Poker Quiz Bot

Telegram preflop GTO range trainer. 6-max cash + MTT 다양한 stack depth, 20개 narrative 시나리오(RFI / vs_open / vs_3bet / squeeze / vs_limp).

## Layout

- `bot/main.py` — telegram entry point. handlers, JobQueue auto-broadcast.
- `bot/quiz.py` — `QuizManager` (scenario + EV table), `OpenRangeQuizManager` (legacy RFI ranges with chart).
- `bot/bankroll.py` — SQLite bankroll/answer_history.
- `bot/persistence.py` — `bot_state.json` (active_chats + subscribed_chats).
- `data/scenarios.json` — 20 scenario definitions with `action_sequence`.
- `data/ev_tables/*.json` — strategy + ev_vs_best per scenario.
- `data/ranges/{fmt}/{rfi|vs_rfi|vs_3bet}/...` — pre-built RFI/vs ranges (legacy chart flow).
- `data/crops/` — PDF range chart crops shown in answer messages.
- `data/bot_state.json` — runtime state, **gitignored** (do not commit).

## Quiz routing

- `/quiz`, `/q` (no args) → narrative scenario from `SCENARIO_POOL` (20 scenarios). `SCENARIO_RATIO=1.0`.
- `/quiz utg`, `/quiz 100bb` → legacy RFI flow (with chart + crop).
- `/quiz <scenario_id>` (e.g. `/quiz sb_vs_limp`) → force a specific scenario.
- `/subscribe` (private chat only) → JobQueue 1h auto-broadcast. Tunable via `BROADCAST_INTERVAL_SEC`.

Two question types share `pending_quizzes[user_id]`: `OpenRangeQuestion` (rfi: callback) vs `QuizQuestion` (sc: callback). Handlers `isinstance`-check before reading attributes.

## Deploy

- **SSH alias**: `sun-personal`
- **Server path**: `/opt/poker-quiz-bot`
- **Runtime**: tmux session `poker-bot` (no systemd). Started by:
  ```
  tmux new-session -d -s poker-bot '.venv/bin/python3 bot/main.py >> bot.log 2>&1'
  ```
- **Restart**:
  ```
  ssh sun-personal "tmux kill-session -t poker-bot 2>/dev/null; sleep 1; \
    cd /opt/poker-quiz-bot && tmux new-session -d -s poker-bot \
    '.venv/bin/python3 bot/main.py >> bot.log 2>&1'"
  ```
- **Verify**: `ssh sun-personal "ps -ef | grep bot/main.py | grep -v grep && tail -30 /opt/poker-quiz-bot/bot.log"`. Expect `Application started` and (if subscribers exist) `Auto-broadcast scheduled every 3600s` / `Scheduler started`.
- **Pre-commit checks**: `python3 -m py_compile bot/main.py bot/quiz.py bot/persistence.py bot/bankroll.py`.
- **Component mapping**:
  - Any `bot/**` change → restart tmux session.
  - Any `data/scenarios.json` change → restart (loaded at startup).
  - Any `data/ev_tables/**` change → restart.
  - `requirements.txt` change → `cd /opt/poker-quiz-bot && .venv/bin/pip install -r requirements.txt` first, then restart.
  - `data/bot_state.json` is **gitignored**; never commit. Holds live `active_chats` / `subscribed_chats`. If a stray commit ever removes it from index, `ssh sun-personal` first to back it up before pulling.
  - `data/ranges/**`, `data/crops/**`, `data/corrections.json` → no restart needed (read fresh at quiz time only when relevant).
- **Branching**: `main` is deployed. Feature branches → PR → merge → server `git pull`.
- **Pinned dep gotcha**: server runs `python-telegram-bot==22.7` but the project supports both 20.x and 22.x. `[job-queue]` extra (`apscheduler`, `pytz`, `tzlocal`) is required — see requirements.txt.
