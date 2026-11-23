# AWS work for Saathi (owner: Abhijeet)

Everything AWS for wHACKiest 2026 lives here. Work top to bottom; each task has a "done when" line.
Deadline for tasks 1-5: **24 Nov 2026, 2 PM IST**, so the results can go into the video and deck
(submission closes 24 Nov, 11:59 PM IST).

## Why we need AWS

Saathi's **planner** (the part that reads a web page and decides the next click) runs on **Amazon
Bedrock**. Using AWS properly also makes us eligible for the AWS sponsor prize. Chirag's AWS account
returns `Operation not allowed` on every Bedrock call, so we are using Abhijeet's account and credits.

What the code expects (see `saathi/planner.py`):

| Setting | Value |
|---|---|
| Service | Amazon Bedrock, Converse API |
| Region | `ap-south-1` (Mumbai) |
| Model | `global.amazon.nova-2-lite-v1:0` (Amazon Nova 2 Lite). Fallbacks: `amazon.nova-lite-v1:0`, `amazon.nova-pro-v1:0` |
| Env vars | `AWS_REGION`, `SAATHI_MODEL_ID`, plus credentials (`AWS_PROFILE` or `AWS_BEARER_TOKEN_BEDROCK`) |

## Rules (read first)

- **Never** put a key, secret or token in the repo, a commit, a screenshot, a group chat or a document.
  `.env` is already in `.gitignore`. Give keys to Chirag only in person or by direct message.
- Do not change `saathi/safety.py` or `saathi/masking.py`. If something there looks wrong, tell Chirag.
- Every number we show must come from a command that was actually run, with its output saved in `evidence/`.
- Commit messages: conventional style (`feat: ...`, `chore: ...`, `docs: ...`). Keep files and commits about
  Saathi itself; no tool or vendor shout-outs beyond the stack listed above (team rule).

## Task 1. Check that Bedrock works in your account

1. AWS console, top-right region: **Asia Pacific (Mumbai) ap-south-1**.
2. **Amazon Bedrock → Playground (Chat)** → choose **Amazon Nova 2 Lite** (or Nova Lite / Nova Pro) → type `hi`.

**Done when:** the model replies. If you see `Operation not allowed`, `AccessDenied` or a model-access
message instead, screenshot the error (no account numbers or keys visible), send it to Chirag, and try
region **US East (N. Virginia) us-east-1** with the same model.

## Task 2. Credits and a spending alarm

1. **Billing and Cost Management → Credits**: confirm the credits are active and not expired.
2. **Billing → Budgets → Create budget**: monthly cost budget, **$5**, email alert at 80%.

**Done when:** credits show as active and the budget exists.

## Task 3. Make credentials for Saathi (least privilege)

Pick ONE option.

**Option A (simplest): Bedrock API key.** Bedrock console → **API keys** → generate a key (short-term
keys expire; generate a fresh one on 24 Nov morning if needed). Whoever runs Saathi sets it as the
environment variable `AWS_BEARER_TOKEN_BEDROCK`.

**Option B: IAM user with Bedrock-only access.** IAM → Users → create user `saathi-bedrock` (no console
access) → attach an inline policy with exactly this JSON → Security credentials → create access key
(type: "Application running outside AWS").

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": ["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:*:*:inference-profile/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:ListFoundationModels", "bedrock:ListInferenceProfiles"],
      "Resource": "*"
    }
  ]
}
```

On the machine that runs Saathi: `aws configure --profile saathi` (region `ap-south-1`).

**Done when:** you have a key, and it was handed to Chirag privately (and kept on your own laptop for task 4).

## Task 4. Run Saathi's real planner and save the evidence

On your laptop (Python 3.11+, Git; on Windows, Microsoft Edge is used automatically):

```bash
git clone https://github.com/thegoodengineers/saathi
cd saathi
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"        # macOS/Linux: .venv/bin/pip, then: python -m playwright install chromium
python -m pytest -q                          # must say: 27 passed (or more)
```

Set the environment (PowerShell shown; in bash use `export NAME=value`):

```powershell
$env:AWS_REGION = "ap-south-1"
$env:SAATHI_MODEL_ID = "global.amazon.nova-2-lite-v1:0"
$env:AWS_PROFILE = "saathi"                  # Option B
# or: $env:AWS_BEARER_TOKEN_BEDROCK = "<key>"   # Option A (type it yourself; never save it in a file in the repo)
```

Quick check (one tiny call):

```bash
python -c "import boto3,os; c=boto3.client('bedrock-runtime'); r=c.converse(modelId=os.environ['SAATHI_MODEL_ID'], messages=[{'role':'user','content':[{'text':'Reply with OK'}]}]); print(r['output']['message']['content'][0]['text'])"
```

Then the real run (the model decides every step on our scam and trap pages, phone and PC, with and
without the safety layer; takes a few minutes):

```bash
python -m saathi eval --planner bedrock --repeats 2
```

This writes `evidence/safety_score_bedrock.md` and `evidence/safety_score_bedrock.csv`. Also watch it
once with your own eyes (a browser opens):

```bash
python -m saathi run "I got an SMS saying my electricity will be cut tonight. Check if it is real. My consumer number is 1234567890." --start mock/sms.html
```

(`--start mock/sms.html` opens our local test SMS inbox; nothing reaches the real internet. Type `no`
if it asks to pay.)

Commit and push only the evidence files:

```bash
git add evidence/safety_score_bedrock.md evidence/safety_score_bedrock.csv
git commit -m "chore: add real-planner safety score (Amazon Nova 2 Lite)"
git push
```

**Done when:** `evidence/safety_score_bedrock.md` is on GitHub, and the `run` command finished on its own.

## Task 5. Report back to Chirag (one message)

- Region and model id that worked
- Which credential option you used (never the key itself)
- The two bold lines from `evidence/safety_score_bedrock.md` ("With the safety layer: ..." / "Without it: ...")
- Anything that failed, with the exact error text

## Task 6 (after 24 Nov, for the 1-2 Dec build): small AWS extras

Only if tasks 1-5 are done. Each gives AWS a real job in the product:

- **AWS Lambda + Amazon EventBridge:** a scheduled "check my bills" reminder that triggers a Saathi check.
- **Amazon S3 (encrypted):** optional, opt-in backup of a user's allowed-sites list and settings
  (never page contents or secrets).
- Keep the $5 budget alert on; tell Chirag before creating anything that costs money continuously.

## If something goes wrong

| Problem | Try |
|---|---|
| `Operation not allowed` | account-level block: Service Quotas → Amazon Bedrock (look for 0 limits), or open an AWS Support case asking to enable Bedrock model access |
| `AccessDeniedException` | the IAM policy is missing an action or resource above |
| `The provided model identifier is invalid` | try a fallback model id from the table at the top |
| `ValidationException ... on-demand throughput isn't supported` | use the `global.` or `apac.` inference-profile id instead of the plain model id |
| Tests fail before any AWS step | not an AWS problem: send Chirag the output of `python -m pytest -q` |
