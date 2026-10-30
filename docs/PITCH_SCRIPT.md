# Pitch script: AI Data Quality Assistant (20 minutes)

There are four modes in this pitch. Each one has a job: **Lightboard** for the story, **Slides** for the proof,
**App** for the "aha", and **AWS** for trust.

| Code | Mode | What's on screen |
|---|---|---|
| ✏️ LB | Lightboard | Presenter drawing (camera on the glass) |
| 🖥️ SL | Slides | `eqh-dq-assistant.html` ([live link](https://raw.githack.com/spbreed/eqh-dq-assistant/refs/heads/main/eqh-dq-assistant.html#/1)) |
| 💬 APP | App demo | The assistant (CloudFront URL in `Resources.md`) |
| ☁️ AWS | AWS console + terminal | Console tabs and a terminal at the repo root |

**Shape of the 20 minutes**

```
0      2        5      7            11  12       14    15     17     18.5   20
|--LB--|---SL---|--LB--|-----APP----|LB |--APP---|-AWS-|--APP-|--SL--|--LB--|
 hook   today    agent  find→triage  ↻   why     infra  live+  trust  close
        +pain    sketch              kick live         govern
```

---

## Before you go live (T–30 min)

- [ ] `make resume` if the pilot is paused. Ask one warm-up question so Aurora wakes up; the first answer after a pause takes about 15 s.
- [ ] **Browser profile A:** signed in as `demo-analyst`. **Profile B:** `demo-steward`. **Profile C:** `demo-bh-analyst`.
      Passwords are in Secrets Manager under `eqh-dq/cognito/<user>`.
- [ ] Open these AWS console tabs in this order:
  1. CloudFormation stacks list, filtered to `EqhDq`
  2. CloudWatch dashboard `eqh-dq-assistant`
  3. Step Functions state machine, last successful execution open in graph view
  4. Bedrock → Guardrails → the assistant guardrail
  5. S3 raw bucket → `payer=PAYER_LA1` claims prefix
  6. Budgets → `eqh-dq-assistant-monthly`
- [ ] Terminal: `cd eqh-dq-assistant && source scripts/env.sh`, with `make simulate-day N=22 INJECT=D07` typed but **not** run.
- [ ] Deck on slide 1 in a separate window. On the lightboard, pre-draw only the title line: "Who knows the data broke?"
- [ ] **Rehearse the live day once**, the same morning, on a throw-away day. Reset afterwards if needed.
      If it fails during the pitch, use the fallback at 15:00.

---

## The script

### 0:00–2:00 · ✏️ LB: the hook ("a quiet failure")
**Draw:** on the left, a box "Payer file (837)"; an arrow to a cylinder "Data platform"; an arrow to a box on the
right, "Quality submission → Health plan". Then draw a small ✗ on one column inside the cylinder.

> "This is a value-based-care company. It takes financial risk with health plans, and it gets paid on quality.
> Every night, files from 20-plus health plans flow through a data platform and out to payer submissions, practice
> scorecards and the care-management app.
>
> Now one payer quietly changes a column type." *(draw the ✗)* "Nothing crashes. The views keep compiling. The
> submission goes out with wrong numbers, and three weeks later someone in finance asks why shared savings moved.
>
> So the real questions are: *who knew, how fast, and what else broke?*" *(write "Who? How fast? What else?" under
> the drawing)*

**Transition → SL:** "Let me show you the platform we modelled this on." *(turn to the screen, slide 2)*

### 2:00–5:00 · 🖥️ SL: today and the pain (slides 2 → 5)
- **Slide 2, Customer context (30 s):** "Medicaid-first, five states, 750k members, and every payer sends different
  files. Revenue depends on the outputs at the bottom: submissions, scorecards, PMPM, datashares."
- **Slide 3, Current architecture: Medallion (60 s):** follow the orange numbers 1 → 5. "Land in bronze, catalogue,
  conform to silver, model gold in Redshift, deliver. It's a solid modern stack, and we don't touch it."
- **Slide 4, Demo data model (20 s):** "To be clear, this is a **synthetic** replica: 8 fictitious payers,
  19 entities, about 3.4 M rows. No real data anywhere in this demo."
- **Slide 5, Challenges (70 s):** "We planted **14 real-world failure modes**: stale HIE feeds, a payer resending
  a file, null spikes, type changes behind late-binding views, undocumented and outdated tables. Each one is a
  ground-truth test the assistant has to catch."

**Transition → LB:** "So what would *good* look like? Let me draw it rather than show you a box chart." *(step back to the glass)*

### 5:00–7:00 · ✏️ LB: Medallion + Agent
**Draw**, over the hook drawing or on fresh glass:
1. Three stacked bands, labelled **Bronze / Silver / Gold**. That's the existing platform.
2. To the right of it, a circle labelled **Agent**. Draw a *one-way* dashed arrow from the platform to the agent,
   labelled "metadata only".
3. Under the agent, a small cylinder labelled **Metadata store**, with the words "lineage · DQ metrics · docs".
4. Around the agent, a shield with three words on it: **read-only · entitled · cited**.
5. A stick figure on the far right with a speech bubble: "Why did LA claims drop?"

> "We don't replace anything. Every night a pipeline reads the platform's *metadata*: schemas, SQL lineage and
> aggregate quality metrics. It never reads row values. It writes all of that into a metadata store. The agent
> answers questions only from that store, through ten read-only tools. It cites every dataset it mentions, it hides
> what you're not entitled to see, and it can't change anything."

**Transition → SL:** "Here's the same picture as real AWS services." *(slide 7)*

### 7:00–8:30 · 🖥️ SL: target architecture and the pipeline (slides 6 → 8)
- **Slide 7, Target: Medallion + Agent (60 s):** point at markers 1–3: "the nightly pipeline: scheduler, Step
  Functions, Fargate jobs, Bedrock for drafting docs." Then markers 4–6: "the ask flow: Cognito, CloudFront and WAF,
  the agent on Fargate, the model on Bedrock with Guardrails."
- **Slide 8, Daily pipeline (30 s):** "Profile, then sync, then enrich, every day. That's how it caught all the
  planted defects on the day each one was injected."
- *(Slide 6, the capability cards, can be skipped live. Leave it in the deck you send afterwards.)*

**Transition → APP:** "Enough architecture. Let's ask it something." *(switch to browser profile A, `demo-analyst`)*

### 8:30–11:00 · 💬 APP: find, explain, impact
| Time | Ask | Point at |
|---|---|---|
| 8:30 | *Where do I find ED visits per 1,000 by practice for Arizona Medicaid?* | It recommends the curated `vbc_mart` view, not the raw feed. Note the citations. |
| 9:15 | *Explain `vbc_mart.practice_shared_savings_calc` in plain language.* → click the asset chip | **"AI draft – not yet approved"** label; cryptic columns decoded from lineage; the lineage graph |
| 10:00 | *If the HbA1c result value changes type, which payer submissions and CareEmpower views are affected?* | Column lineage runs through a **late-binding view** to the PAYER_AZ1 submission. "This is the hook from the lightboard. It found the quiet failure." |

**Transition → LB/terminal (the kick-off):** "Everything so far is yesterday's data. Let's make *today* happen."

### 11:00–12:00 · ✏️ LB + ☁️ terminal: kick off a live day
- In the terminal, press Enter on `make simulate-day N=22 INJECT=D07`.
  > "I've just injected a new defect into day 22: one payer's claims feed drops by two thirds. Nothing is pre-baked.
  > It'll land the files, load Redshift, profile, and sync. That takes about three minutes, so let's keep going."
- On the glass, circle the **Gold** band and write "day 22 ⏳" next to it. This gives the audience a visual timer
  to come back to.

**Transition → APP:** "While that runs, here's how a data steward starts their morning."

### 12:00–14:00 · 💬 APP: triage and root cause
| Time | Ask | Point at |
|---|---|---|
| 12:00 | *What DQ issues opened in the last 7 days? Prioritise by impact on payer submissions.* | Issues ranked by business impact: payer submissions, then CareEmpower, then practices, then finance, then marts. One-line "what breaks for whom". |
| 13:00 | *Why did Louisiana claims volume drop yesterday?* | The segment drill-down (`payer_code=PAYER_LA1`) and the trend chart, traced upstream to the raw feed. "Without this, LA cost and quality would look artificially *good*." |

**Transition → AWS:** "Let's check in on our live day, and I'll show you what's underneath." *(switch to the AWS tabs)*

### 14:00–15:00 · ☁️ AWS: the infrastructure is real
Go through the tabs quickly, with one sentence each:
1. **Terminal:** show the live-day log scrolling. "Loading Redshift now."
2. **S3 raw bucket:** the new day-22 partition for PAYER_LA1. "The thinner file just landed."
3. **CloudFormation:** "8 stacks, all infrastructure as code. One command builds it and one tears it down."
4. **CloudWatch dashboard:** "Latency, tokens per model, Guardrail interventions, pipeline failures."
5. **Bedrock Guardrail:** the deny topic "modify data, schemas or pipelines" and PII anonymisation.
6. **Budgets** *(don't dwell on the amounts)*: "Alerts to our team, and an automatic deny policy if it ever overruns."

**Transition → APP:** watch for the terminal to finish, or fill with Bedrock Guardrails until it does. Then: "Day 22 is in. Let's ask."

### 15:00–17:00 · 💬 APP: the live answer, governance, guardrails
| Time | Ask | Point at |
|---|---|---|
| 15:00 | *Is the PAYER_LA1 claims feed normal today?* | It detects the **new** volume anomaly on day 22. "Three minutes ago this didn't exist." *(On the glass, tick "day 22 ✓".)* |
| 15:40 | *Which gold-layer assets are undocumented or have outdated documentation?* | The undocumented view and the stale `core.member` comment |
| 16:00 | Switch to **profile B (`demo-steward`)** → Review queue → approve one draft | "This is the only write path. It goes to the metadata store, never to Redshift or Glue, and it's audited." |
| 16:30 | Profile A: *Show me SDoH screening tables.* then *Delete the duplicate claims for me.* | Restricted data is hidden, with an explanation. The delete is politely refused. *(Optional: show the same SDoH question in profile C, `demo-bh-analyst`.)* |

> **Fallback if the live day failed or is still running:** ask *Is the Tennessee HIE ADT feed current? What depends
> on it?* It finds a stale feed (about 155 h against a 36 h SLA) feeding the hospital-at-home referral queue, and
> makes the same point with day-21 data. Say "the live run is still going, so here's one it caught overnight" and
> move on.

**Transition → SL:** "That's the experience. Here's why you can trust it." *(slide 9)*

### 17:00–18:30 · 🖥️ SL: trust (slides 9 → 10)
- **Slide 9, Security & governance by design (45 s):** read the six headings, and land on two of them: "**metadata
  only, never row values**, enforced by an automated test" and "**agent identity**: every answer is logged with who
  asked and which tools ran."
- **Slide 10, AI evaluation (45 s):** "74 ground-truth questions, all targets met: 92% correct, 96% citation
  precision, 100% refusal and entitlement. And it's a loop: error analysis, prompt and tool hardening, and
  deterministic checks moved correctness from 74 to 92%. When GPT-5.6 is enabled, we switch the config and re-run
  the same exam."

**Transition → LB:** "Let me bring it back to where we started." *(back to the glass and the hook drawing)*

### 18:30–20:00 · ✏️ LB: close and the ask
Go back to the three questions from the hook and answer each one on the glass:
- **Who knew?** → write "the assistant, *same day*"
- **How fast?** → write "minutes, with citations"
- **What else broke?** → draw the lineage arrow to "payer submission" and write "ranked by impact"

> "No replatforming, no access to row data, nothing it can break. It sits beside the medallion platform you already
> have and makes it explainable.
>
> **Our ask:** a 6-week pilot on your *real* Glue and Redshift metadata. Your identity provider, PrivateLink, and
> your own data and AI accounts. We'll run the same 74-question exam on your platform and show you the scorecard."

*(Show slide 15, Next steps / Thank you, to finish. Open for questions.)*

---

## Transition cheat-sheet (memorise these lines)
| From → To | Line |
|---|---|
| LB → SL | "Let me show you the platform we modelled this on." |
| SL → LB | "What would *good* look like? Let me draw it." |
| LB → SL | "Here's the same picture as real AWS services." |
| SL → APP | "Enough architecture. Let's ask it something." |
| APP → LB/terminal | "Everything so far is yesterday's data. Let's make *today* happen." |
| LB → APP | "While that runs, here's how a data steward starts their morning." |
| APP → AWS | "Let's check in on our live day, and I'll show you what's underneath." |
| AWS → APP | "Day 22 is in. Let's ask." |
| APP → SL | "That's the experience. Here's why you can trust it." |
| SL → LB | "Let me bring it back to where we started." |

## If you're running long
- Cut slide 4 (data model) to one sentence, and skip slide 6.
- Skip the *Explain* question at 9:15 (the asset page shows up again in the steward step).
- In the AWS segment, show only the terminal, CloudFormation and the Guardrail.
