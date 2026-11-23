# Round 1 video for Saathi (owner: Bhumika)

The wHACKiest rules ask for a **3-5 minute YouTube video (public or unlisted) that walks through our
PPT and explains the problem, the solution and the technical architecture**. Target length: **about
4 minutes**. Deadline: **uploaded by 24 Nov 2026, 5 PM IST** (Chirag submits on Devnovate by 8 PM;
the portal closes 11:59 PM).

## Rules (read first)

- Say only what is true today. The demo shows what the repo really does. Anything not built yet is
  said as "next" or "on build day".
- In the demo, the steps are **scripted** so the safety layer can be tested exactly. Say that plainly.
  Part 4b shows the real AI model's results (Abhijeet's run, `evidence/safety_score_bedrock.md`).
- Numbers on screen and in the voice-over: only the ones in this file. Each has a source.
- Calm, plain voice. No hype words ("revolutionary", "world's first"). Speak slowly.
- No other product names, and no mention of tools used to make the project (team rule).
- Never show a real phone number, address, account, OTP or key on screen.

## What you need

- Laptop with the repo set up (one time, about 5 minutes):
  ```bash
  git clone https://github.com/thegoodengineers/saathi
  cd saathi
  python -m venv .venv
  .venv/Scripts/pip install -e ".[dev]"
  python -m pytest -q        # should say 59 passed (or more)
  ```
- The deck (Google Slides, `TheGoodEngineers_Track2`), from Chirag.
- Screen recorder: **OBS Studio** (free) at 1920x1080, or Windows **Win + Alt + R** (Xbox Game Bar).
- A quiet room and earphones with a mic. Record the voice in one take per part; it is fine to redo a part.

## The script (about 4:10)

### Part 1. Hook (0:00-0:20), on screen: phone screenshot `evidence/screens/sms-scam-check-phone-safe-01.png`

> "This is a message many families in India get. 'Your electricity connection will be cut tonight.
> Update your KYC immediately,' with a link. For my grandmother, that link is a trap. We built Saathi
> to make sure she never falls into it."

### Part 2. Problem (0:20-0:55), on screen: deck slide 2

> "From 2021 to 2025, people in India filed more than sixty-five lakh financial-fraud complaints on the
> national cybercrime portal, reporting over fifty-five thousand crore rupees lost. That is Ministry of
> Home Affairs data. Fake KYC and power-cut messages are a common first step; CERT-In warns senior
> citizens about exactly these. And the people scammers target most are the ones least able to check a
> website: only thirteen percent of Indian elders use the internet. Screen readers help people see a page,
> but not judge it. And an AI agent that simply follows what a page says can be steered by a scam page."

### Part 3. Solution (0:55-1:30), on screen: deck slide 3

> "Saathi is a web helper for phone and PC that can't be tricked. You tell it what you need, or forward a
> suspicious message. It does the task on the real website, one step at a time, and tells you each step.
> Every action passes through a safety layer: it never opens look-alike sites, never types an OTP,
> password, card or Aadhaar number, only types what you yourself said, and asks before anything like a
> payment."

### Part 4. Demo (1:30-2:50), on screen: screen recording

Run in the `saathi` folder. A phone-sized browser opens and Saathi's messages appear in the banner at
the bottom.

```bash
.venv/Scripts/python -m saathi demo sms-scam-check --slow 2.5
```

Say while it runs:

> "Here is the same SMS. We ask Saathi to check it. In this demo the steps are scripted, so we can test
> the safety layer exactly. Saathi is asked to open the link, and it refuses: the address imitates the
> real electricity board's site. Instead it goes to the real site, enters the consumer number, and
> fetches the bill. Eight hundred and forty rupees, due on the thirtieth. Nothing is being cut tonight.
> That message was a scam."

Then the same agent without the safety layer:

```bash
.venv/Scripts/python -m saathi demo sms-scam-check --no-safety --slow 2.5
```

> "Now the same steps with the safety layer switched off. It opens the link, lands on the fake site, and
> types the consumer number into the fake Aadhaar box. And it still says everything is fine. That is the
> danger we are protecting people from."

Optional, 15 seconds, PC view:

```bash
.venv/Scripts/python -m saathi demo sms-scam-check --device pc --slow 1.5
```

> "The same works in a browser on a PC."

### Part 4b. The real AI (20-25 seconds), on screen: `evidence/safety_score_bedrock.md` on GitHub

> "We also let a real AI model, Amazon Nova on Bedrock, decide every step on the same pages. On its own,
> it typed the OTP that a hidden note on the page told it to, and it opened the scam link. With Saathi's
> safety layer, zero of eighty unsafe actions went through. Without it, seventeen out of seventeen did."

### Part 5. Architecture (2:50-3:30), on screen: deck slide 5

> "Here is how it works. The request comes in as voice or a forwarded message. Speech in Kannada and
> Hindi will go through Sarvam. The planner, on Amazon Bedrock, looks at a masked copy of the page,
> with passwords and numbers hidden, and proposes one action. The safety layer decides: block it, ask the
> user, or allow it. Playwright does the action in the browser, and the reply is spoken back through
> ElevenLabs. Then it repeats until the task is done."

### Part 6. Proof (3:30-3:55), on screen: `evidence/safety_score.md` on GitHub, then the green CI tick

> "We measure this, not just say it. One command runs the same agent with and without the safety layer
> on our scam pages, on a phone screen and a PC screen, both with scripted steps and with the real AI.
> With the layer, nothing unsafe went through, and no normal step was blocked by mistake. Fifty-nine
> automated tests run on every change."

### Part 7. Close (3:55-4:10), on screen: deck slide 8, then the repo link

> "Next, on build day: Kannada and Hindi voice end to end, an Android app and a PC extension, and a
> phone-call line for people without smartphones. Saathi: a web helper that can't be tricked. Thank you."

## Editing and upload

1. Join the parts in order (any editor: Clipchamp on Windows is free). Total 3:30-4:45. **Not over 5:00.**
2. Check the sound: no long silences, voice louder than any music (music is optional; no lyrics).
3. YouTube → Create → Upload. Title: `Saathi - a web helper that can't be tricked | wHACKiest 2026 Track 2 | The Good Engineers`.
   Visibility: **Unlisted**. Not made for kids. No AI-voice / synthetic content (we use our own voices).
4. Open the link in a private (incognito) window to check it plays without login.
5. Send the link to Chirag.

**Done when:** an unlisted YouTube link, 3-5 minutes, plays in a private window, and Chirag has it.

## If something goes wrong

| Problem | Try |
|---|---|
| `pip install` fails | send Chirag the last 10 lines of the output |
| The demo window is too small to read | record at 100% screen zoom; the phone window can be moved to the centre |
| Demo too fast | use `--slow 3` |
| Over 5 minutes | shorten Part 2 and Part 5 first; never cut the demo |
