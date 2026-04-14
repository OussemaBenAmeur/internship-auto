# Internship Auto Usage Guide

This guide explains how to use this app as an actual internship-search workflow, not just as a one-off generator.

The tool is designed to help you:

- convert your CV into a structured profile
- keep a clean list of target companies and roles
- generate tailored outreach drafts
- track each application in SQLite
- review what to send next
- manage follow-ups without losing state when you rerun the generator

It does not auto-apply to portals and it does not send emails for you. That is deliberate. The app handles the repeatable parts; you keep control over the final send decision.

## 1. Core Idea

There are two input files:

- `profile.json`: your structured candidate profile
- `companies.csv`: the companies and roles you want to target

There is one main output folder:

- `out/`

Inside `out/`, the most important files are:

- `applications.db`: the real source of truth for tracking application state
- `tracker.csv`: spreadsheet-style export of the DB
- `dashboard.md`: ranked summary of targets
- `followups.ics`: calendar reminders for follow-ups
- `companies/*.md`: one generated company page per target, with drafts and rationale

The intended workflow is:

1. Prepare your profile.
2. Maintain a focused target list.
3. Run the generator.
4. Review one application at a time.
5. Manually send the best drafts.
6. Update statuses in the tracker.
7. Check due follow-ups regularly.
8. Rerun the generator when your profile or company list changes.

The important design choice is this: rerunning `run` refreshes generated content, but it keeps your manual tracking state from the SQLite database.

## 2. File Overview

### `profile.json`

This file represents you as structured data.

It includes:

- contact details
- headline and summary
- education
- skills
- interests
- value pitch
- projects
- experiences
- certifications
- languages
- preferred locations
- target roles
- public links

The better this file is, the better the generated outreach will be.

### `companies.csv`

This file is your target pipeline.

Supported columns:

```text
company,role,location,contact_name,contact_email,job_url,priority,keywords,notes
```

What each column means:

- `company`: company or lab name
- `role`: exact role title you want to target
- `location`: city, country, or `Remote`
- `contact_name`: recruiter or professor name if known
- `contact_email`: email address if you have one
- `job_url`: job page or lab page URL
- `priority`: usually `high`, `medium`, or `low`
- `keywords`: comma-separated skills or themes relevant to the role
- `notes`: your custom angle for that target

### `out/applications.db`

This is the main tracker.

It stores:

- the generated drafts
- company metadata
- match score and fit reasoning
- current application status
- follow-up schedule
- applied date
- last follow-up date

If you care about workflow continuity, this file matters more than `tracker.csv`.

## 3. First-Time Setup

If you already have a CV PDF:

```bash
python3 main.py import-cv --cv cv_new.pdf --force
```

This uses `pdftotext` to build `profile.json`.

If you want starter templates instead:

```bash
python3 main.py init --force
```

That creates starter versions of:

- `profile.json`
- `companies.csv`

After that:

1. Review `profile.json` manually.
2. Add real companies to `companies.csv`.
3. Run the pipeline.

## 4. Build a Good `profile.json`

Do not treat `profile.json` as a dump of your CV. Treat it as a curated signal source.

To use the app effectively:

- keep your summary specific
- list real technical skills you are comfortable discussing
- make project bullets concrete
- make experience bullets action-oriented
- include public links that are worth opening
- keep target roles aligned with what you actually want

Good profile content improves:

- match scoring
- selected project and experience evidence
- email draft quality
- LinkedIn message quality
- cover note relevance

Weak example:

```text
Worked on AI and backend systems.
```

Better example:

```text
Built an end-to-end document extraction pipeline combining OCR, layout-aware models, and retrieval for enterprise document workflows.
```

The generator can only produce strong drafts if the underlying facts are strong.

## 5. Build a Good `companies.csv`

The biggest mistake is adding too many vague targets.

Use this tool for a deliberate shortlist, not for blind mass outreach.

Good practice:

- add companies you would genuinely apply to
- use one row per role
- include `job_url` whenever possible
- set `priority` honestly
- add role-specific `keywords`
- write a short `notes` angle that tells future-you what to emphasize

Example:

```csv
InstaDeep,AI Research Engineer Intern,Paris,,,https://instadeep.com/careers,high,"rl,python,pytorch,research","Emphasize applied ML, production systems, and Tunisian background"
```

For research labs, you can still use the tool even if there is no formal posting.

In that case:

- put the lab name in `company`
- describe the target in `role`
- use a team page or lab page in `job_url`
- put professor/team info in `contact_name` and `contact_email` if known
- use `notes` to capture the research angle

## 6. Run the Pipeline

