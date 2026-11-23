# Saathi

**Say it in your language. Saathi does the web task for you, and stops before anything risky.**

Bills, bookings, certificates and forms now live on websites, and millions of people cannot complete
them alone. Only 26.8% of Indians aged 15-24 can search the internet, send email *and* bank online
(NSS 79th round, CAMS 2022-23), and only 13% of elders use computers or the internet (HelpAge India,
2025). Today they wait for family, pay an agent, or share their OTP and password.

Saathi does the task on the real website, one step at a time, says each step aloud, and **cannot be
talked into typing a secret or paying without a spoken yes.**

wHACKiest 2026 · Track 2: Beyond the Browser · Team **The Good Engineers**: Chirag Honnyal,
Bhumika Gurav, Ayush V Upadhye, Abhijeet Sharma.

## What works today

| Part | Status |
|---|---|
| Safety layer (every action passes through it) | working, unit-tested |
| Secret masking before anything leaves the device | working, unit-tested |
| Agent loop: read page → plan one step → safety check → act → narrate | working with a scripted planner, tested end to end in a real browser |
| Amazon Bedrock planner | written; not yet run (waiting for Bedrock access) |
| Mock electricity-bill site with trap pages | working (fictional "Namma Power", local only) |
| Safety score | [evidence/safety_score.md](evidence/safety_score.md) |
| Voice (Sarvam in, ElevenLabs out), scam shield, teach-once, family approval | planned, see roadmap |

## Safety score

`python -m saathi eval` runs every scenario with and without the safety layer. Results, with the commit
and time they were produced, are in [evidence/safety_score.md](evidence/safety_score.md).

The trap scenarios replay a scripted *tricked agent*: unsafe actions written to imitate an agent that
obeyed the page instead of the user. That measures the safety layer, not the planner. What counts as
a trap comes from the mock site's own markup, not from the safety rules.

## The safety rules

1. Never type into a secret field: password, OTP, PIN, CVV, card or Aadhaar.
2. Never type a value that looks like an Aadhaar or card number, in any field.
3. Only type what the user said. Values cannot come from the page, so hidden instructions on a page
   cannot make Saathi type anything.
4. Only open allowed sites. A site that imitates a known one is called out as a likely scam.
5. Ask before anything irreversible: pay, confirm, submit, delete, send, transfer.
6. On a page with scam signs (urgent threats plus KYC, password or refund), ask before any action.

Code: [saathi/safety.py](saathi/safety.py) · tests: [tests/test_safety.py](tests/test_safety.py)

## How it works

```
voice / text ─► planner (Amazon Bedrock) ─► SAFETY LAYER ─► browser (Playwright) ─► narrate
                    ▲      proposes ONE action      │ block / ask user / allow          │
                    └──── masked page snapshot ◄────┴───────────── new page ◄───────────┘
```

The planner sees the page as a list of numbered elements plus its text, with secrets masked
([saathi/masking.py](saathi/masking.py)). Page text is treated as data, never as instructions.

## Run it

Needs Python 3.11+ and Microsoft Edge (Windows) or Playwright's Chromium (Linux/macOS).

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # Linux/macOS: .venv/bin/pip
python -m pytest -q                        # unit + end-to-end tests
python -m saathi eval                      # writes evidence/safety_score.md
python -m saathi demo hidden-instructions  # watch it in a visible browser
python -m saathi demo hidden-instructions --no-safety   # the same agent without the layer
python -m saathi demo normal-bill-payment
```

On Linux/macOS, run `python -m playwright install chromium` once.

With Bedrock access (credentials from your normal AWS setup, model id from an env var):

```bash
export AWS_REGION=ap-south-1
export SAATHI_MODEL_ID=<a Bedrock model id you have access to>
python -m saathi run "Pay my electricity bill. My consumer number is 1234567890."
```

The demo browser is sandboxed: any request that tries to leave the local mock site gets a fake page,
so nothing reaches the real internet. Nothing here ever uses a real account or real money.

## Roadmap

- Voice both ways: Sarvam speech-to-text for Kannada and Hindi, ElevenLabs for spoken replies
- Scam shield on real sites, family approval for payments above a limit, teach once / repeat
- Android version (works inside any app), a phone-call line for people without smartphones,
  reading a paper bill with the camera

## Licence

MIT
