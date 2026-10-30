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

### 0:00–2:00 · ✏️ LB: the hook ("one lab value, three people")
**Draw**, left to right across the glass, as you tell the story:
1. **Provider** (left): a small clinic icon, labelled "Community health center, Phoenix · Dr. Patel".
2. **Consumer** (under the clinic): a stick figure, labelled "Maria, 52, Medicaid, type 2 diabetes".
3. **The platform** (middle): a cylinder labelled "VBC data platform".
4. **Payer** (right): a box labelled "Medicaid health plan, Arizona · Quality team".
5. Arrows: clinic → cylinder labelled "lab result HbA1c 7.2"; cylinder → plan labelled "quality file".

> "Let me tell you about three people.
>
> **Maria** is 52, on Medicaid in Arizona, and has type 2 diabetes. *(draw Maria)* Her doctor, **Dr. Patel**, works
> at a community health center in Phoenix *(draw the clinic)* and has been working with her all year. Last month
> her HbA1c came back at 7.2. Her diabetes is under control, a real win.
>
> That lab result flows into a value-based-care data platform *(draw the cylinder and arrow)*, which every month
> sends a supplemental quality file to **Maria's health plan** *(draw the plan)*. The plan's quality team uses it to
> score diabetes control. That score decides the clinic's quality bonus and the shared savings.
>
> Now, one night, upstream, the lab feed changes the result field from a number to text." *(draw a ✗ on the arrow
> into the cylinder)* "Nothing crashes. The views keep compiling. But Maria's 7.2 no longer lands as a number, so the
> quality file says her diabetes is *not controlled*. *(cross out 7.2 and write '?')*
>
> Multiply Maria by a few thousand patients. Dr. Patel's clinic looks worse than it is, the plan pays less, and the
> care manager is told to chase patients who are already doing fine. Three weeks later, someone in finance asks why
> shared savings moved.
>
> So the real questions are: *who knew, how fast, and what else broke?*" *(write "Who? How fast? What else?" under
> the drawing)*