Basic command:

```bash
python3 main.py run
```

This does several things:

1. Loads `profile.json`
2. Loads `companies.csv`
3. Scores each target against your profile
4. Selects the best experiences and projects for each target
5. Generates tailored drafts
6. Writes one markdown page per company into `out/companies/`
7. Syncs everything into `out/applications.db`
8. Exports `out/tracker.csv`
9. Writes `out/dashboard.md`
10. Writes `out/followups.ics`

Useful options:

```bash
python3 main.py run --profile profile.json --companies companies.csv --output out
```

```bash
python3 main.py run --campaign-start 2026-04-14
```

```bash
python3 main.py run --db out/applications.db
```

When to rerun:

- after editing `profile.json`
- after adding or removing companies
- after improving your notes or keywords
- after updating your CV

What rerun does not do:

- it does not erase your application status history
- it does not erase `date_applied`
- it does not erase follow-up state stored in SQLite

That makes reruns safe and useful.

## 7. Understand the Outputs

### `out/dashboard.md`

This is a quick ranking view.

Use it to:

- see the highest-match targets
- spot where your strongest fit is
- decide what to review first

### `out/companies/<slug>.md`

This is the detailed page for one target.

Each file includes:

- match score
- priority
- location
- contact info
- pitch angle
- recommended action
- why the fit makes sense
- best experiences to mention
- best projects to mention
- follow-up dates
- outreach email draft
- LinkedIn message draft
- short cover note

This file is the best place to review one target in detail outside the CLI.

### `out/tracker.csv`

This is a spreadsheet-style export.

Use it when you want to:

- scan many rows quickly
- sort in Excel or Google Sheets
- share a tracker with someone else

But remember: the DB is authoritative.

## 8. Daily CLI Workflow

### Show top opportunities

```bash
python3 main.py status
```

If `out/applications.db` exists, this reads from the database.

### See the current queue

```bash
python3 main.py queue
```

This lists active applications with:

- ID
- company
- role
- current status
- priority
- match score
- next follow-up date

Filter by status:

```bash
python3 main.py queue --status new
```

```bash
python3 main.py queue --status drafted --status reviewed
```

Limit results:

```bash
python3 main.py queue --limit 10
```

### Review one application in detail

```bash
python3 main.py review --id 3
```

This prints:

- role and company context
- notes and keywords
- matched tracks and matched keywords
- recommended action
- follow-up plan
- email subject
- full email draft
- LinkedIn draft
- cover note

If you omit `--id`, it picks the next application from review-oriented statuses:

```bash
python3 main.py review
```

You can also constrain that fallback:

```bash
python3 main.py review --status drafted
```

## 9. Status Workflow

The app supports this status flow:

```text
new -> drafted -> reviewed -> sent -> followed_up -> closed
```

What each status means:

- `new`: generated and not yet worked
- `drafted`: draft exists and needs editing
- `reviewed`: you reviewed and approved the draft
- `sent`: you actually sent the email or applied
- `followed_up`: you already sent at least one follow-up
- `closed`: no more action needed

Update status like this:

```bash
python3 main.py set-status --id 3 --status drafted
```

```bash
python3 main.py set-status --id 3 --status reviewed
```

```bash
python3 main.py set-status --id 3 --status sent
```

When you mark something as `sent`:

- the app keeps or computes the next follow-up date
- `date_applied` is set automatically if it was empty

When you mark something as `followed_up`:

- the app stores the follow-up action date
- it computes the next follow-up date from the second reminder or from a default delay

When you mark something as `closed`:

- follow-up due is cleared

You can override the next follow-up date manually:

```bash
python3 main.py set-status --id 3 --status sent --follow-up-due 2026-04-25
```

You can also backdate a status change:

```bash
python3 main.py set-status --id 3 --status sent --changed-on 2026-04-14
```

This is useful if you sent the application yesterday but updated the tracker today.

## 10. Follow-Up Workflow

List due follow-ups:

```bash
python3 main.py followups
```

Check due follow-ups as of a specific date:

```bash
python3 main.py followups --as-of 2026-04-20
```

This command only shows applications in statuses where follow-up matters:

- `sent`
- `followed_up`

Best practice:

1. Run `python3 main.py followups` each morning or evening.
2. Send the follow-up manually.
3. Mark the application as `followed_up`.
4. Close the application when it is resolved or no longer worth pursuing.

## 11. Recommended Real-World Workflow

If you want to use the app effectively, follow this routine.

### Weekly planning

Once or twice per week:

