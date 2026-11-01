# The AI assistant (read-only)

What it is: a chat window on the home screen that answers questions about the business from the live ERP: "إيه رصيد
خزنة الأزاريطة؟", "كام حجز بكرة في القاعات؟", "إيراد الاستوديو الشهر ده؟". It reads only. It cannot create, change,
delete, submit or post anything, and every read runs as the user who asks, with that user's own permissions.

Who sees it: the owner (Super Admin) and the developers (System Manager) — `assistant/api.py`.

How it answers (`assistant/tools.py`, used by both `assistant/gemini.py` and `assistant/claude.py`): the model gets five read tools and nothing else — the dashboard's
figures, the ERP's reports (a fixed list), listing and counting records of a fixed list of DocTypes through
`frappe.get_list` (permissions applied), and an account's ledger balance. After every tool the database transaction is
rolled back, so even a mistaken read cannot leave anything behind. A permission refusal is returned to the model as an
error, which it reports; it never guesses a number. A zero with no records behind it is said to be missing data.

Connect it (production, once; the key is kept in the site's config, never in git). Gemini (the owner's choice, 1 Nov 2026):

```
bench --site frontend set-config imed_assistant_provider imed_erp.assistant.gemini.GeminiProvider
bench --site frontend set-config imed_assistant_api_key AIza...                   # Google AI Studio key
bench --site frontend set-config imed_assistant_model gemini-3.5-flash             # optional; the default (1 Nov 2026:
                                   # 3.1 Pro Preview exceeded the key's quota; 3.8 Flash ran minutes under high demand)
```

Or Claude, the same way with `imed_erp.assistant.claude.ClaudeProvider`, an `sk-ant-...` key and `claude-opus-5-5`.

Then the Owner Dashboard's "AI assistant" line reads "Connected to its model". Each message costs tokens; the chat is
rate-limited to 20 messages a minute per address.

Voice: the browser reads an answer aloud (the 🔊 button on it) with its own voice, no server involved. Spoken questions
are recorded by the chat, but the model does not transcribe audio: a voice message arrives as "[voice message]" until a
speech-to-text step is added (a later change).

Tests: `bench --site frontend run-tests --module imed_erp.imederp.test_assistant` (a fake model; nothing is sent).
