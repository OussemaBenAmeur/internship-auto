# Internship Automation Script

This project gives you a local CLI to organize an internship search without relying on external packages.

It automates the parts that are repeatable:

- importing your CV into a structured profile
- turning a list of target companies into a ranked tracker
- generating a tailored outreach page for each company
- drafting an email subject, email body, LinkedIn DM, and short cover note
- persisting applications in a SQLite tracker so status survives reruns
- surfacing a review queue and follow-up queue from the CLI
- creating follow-up reminders in an `.ics` calendar file

It does not try to bypass application portals or captchas.

## Quick Start

If you already have a CV PDF, generate the profile from it:

```bash
python3 main.py import-cv --cv cv_new.pdf --force
```

If you want starter files instead:

```bash
python3 main.py init --force
```

Then edit `companies.csv` and run:

```bash
python3 main.py run
```

Review the queue:

```bash
python3 main.py queue
python3 main.py review --id 1
python3 main.py set-status --id 1 --status reviewed
python3 main.py set-status --id 1 --status sent
python3 main.py followups
```

Generated files:

- `out/tracker.csv`
- `out/applications.db`
- `out/dashboard.md`
- `out/followups.ics`
- `out/companies/*.md`

To print the top targets from the generated tracker:

```bash
python3 main.py status
```

## Input Files

`profile.json` stores your background, skills, links, projects, certifications, and work experience.

`import-cv` uses `pdftotext`, so that command needs to be available on your machine.

`companies.csv` supports these columns:

```text
company,role,location,contact_name,contact_email,job_url,priority,keywords,notes
```

The SQLite tracker uses this status flow:

```text
new -> drafted -> reviewed -> sent -> followed_up -> closed
```

`run` keeps manual status fields intact when you regenerate drafts from `companies.csv`.

## Suggested Workflow

1. Add 20 to 50 companies you actually want.
2. Regenerate `profile.json` whenever you materially update your CV.
3. Tune `keywords` and `notes` so the generated outreach stays specific.
4. Run `python3 main.py run` to refresh company pages and sync the SQLite tracker.
5. Use `python3 main.py queue` and `python3 main.py review --id <id>` to work through drafts.
6. Move applications forward with `python3 main.py set-status --id <id> --status <status>`.
7. Attach your resume manually when you send emails.
8. Import `out/followups.ics` into your calendar and use `python3 main.py followups` to catch due follow-ups.
# internship-auto