1. Add new companies or labs to `companies.csv`.
2. Remove weak targets you are no longer serious about.
3. Improve keywords and notes.
4. Rerun `python3 main.py run`.

### Daily execution

Each day:

1. Run `python3 main.py queue --status new`.
2. Pick 1 to 3 strong targets.
3. Open `python3 main.py review --id <id>`.
4. Edit the draft outside the tool if needed.
5. Send manually.
6. Mark status as `sent`.
7. Run `python3 main.py followups`.

This keeps outreach quality high while still using automation for speed.

## 12. How to Write Better Notes and Keywords

The `keywords` and `notes` columns are where most of the targeting quality comes from.

Use `keywords` for:

- technologies
- problem domains
- research themes
- stack hints

Examples:

- `python,pytorch,transformers,rag`
- `computer vision,ocr,document intelligence`
- `backend,distributed systems,api`

Use `notes` for:

- why this company is relevant
- what project or experience to emphasize
- whether to frame it as research, engineering, or product work
- any personal connection or language angle

Examples:

- `Lean on document extraction and OCR work`
- `Mention French and English communication ability`
- `Position yourself as applied ML engineer, not only researcher`
- `Tie to native inference and JVM integration work`

Weak `notes`:

```text
Interesting company.
```

Strong `notes`:

```text
Emphasize OCR pipeline, layout-aware models, and production inference constraints because the team works on document workflows.
```

## 13. Research Labs vs Industry Roles

You can use the same tool for both, but the way you fill `companies.csv` should differ.

### For industry internships

Focus on:

- exact role title
- job URL
- recruiter contact if available
- stack-specific keywords
- product or infrastructure angle

### For research labs

Focus on:

- lab or team name
- professor or group contact
- lab page URL
- research keywords
- notes about papers, topics, or fit

For labs, you should still manually read papers before sending the final email. The app can help structure the outreach, but it cannot replace that judgment step.

## 14. Practical Tips for Better Results

- Do not dump 200 companies into `companies.csv`. Quality drops fast.
- Keep separate notes for each target instead of reusing generic language.
- Review every email before sending.
- Use the company markdown page to extract the best talking points.
- Keep your GitHub and LinkedIn links clean and current.
- Rerun after meaningful CV updates.
- Close stale applications so the queue stays honest.
- Use `priority` to control focus, not ego.
- Prefer fewer high-quality applications over broad low-quality outreach.

## 15. Common Mistakes

### Mistake: treating generated drafts as final

Fix: always review before sending.

### Mistake: vague profile content

Fix: rewrite summary, achievements, and project bullets with real technical detail.

### Mistake: weak company notes

Fix: add a clear angle for each target.

### Mistake: never updating statuses

Fix: use `set-status` immediately after you act.

### Mistake: relying only on `tracker.csv`

Fix: treat `applications.db` as the real tracker.

### Mistake: rerunning and assuming everything reset

Fix: understand that reruns refresh drafts but preserve manual tracking state.

## 16. Example Session

A typical session might look like this:

```bash
python3 main.py run
python3 main.py queue --status new --limit 5
python3 main.py review --id 2
python3 main.py set-status --id 2 --status reviewed
python3 main.py set-status --id 2 --status sent
python3 main.py followups
```

What that means:

1. Refresh all generated content.
2. Show the best untouched targets.
3. Inspect one target deeply.
4. Mark it ready.
5. Mark it sent after manual submission.
6. Check what needs follow-up.

## 17. If You Want to Stay Organized

A strong setup is:

- `profile.json` updated whenever your CV changes
- `companies.csv` kept to a deliberate shortlist
- `out/applications.db` preserved over time
- `out/tracker.csv` used only as a convenience view
- `followups.ics` imported into your calendar

If you follow that pattern, the app becomes a lightweight CRM for your internship search.

## 18. Command Reference

Initialize starter files:

```bash
python3 main.py init --force
```

Import CV into structured profile:

```bash
python3 main.py import-cv --cv cv_new.pdf --force
```

Generate and sync everything:

```bash
python3 main.py run
```

Show top targets:

```bash
python3 main.py status
```

List active queue:

```bash
python3 main.py queue
```

Review one application:

```bash
python3 main.py review --id 1
```

Update status:

```bash
python3 main.py set-status --id 1 --status sent
```

List due follow-ups:

```bash
python3 main.py followups
```

## 19. Final Advice

Use this app to increase consistency, not to remove judgment.

The winning pattern is:

- keep inputs sharp
- review before sending
- update statuses immediately
- follow up reliably
- rerun often enough to keep drafts fresh

If you do that, the tool becomes genuinely useful instead of becoming another folder of generated files.