*(The people and the clinic are illustrative, not a real case or organisation. The mechanics are real: HbA1c control
is a standard diabetes quality measure that plans score from claims, lab results and supplemental data. This exact
failure is planted in the demo as the lab-result type change behind a late-binding view, and it's the question
you'll ask at 10:00.)*

**Transition → SL:** "Let me show you the kind of platform this runs on." *(turn to the screen, slide 2)*

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
| 10:00 | *If the HbA1c result value changes type, which payer submissions and CareEmpower views are affected?* | Column lineage runs through a **late-binding view** to the PAYER_AZ1 supplemental quality file. "This is Maria's 7.2 from the lightboard. It found the quiet failure before the file went out." |

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
- Point back at Maria: "Same night, the assistant flags the type change, traces it to the quality file, and
  Dr. Patel's 7.2 counts."

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

---

## Studio setup: OBS + Teams on one monitor

### The idea: share once, never re-share
Toggling Teams screen sharing on and off mid-pitch is the slow, fragile part. On one monitor there's no need to do
it at all:

1. **Start one Teams share of your *entire screen*** at 0:00 and leave it running for all 20 minutes.
2. **Lightboard mode:** an OBS *projector* window fills your screen with the lightboard. The audience sees it at
   full screen-share quality, and you see it as your confidence monitor while you're at the glass.
3. **Screen mode:** one key minimises the projector and brings the deck, app, AWS console or terminal to the front,
   so the audience sees that. At the same time, OBS switches to a **Presenter** close-up that feeds your Teams
   camera tile, so you stay visible in the small tile while you drive the browser.

Switching is **one keystroke** (`scripts/pitch_switch.ahk`, AutoHotkey v2), with no Teams menus and no window picker.

```
  LIGHTBOARD MODE  (Ctrl+Alt+L)               SCREEN MODE  (Ctrl+Alt+D / A / W / T)
  ┌──────────── your monitor ───────────┐     ┌──────────── your monitor ───────────┐
  │  OBS projector, full screen          │     │  Chrome: deck / app / AWS, terminal  │
  │  = lightboard (shared to Teams)      │     │  (shared to Teams)                    │
  └──────────────────────────────────────┘     └──────────────────────────────────────┘
  Teams camera tile: OBS Virtual Camera        Teams camera tile: OBS "Presenter" close-up
```

### OBS settings (one-time)
| Where | Setting |
|---|---|
| Settings → Video | Base and output **1920×1080**, 30 fps |
| Settings → General | **Hide OBS from screen capture: OFF**. The projector *is* what's being shared. Turn off "Show confirmation on exit". |
| Settings → Audio | Desktop audio and mic **disabled**. Your mic goes straight into Teams, which avoids echo and lip-sync lag. |
| Studio Mode | **Off**, so hotkeys switch the live output instantly |
| Settings → Hotkeys | "Switch to scene **LB-Full**" = `Ctrl+Alt+F1`, "Switch to scene **Presenter**" = `Ctrl+Alt+F2` |
| Controls | **Start Virtual Camera** before joining the meeting |

### OBS scenes
| Scene | Sources | Used for |
|---|---|---|
| **LB-Full** | Lightboard camera (Video Capture Device, 1920×1080), Transform → **Flip Horizontal** so your writing reads correctly. Filters: Color Correction (contrast +0.2, gamma −0.1) and Sharpen. Optional small Emergere logo, bottom right. | Lightboard segments |
| **Presenter** | The *same* camera source (add it as an existing source, not a new one), cropped and scaled to head and shoulders | Teams camera tile while you're in screen mode |
| **Holding** | Emergere logo with "Starting shortly" | Before the meeting starts, and if something breaks |

Then **right-click the preview → Windowed Projector (Program)**, and press `Ctrl+Alt+P` once to make it borderless
and maximised. (Use a *windowed* projector, not a full-screen one: only a windowed one can be minimised and
restored by the script.)

### Teams settings
- Camera: **OBS Virtual Camera**. Background effects **off**. Your self-view looks mirrored; attendees see it correctly.
- Microphone: your real mic, not OBS.
- Turn on Windows **Focus assist / Do not disturb** so no notifications appear in the share. Set the taskbar to auto-hide.
- At 0:00: **Share → Screen** (the entire screen, *not* a window, so switching windows never breaks the share). Leave "Include sound" off.
- Ask the organiser to **spotlight** you, or pin yourself, so your tile stays visible next to the share.

### Browser and windows
- **Chrome windows:** the deck in one window. The app in profile A (`demo-analyst`), profile B (`demo-steward`)
  and profile C (`demo-bh-analyst`). The AWS console tabs in their own window.
- Set browser zoom to **125–150%** on the app and console tabs so attendees can read them. Present the deck with `F`
  (reveal.js full screen).
- Have Windows Terminal open with the live-day command typed but not run.

### Hotkeys (`scripts/pitch_switch.ahk`)
| Key | Result |
|---|---|
| `Ctrl+Alt+L` | **Lightboard mode:** scene LB-Full; projector restored full screen and in front |
| `Ctrl+Alt+D` | **Deck:** scene Presenter; projector minimised; deck window in front |
| `Ctrl+Alt+A` | **App:** the same, with the assistant window in front. Use `Alt+Tab` between the analyst and steward profiles. |
| `Ctrl+Alt+W` | **AWS console** window |
| `Ctrl+Alt+T` | **Terminal** |

**At the glass:** you're away from the keyboard during lightboard segments, so put the keys within reach. A small
programmable macro pad (or a Stream Deck) mapped to `Ctrl+Alt+L/D/A/W/T` works well. Don't use a slide clicker's
"black screen" key: it sends `B` or `.`, which would type into the app.

### Switch cues for this script
| Time | Press | Audience sees |
|---|---|---|
| 0:00 | `Ctrl+Alt+L` | Lightboard: the hook |
| 2:00 | `Ctrl+Alt+D` | Slides 2–5 |
| 5:00 | `Ctrl+Alt+L` | Lightboard: Medallion + Agent |
| 7:00 | `Ctrl+Alt+D` | Slides 7–8 |
| 8:30 | `Ctrl+Alt+A` | App (analyst) |
| 11:00 | `Ctrl+Alt+T`, Enter, then `Ctrl+Alt+L` | Live day starts; lightboard "day 22 ⏳" |
| 12:00 | `Ctrl+Alt+A` | App: triage and root cause |
| 14:00 | `Ctrl+Alt+T`, then `Ctrl+Alt+W` | Terminal log, then the AWS console tabs |
| 15:00 | `Ctrl+Alt+A` (`Alt+Tab` to the steward profile at 16:00) | App: live answer, govern, guardrails |
| 17:00 | `Ctrl+Alt+D` | Slides 9–10 |
| 18:30 | `Ctrl+Alt+L` | Lightboard close |
| 19:45 | `Ctrl+Alt+D` | Slide 15, Thank you |

### Rehearse it once (10 minutes)
1. Join the meeting from your **phone** as a second attendee, muted, so you can see exactly what the audience sees.
2. Start the screen share, run every hotkey in the cue table, and check that each switch takes under a second. Also
   check that the Teams meeting window and toolbar don't show up on the phone.
3. Write on the glass and confirm the text reads left-to-right on the phone. If it's backwards, toggle Flip Horizontal.
4. If OBS ignores the script's scene keys, test the OBS hotkeys by hand first. Then run the script as administrator,
   or raise `SetKeyDelay`.

**If it goes wrong:** press `Ctrl+Alt+D`. The deck is always a safe screen while you fix it. If OBS itself crashes,
the screen share keeps running: present from the deck and draw the lightboard parts on slides 3 and 7 instead.

**On a Mac:** the same approach works. Use Keyboard Maestro or Hammerspoon instead of AutoHotkey. Grant OBS and Teams
*Screen Recording* permission and OBS *Accessibility* permission (needed for global hotkeys).
