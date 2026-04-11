from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus


PROFILE_TEMPLATE = """{
  "name": "Your Name",
  "email": "you@example.com",
  "phone": "+216 00 000 000",
  "headline": "Software engineering student focused on machine learning and backend systems",
  "summary": "Write 2-3 lines summarizing your strongest technical direction and current experience.",
  "university": "Your University",
  "degree": "Software Engineering",
  "graduation_year": 2027,
  "availability": "Summer 2026",
  "skills": [
    "Python",
    "PyTorch",
    "Spring Boot",
    "React",
    "Docker"
  ],
  "interests": [
    "machine learning engineering",
    "computer vision",
    "backend engineering",
    "document intelligence"
  ],
  "value_pitch": [
    "I can move from experimentation to production code quickly.",
    "I am comfortable across ML, backend APIs, and product integration."
  ],
  "projects": [
    {
      "name": "Example Project",
      "summary": "One-line description of the project and why it matters.",
      "skills": ["Python", "React"],
      "achievements": [
        "Add one bullet with a concrete result or capability."
      ]
    }
  ],
  "experiences": [
    {
      "company": "Example Company",
      "title": "Software Engineering Intern",
      "location": "Sousse, Tunisia",
      "start_date": "June 2025",
      "end_date": "July 2025",
      "summary": "One-line summary of what you shipped or improved.",
      "skills": ["PyTorch", "Computer Vision"],
      "achievements": [
        "Add one bullet that shows scope, ownership, or impact."
      ],
      "kind": "work"
    }
  ],
  "certifications": [
    "Example Certificate"
  ],
  "languages": [
    "Arabic (Native)",
    "English (C1)",
    "French (B2)"
  ],
  "preferred_locations": [
    "Tunisia",
    "France",
    "Remote"
  ],
  "target_roles": [
    "Machine Learning Engineer Intern",
    "Software Engineer Intern",
    "MLOps Intern"
  ],
  "links": {
    "linkedin": "https://linkedin.com/in/your-handle",
    "github": "https://github.com/your-handle",
    "portfolio": "https://your-portfolio.example.com"
  }
}
"""

COMPANIES_TEMPLATE = """company,role,location,contact_name,contact_email,job_url,priority,keywords,notes
Mistral AI,ML Engineer Intern,Paris,,careers@mistral.ai,https://jobs.mistral.ai,high,"llm,python,ml,rag,transformers","Lean on your document intelligence and RAG work"
Datadog,Software Engineering Intern,Paris,,recruiting@datadoghq.com,https://careers.datadoghq.com,high,"python,backend,distributed systems,observability","Highlight production engineering depth and ability to work across services"
Hugging Face,Machine Learning Intern,Remote,,jobs@huggingface.co,high,"pytorch,transformers,nlp,mlops","Mention LLM fine-tuning, Hugging Face stack, and NLP coursework"
Doctolib,Software Engineer Intern,Paris,Recruiting Team,,https://careers.doctolib.com,medium,"java,spring boot,react,product","Emphasize full-stack adaptability and product-minded execution"
"""

SECTION_HEADERS = [
    "ABOUT ME",
    "WORK EXPERIENCE",
    "EDUCATION",
    "PROJECTS",
    "TECHNICAL SKILLS",
    "VOLUNTEER EXPERIENCE",
    "CERTIFICATES",
    "HOBBIES AND INTERESTS",
]

TRACK_KEYWORDS = {
    "ai_ml": {
        "machine learning",
        "deep learning",
        "ml",
        "llm",
        "nlp",
        "pytorch",
        "scikit-learn",
        "keras",
        "transformers",
        "hugging face",
    },
    "computer_vision": {
        "computer vision",
        "vision",
        "image",
        "ocr",
        "layoutlm",
        "paddleocr",
        "document extraction",
        "qwen-vl",
    },
    "mlops_data": {
        "mlops",
        "docker",
        "kubernetes",
        "mlflow",
        "pipeline",
        "rag",
        "deployment",
        "data",
        "inference",
    },
    "backend_platform": {
        "backend",
        "api",
        "spring boot",
        "java",
        "jvm",
        "c++",
        "platform",
        "distributed systems",
        "microservices",
    },
    "full_stack_mobile": {
        "react",
        "frontend",
        "full-stack",
        "full stack",
        "flutter",
        "mobile",
        "web",
        "javascript",
        "typescript",
    },
}

TRACK_LABELS = {
    "ai_ml": "AI/ML",
    "computer_vision": "Computer Vision",
    "mlops_data": "MLOps/Data",
    "backend_platform": "Backend/Platform",
    "full_stack_mobile": "Full-Stack/Mobile",
}

SKILL_HINTS = [
    "Python",
    "C/C++",
    "Java",
    "JavaScript/TypeScript",
    "PyTorch",
    "Scikit-Learn",
    "PaddleOCR",
    "LayoutLM",
    "Hugging Face Transformers",
    "Spring Boot",
    "React",
    "Flutter",
    "Docker",
    "Kubernetes",
    "MLflow",
    "LangChain",
    "pandas",
    "NumPy",
    "Matplotlib",
    "Seaborn",
    "Statsmodels",
    "RAG",
    "Qwen-VL",
]

STOPWORDS = {
    "and",
    "the",
    "with",
    "in",
    "on",
    "for",
    "from",
    "your",
    "this",
    "that",
    "role",
    "team",
    "intern",
    "internship",
    "software",
    "engineer",
    "engineering",
    "present",
    "current",
    "using",
    "used",
    "into",
    "across",
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "target"


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tokenize(*chunks: str) -> set[str]:
    text = " ".join(chunk for chunk in chunks if chunk)
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9+#./-]{2,}", text)
        if token.lower() not in STOPWORDS
    }


def parse_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def parse_date(raw: str | None) -> date:
    if not raw:
        return date.today()
    return datetime.strptime(raw, "%Y-%m-%d").date()


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            ordered.append(cleaned)
            seen.add(cleaned)
    return ordered


def normalize_url(value: str) -> str:
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"


def clean_pdf_lines(text: str) -> list[str]:
    cleaned = text.replace("\x0c", "\n")
    return [line.strip() for line in cleaned.splitlines()]


def extract_sections_from_cv(text: str) -> tuple[list[str], dict[str, list[str]]]:
    header_lines: list[str] = []
    sections: dict[str, list[str]] = {header: [] for header in SECTION_HEADERS}
    current_header: str | None = None

    for raw_line in clean_pdf_lines(text):
        if raw_line in SECTION_HEADERS:
            current_header = raw_line
            continue
        if current_header:
            sections[current_header].append(raw_line)
        else:
            header_lines.append(raw_line)

    return header_lines, sections


def consume_bullet(lines: list[str], start_index: int, marker: str) -> tuple[str, int]:
    line = lines[start_index]
    text = line.lstrip(marker).strip()
    index = start_index + 1

    while index < len(lines):
        next_line = lines[index]
        if not next_line:
            index += 1
            continue
        if next_line.startswith("•") or next_line.startswith("◦") or next_line in SECTION_HEADERS:
            break
        text = f"{text} {next_line}"
        index += 1

    return compact_whitespace(text), index


def infer_skills(text: str) -> list[str]:
    lowered = text.lower()
    return [skill for skill in SKILL_HINTS if skill.lower() in lowered]


def infer_tracks(text: str) -> list[str]:
    lowered = text.lower()
    tracks: list[str] = []
    for track, keywords in TRACK_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            tracks.append(track)
    return tracks


def infer_graduation_year(summary: str) -> int:
    current_year = date.today().year
    if "second-year" in summary.lower() or "second year" in summary.lower():
        return current_year + 1
    return current_year + 2


@dataclass
class Project:
    name: str
    summary: str
    skills: list[str]
    achievements: list[str]

    @classmethod
    def from_dict(cls, payload: dict) -> "Project":
        return cls(
            name=payload["name"],
            summary=payload["summary"],
            skills=list(payload.get("skills", [])),
            achievements=list(payload.get("achievements", [])),
        )

    def combined_text(self) -> str:
        return " ".join([self.name, self.summary, *self.skills, *self.achievements])


@dataclass
class Experience:
    company: str
    title: str
    location: str
    start_date: str
    end_date: str
    summary: str
    skills: list[str]
    achievements: list[str]
    kind: str = "work"

    @classmethod
    def from_dict(cls, payload: dict) -> "Experience":
        return cls(
            company=payload["company"],
            title=payload["title"],
            location=payload.get("location", ""),
            start_date=payload.get("start_date", ""),
            end_date=payload.get("end_date", ""),
            summary=payload["summary"],
            skills=list(payload.get("skills", [])),
            achievements=list(payload.get("achievements", [])),
            kind=payload.get("kind", "work"),
        )

    def combined_text(self) -> str:
        return " ".join(
            [self.company, self.title, self.location, self.summary, *self.skills, *self.achievements]
        )


@dataclass
class CandidateProfile:
    name: str
    email: str
    phone: str
    headline: str
    summary: str
    university: str
    degree: str
    graduation_year: int
    availability: str
    skills: list[str]
    interests: list[str]
    value_pitch: list[str]
    projects: list[Project]
    experiences: list[Experience]
    certifications: list[str]
    languages: list[str]
    preferred_locations: list[str]
    target_roles: list[str]
    links: dict[str, str]

    @classmethod
    def from_dict(cls, payload: dict) -> "CandidateProfile":
        return cls(
            name=payload["name"],
            email=payload["email"],
            phone=payload["phone"],
            headline=payload.get("headline", ""),
            summary=payload.get("summary", ""),
            university=payload["university"],
            degree=payload["degree"],
            graduation_year=int(payload["graduation_year"]),
            availability=payload["availability"],
            skills=list(payload.get("skills", [])),
            interests=list(payload.get("interests", [])),
            value_pitch=list(payload.get("value_pitch", [])),
            projects=[Project.from_dict(item) for item in payload.get("projects", [])],
            experiences=[Experience.from_dict(item) for item in payload.get("experiences", [])],
            certifications=list(payload.get("certifications", [])),
            languages=list(payload.get("languages", [])),
            preferred_locations=list(payload.get("preferred_locations", [])),
            target_roles=list(payload.get("target_roles", [])),
            links=dict(payload.get("links", {})),
        )

    def combined_text(self) -> str:
        return " ".join(
            [
                self.headline,
                self.summary,
                self.degree,
                self.university,
                *self.skills,
                *self.interests,
                *self.value_pitch,
                *self.certifications,
                *self.languages,
                *(project.combined_text() for project in self.projects),
                *(experience.combined_text() for experience in self.experiences),
            ]
        )


@dataclass
class CompanyTarget:
    company: str
    role: str
    location: str
    contact_name: str
    contact_email: str
    job_url: str
    priority: str
    keywords: list[str]
    notes: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "CompanyTarget":
        return cls(
            company=row.get("company", "").strip(),
            role=row.get("role", "").strip(),
            location=row.get("location", "").strip(),
            contact_name=row.get("contact_name", "").strip(),
            contact_email=row.get("contact_email", "").strip(),
            job_url=row.get("job_url", "").strip(),
            priority=(row.get("priority", "medium") or "medium").strip().lower(),
            keywords=parse_list(row.get("keywords", "")),
            notes=row.get("notes", "").strip(),
        )

    def combined_text(self) -> str:
        return " ".join([self.company, self.role, self.location, self.notes, *self.keywords])


@dataclass
class TargetPackage:
    target: CompanyTarget
    match_score: int
    matched_keywords: list[str]
    matched_tracks: list[str]
    selected_projects: list[Project]
    selected_experiences: list[Experience]
    recommended_action: str
    follow_ups: list[date]
    email_subject: str
    email_body: str
    linkedin_message: str
    cover_note: str
    fit_summary: str
    pitch_angle: str
    output_file: Path


def load_profile(path: Path) -> CandidateProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CandidateProfile.from_dict(payload)


def load_targets(path: Path) -> list[CompanyTarget]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [CompanyTarget.from_row(row) for row in reader if row.get("company")]


def extract_pdf_text(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Failed to read CV with pdftotext: {result.stderr.strip()}")
    return result.stdout


def parse_header_info(lines: list[str]) -> tuple[str, str, str, dict[str, str]]:
    text = "\n".join(lines)
    visible_lines = [line for line in lines if line]
    name = visible_lines[0] if visible_lines else "Candidate"
    email_match = re.search(r"Email:\s*([^\s]+)", text)
    phone_match = re.search(r"Mobile:\s*([+\d\s]+)", text)

    links = {"linkedin": "", "github": "", "portfolio": ""}
    for line in visible_lines:
        lowered = line.lower()
        if "linkedin.com/" in lowered:
            links["linkedin"] = normalize_url(line)
        elif "github.com/" in lowered:
            links["github"] = normalize_url(line)
        elif lowered.startswith("website:"):
            links["portfolio"] = normalize_url(line.split(":", 1)[1].strip())

    return (
        name,
        email_match.group(1) if email_match else "",
        phone_match.group(1).strip() if phone_match else "",
        links,
    )


def join_section_lines(lines: list[str]) -> str:
    return compact_whitespace(" ".join(line for line in lines if line))


def parse_technical_skills(lines: list[str]) -> tuple[list[str], list[str]]:
    skills: list[str] = []
    languages: list[str] = []

    for line in lines:
        if not line.startswith("•"):
            continue
        content = line.lstrip("•").strip()
        if ":" not in content:
            continue
        label, raw_values = content.split(":", 1)
        values = unique(parse_list(raw_values))
        if label.strip().lower() == "languages":
            languages = values
        elif label.strip().lower() != "soft skills":
            skills.extend(values)

    return unique(skills), languages


def parse_work_experiences(lines: list[str], kind: str) -> list[Experience]:
    experiences: list[Experience] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue
        if not line.startswith("•"):
            index += 1
            continue

        header = line.lstrip("•").strip()
        if kind == "volunteer":
            title_part, _, date_part = header.partition(":")
            title, company = title_part, ""
            if " at " in title_part:
                title, company = [part.strip() for part in title_part.split(" at ", 1)]
            index += 1
            achievements: list[str] = []
            while index < len(lines) and not lines[index].startswith("•"):
                if lines[index].startswith("◦"):
                    bullet, index = consume_bullet(lines, index, "◦")
                    achievements.append(bullet)
                else:
                    index += 1
            experiences.append(
                Experience(
                    company=company or "Volunteer",
                    title=title,
                    location="",
                    start_date=date_part.strip(),
                    end_date="",
                    summary=achievements[0] if achievements else title,
                    skills=infer_skills(" ".join(achievements)),
                    achievements=achievements,
                    kind="volunteer",
                )
            )
            continue

        company = header
        index += 1

        def next_non_empty(start: int) -> tuple[str, int]:
            cursor = start
            while cursor < len(lines) and not lines[cursor]:
                cursor += 1
            if cursor >= len(lines):
                return "", cursor
            return lines[cursor], cursor + 1

        title, index = next_non_empty(index)
        location, index = next_non_empty(index)
        dates, index = next_non_empty(index)

        achievements: list[str] = []
        while index < len(lines) and not lines[index].startswith("•"):
            if lines[index].startswith("◦"):
                bullet, index = consume_bullet(lines, index, "◦")
                achievements.append(bullet)
            else:
                index += 1

        start_date, end_date = "", ""
        if " - " in dates:
            start_date, end_date = [part.strip() for part in dates.split(" - ", 1)]
        elif " – " in dates:
            start_date, end_date = [part.strip() for part in dates.split(" – ", 1)]

        combined = " ".join([company, title, location, *achievements])
        experiences.append(
            Experience(
                company=company,
                title=title,
                location=location,
                start_date=start_date,
                end_date=end_date,
                summary=achievements[0] if achievements else f"{title} at {company}",
                skills=infer_skills(combined),
                achievements=achievements,
                kind="work",
            )
        )

    return experiences


def parse_projects(lines: list[str]) -> list[Project]:
    projects: list[Project] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue
        if not line.startswith("•"):
            index += 1
            continue

        header = line.lstrip("•").strip()
        name = header.split(":")[0].strip()
        index += 1
        achievements: list[str] = []

        while index < len(lines) and not lines[index].startswith("•"):
            if lines[index].startswith("◦"):
                bullet, index = consume_bullet(lines, index, "◦")
                achievements.append(bullet)
            else:
                index += 1

        combined = " ".join([name, *achievements])
        projects.append(
            Project(
                name=name,
                summary=achievements[0] if achievements else name,
                skills=infer_skills(combined),
                achievements=achievements,
            )
        )

    return projects


def infer_value_pitch(summary: str, experiences: list[Experience]) -> list[str]:
    pitches = [
        "I can move from ML experimentation to production-grade engineering quickly.",
        "I am comfortable working across models, backend systems, and product integration.",
    ]
    joined = " ".join(experience.combined_text() for experience in experiences).lower()
    if "c++" in joined and "java" in joined:
        pitches.insert(
            1,
            "I can bridge research code and runtime constraints, including native-performance integration work.",
        )
    return pitches[:3]


def infer_target_roles(profile_text: str) -> list[str]:
    roles = [
        "Machine Learning Engineer Intern",
        "Software Engineer Intern",
        "Backend Engineer Intern",
    ]
    lowered = profile_text.lower()
    if any(token in lowered for token in ["computer vision", "ocr", "layoutlm"]):
        roles.append("Computer Vision Intern")
    if any(token in lowered for token in ["mlops", "docker", "kubernetes", "mlflow"]):
        roles.append("MLOps Intern")
    if any(token in lowered for token in ["react", "flutter", "spring boot"]):
        roles.append("Full-Stack Engineer Intern")
    return unique(roles)


def profile_from_cv_text(cv_text: str, availability: str) -> dict:
    header_lines, sections = extract_sections_from_cv(cv_text)
    name, email, phone, links = parse_header_info(header_lines)
    summary = join_section_lines(sections["ABOUT ME"])
    skills, languages = parse_technical_skills(sections["TECHNICAL SKILLS"])
    work_experiences = parse_work_experiences(sections["WORK EXPERIENCE"], "work")
    volunteer_experiences = parse_work_experiences(sections["VOLUNTEER EXPERIENCE"], "volunteer")
    projects = parse_projects(sections["PROJECTS"])
    certifications = [line for line in sections["CERTIFICATES"] if line]

    education_lines = [line for line in sections["EDUCATION"] if line]
    university = education_lines[0].lstrip("•").strip() if education_lines else ""
    degree = education_lines[1] if len(education_lines) > 1 else "Software Engineering"

    interests = unique(
        [
            "machine learning engineering",
            "computer vision",
            "document intelligence",
            "MLOps",
            "backend engineering",
            "full-stack product development",
            "developer tooling",
        ]
    )

    combined_text = " ".join(
        [
            summary,
            *(project.combined_text() for project in projects),
            *(experience.combined_text() for experience in work_experiences),
        ]
    )

    profile = {
        "name": name,
        "email": email,
        "phone": phone,
        "headline": "Software engineering student building ML, document AI, and backend systems",
        "summary": summary,
        "university": university,
        "degree": degree,
        "graduation_year": infer_graduation_year(summary),
        "availability": availability,
        "skills": skills,
        "interests": interests,
        "value_pitch": infer_value_pitch(summary, work_experiences),
        "projects": [project.__dict__ for project in projects],
        "experiences": [experience.__dict__ for experience in [*work_experiences, *volunteer_experiences]],
        "certifications": certifications,
        "languages": languages,
        "preferred_locations": ["Tunisia", "France", "Remote"],
        "target_roles": infer_target_roles(combined_text),
        "links": links,
    }
    return profile


def build_profile_terms(profile: CandidateProfile) -> set[str]:
    return tokenize(profile.combined_text())


def build_target_terms(target: CompanyTarget) -> set[str]:
    return tokenize(target.combined_text())


def score_profile_tracks(profile: CandidateProfile, target: CompanyTarget) -> list[str]:
    profile_tracks = set(infer_tracks(profile.combined_text()))
    target_tracks = set(infer_tracks(target.combined_text()))
    return [TRACK_LABELS[track] for track in sorted(profile_tracks & target_tracks)]


def score_evidence_text(text: str, target_terms: set[str], target_tracks: set[str]) -> int:
    lowered = text.lower()
    overlap = len(target_terms & tokenize(text))
    track_hits = sum(1 for track in target_tracks if any(keyword in lowered for keyword in TRACK_KEYWORDS[track]))
    return overlap * 4 + track_hits * 10


def choose_evidence(
    profile: CandidateProfile,
    target: CompanyTarget,
) -> tuple[list[Experience], list[Project], list[str], list[str], int]:
    target_terms = build_target_terms(target)
    profile_terms = build_profile_terms(profile)
    matched_keywords = sorted(target_terms & profile_terms)
    target_tracks = set(infer_tracks(target.combined_text()))
    matched_tracks = score_profile_tracks(profile, target)

    scored_experiences = []
    for experience in profile.experiences:
        score = score_evidence_text(experience.combined_text(), target_terms, target_tracks)
        if experience.kind == "work":
            score += 6
        scored_experiences.append((score, experience))
    scored_experiences.sort(key=lambda item: item[0], reverse=True)

    scored_projects = []
    for project in profile.projects:
        score = score_evidence_text(project.combined_text(), target_terms, target_tracks)
        scored_projects.append((score, project))
    scored_projects.sort(key=lambda item: item[0], reverse=True)

    selected_experiences = [experience for score, experience in scored_experiences if score > 0][:2]
    if not selected_experiences and profile.experiences:
        selected_experiences = profile.experiences[:2]

    selected_projects = [project for score, project in scored_projects if score > 0][:2]
    if not selected_projects and profile.projects:
        selected_projects = profile.projects[:2]

    priority_bonus = {"high": 12, "medium": 6, "low": 0}.get(target.priority, 3)
    location_bonus = 0
    if target.location:
        lowered_location = target.location.lower()
        if "remote" in lowered_location:
            location_bonus = 2
        elif any(location.lower() in lowered_location for location in profile.preferred_locations):
            location_bonus = 5
        elif "paris" in lowered_location and any("French" in language for language in profile.languages):
            location_bonus = 5

    experience_score = sum(score for score, _ in scored_experiences[:2])
    project_score = sum(score for score, _ in scored_projects[:2])
    match_score = min(
        100,
        len(matched_keywords) * 5
        + len(matched_tracks) * 16
        + experience_score
        + project_score
        + priority_bonus
        + location_bonus,
    )

    return selected_experiences, selected_projects, matched_keywords, matched_tracks, match_score


def build_pitch_angle(matched_tracks: list[str], target: CompanyTarget) -> str:
    if matched_tracks:
        return f"Lead with {', '.join(matched_tracks[:2])} experience."
    if "research" in target.role.lower() or "ml" in target.role.lower():
        return "Lead with applied ML experience and production model work."
    return "Lead with hands-on engineering breadth and ability to ship quickly."


def build_recommended_action(target: CompanyTarget, matched_tracks: list[str], matched_keywords: list[str]) -> str:
    angle = ", ".join(matched_tracks[:2]) or ", ".join(matched_keywords[:3]) or "your strongest technical evidence"
    if target.contact_email:
        return f"Email {target.contact_email} and anchor the note on {angle}."
    if target.job_url:
        return f"Apply via the portal, then send a LinkedIn note referencing {angle}."
    return f"Research a recruiter or team lead, then reach out with a short message built around {angle}."


def build_fit_summary(
    matched_tracks: list[str],
    matched_keywords: list[str],
    experiences: list[Experience],
    projects: list[Project],
) -> str:
    evidence_chunks: list[str] = []
    if matched_tracks:
        evidence_chunks.append(f"track match in {', '.join(matched_tracks[:2])}")
    if experiences:
        evidence_chunks.append(f"professional evidence from {experiences[0].title} at {experiences[0].company}")
    if projects:
        evidence_chunks.append(f"project support from {projects[0].name}")
    if matched_keywords:
        evidence_chunks.append(f"keyword overlap on {', '.join(matched_keywords[:4])}")
    return "; ".join(evidence_chunks) or "general engineering fit"


def summarize_experience_for_outreach(experience: Experience) -> str:
    if experience.achievements:
        return experience.achievements[0]
    return experience.summary


def summarize_project_for_outreach(project: Project) -> str:
    if project.achievements:
        return project.achievements[0]
    return project.summary


def lower_sentence_start(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned
    return cleaned[0].lower() + cleaned[1:]


def describe_candidate(profile: CandidateProfile) -> str:
    first_sentence = profile.summary.split(".")[0].strip()
    if first_sentence:
        lowered = lower_sentence_start(first_sentence)
        if lowered.startswith(("a ", "an ")):
            return lowered
        article = "an" if lowered[:1] in {"a", "e", "i", "o", "u"} else "a"
        return f"{article} {lowered}"
    return f"a {profile.degree} student at {profile.university}"


def current_focus_line(profile: CandidateProfile) -> str:
    work_experience = next((experience for experience in profile.experiences if experience.kind == "work"), None)
    if not work_experience:
        return f"My current focus is {profile.headline.lower()}."
    action = lower_sentence_start(summarize_experience_for_outreach(work_experience).rstrip("."))
    return f"I currently work as {work_experience.title} at {work_experience.company}, where I {action}."


def build_email_subject(profile: CandidateProfile, target: CompanyTarget) -> str:
    return f"{profile.availability} internship | {target.role} | {profile.name}"


def build_email_body(
    profile: CandidateProfile,
    target: CompanyTarget,
    matched_tracks: list[str],
    matched_keywords: list[str],
    experiences: list[Experience],
    projects: list[Project],
) -> str:
    greeting_target = target.contact_name or f"{target.company} team"
    lines = [
        f"Hi {greeting_target},",
        "",
        f"I am {profile.name}, {describe_candidate(profile)}. "
        f"I am looking for a {profile.availability.lower()} internship and I am interested in the {target.role} opportunity at {target.company}.",
        "",
        current_focus_line(profile),
    ]

    if matched_tracks:
        lines.append(f"My strongest overlap here is in {', '.join(matched_tracks[:2])}.")
    elif matched_keywords:
        lines.append(f"I noticed the role emphasizes {', '.join(matched_keywords[:4])}, which maps well to my recent work.")

    lines.append("")
    lines.append("Relevant evidence:")
    for experience in experiences[:2]:
        lines.append(f"- {experience.title}, {experience.company}: {summarize_experience_for_outreach(experience)}")
    for project in projects[:1]:
        lines.append(f"- Project - {project.name}: {summarize_project_for_outreach(project)}")

    if target.location and (
        "paris" in target.location.lower() or "france" in target.location.lower()
    ) and any(language.startswith("French") for language in profile.languages):
        lines.extend(["", "I am also comfortable working in French and English."])

    lines.extend(
        [
            "",
            f"GitHub: {profile.links.get('github', '')}",
            f"LinkedIn: {profile.links.get('linkedin', '')}",
            "",
            "Best regards,",
            profile.name,
            f"{profile.email} | {profile.phone}",
        ]
    )

    return "\n".join(lines).strip()


def build_linkedin_message(
    profile: CandidateProfile,
    target: CompanyTarget,
    matched_tracks: list[str],
    experiences: list[Experience],
) -> str:
    anchor = matched_tracks[0] if matched_tracks else "software engineering"
    experience_line = ""
    if experiences:
        experience_line = (
            f" I currently work as {experiences[0].title} at {experiences[0].company}, with hands-on work in {anchor.lower()}."
        )
    return (
        f"Hi, I am {profile.name}, {describe_candidate(profile)} looking for a {profile.availability.lower()} internship."
        f" I am interested in the {target.role} role at {target.company}.{experience_line}"
        " If useful, I can share a short note and my resume."
    )


def build_cover_note(
    profile: CandidateProfile,
    target: CompanyTarget,
    matched_tracks: list[str],
    experiences: list[Experience],
    projects: list[Project],
) -> str:
    angle = ", ".join(matched_tracks[:2]) or "machine learning and backend engineering"
    experience_text = summarize_experience_for_outreach(experiences[0]).rstrip(".") if experiences else profile.summary.rstrip(".")
    parts = [
        f"I am applying for the {target.role} role at {target.company} because it matches my recent work in {angle}.",
        f"In my current experience, I {lower_sentence_start(experience_text)}.",
    ]
    if projects:
        project_text = summarize_project_for_outreach(projects[0]).rstrip(".")
        parts.append(
            f"I also built projects such as {projects[0].name}, where I {lower_sentence_start(project_text)}."
        )
    parts.append(
        f"I would bring strong execution, cross-stack flexibility, and quick ramp-up to a {profile.availability.lower()} internship."
    )
    return " ".join(parts)


def build_package(profile: CandidateProfile, target: CompanyTarget, campaign_start: date, output_dir: Path) -> TargetPackage:
    experiences, projects, matched_keywords, matched_tracks, match_score = choose_evidence(profile, target)
    follow_ups = [campaign_start + timedelta(days=5), campaign_start + timedelta(days=12)]
    output_file = output_dir / f"{slugify(target.company)}-{slugify(target.role)}.md"
    pitch_angle = build_pitch_angle(matched_tracks, target)
    return TargetPackage(
        target=target,
        match_score=match_score,
        matched_keywords=matched_keywords,
        matched_tracks=matched_tracks,
        selected_projects=projects,
        selected_experiences=experiences,
        recommended_action=build_recommended_action(target, matched_tracks, matched_keywords),
        follow_ups=follow_ups,
        email_subject=build_email_subject(profile, target),
        email_body=build_email_body(profile, target, matched_tracks, matched_keywords, experiences, projects),
        linkedin_message=build_linkedin_message(profile, target, matched_tracks, experiences),
        cover_note=build_cover_note(profile, target, matched_tracks, experiences, projects),
        fit_summary=build_fit_summary(matched_tracks, matched_keywords, experiences, projects),
        pitch_angle=pitch_angle,
        output_file=output_file,
    )


def format_experience_block(experiences: list[Experience]) -> str:
    if not experiences:
        return "- No experience selected."
    lines = []
    for experience in experiences:
        lines.append(f"- **{experience.title}**, {experience.company}: {experience.summary}")
    return "\n".join(lines)


def format_project_block(projects: list[Project]) -> str:
    if not projects:
        return "- No project selected."
    lines = []
    for project in projects:
        lines.append(f"- **{project.name}**: {project.summary}")
    return "\n".join(lines)


def format_company_page(package: TargetPackage) -> str:
    target = package.target
    matched_keywords = ", ".join(package.matched_keywords) or "No direct keyword overlap found."
    matched_tracks = ", ".join(package.matched_tracks) or "No strong track overlap detected."
    follow_ups = "\n".join(f"- {follow_up.isoformat()}" for follow_up in package.follow_ups)
    contact = target.contact_name or "Not specified"
    if target.contact_email:
        contact = f"{contact} ({target.contact_email})"

    return f"""# {target.company} - {target.role}

## Snapshot
- Match score: {package.match_score}/100
- Priority: {target.priority}
- Location: {target.location or "Not specified"}
- Contact: {contact}
- Job URL: {target.job_url or "Not provided"}
- Pitch angle: {package.pitch_angle}
- Recommended action: {package.recommended_action}

## Why This Fits
- Track overlap: {matched_tracks}
- Keyword overlap: {matched_keywords}
- Fit summary: {package.fit_summary}
- Notes: {target.notes or "None"}

## Best Experience To Mention
{format_experience_block(package.selected_experiences)}

## Best Projects To Mention
{format_project_block(package.selected_projects)}

## Follow-Up Schedule
{follow_ups}

## Outreach Email
Subject: {package.email_subject}

{package.email_body}

## LinkedIn DM
{package.linkedin_message}

## Short Cover Note
{package.cover_note}
"""


def build_dashboard(packages: Iterable[TargetPackage], generated_at: date) -> str:
    rows = sorted(packages, key=lambda item: item.match_score, reverse=True)
    top_rows = []
    for package in rows[:10]:
        top_rows.append(
            f"| {package.target.company} | {package.target.role} | {package.match_score} | {', '.join(package.matched_tracks[:2]) or '-'} | {package.follow_ups[0].isoformat()} | {package.output_file.name} |"
        )
    body = "\n".join(top_rows) or "| No targets | - | - | - | - | - |"
    return f"""# Internship Campaign Dashboard

Generated on {generated_at.isoformat()}.

## Priority Targets
| Company | Role | Match | Best Angle | First Follow-Up | File |
| --- | --- | --- | --- | --- | --- |
{body}

## Next Steps
1. Regenerate `profile.json` from your latest CV with `python3 main.py import-cv --cv cv_new.pdf --force`.
2. Add real targets to `companies.csv`.
3. Run `python3 main.py run`.
4. Start with the highest match score, attach your resume, and send outreach.
"""


def build_calendar(packages: Iterable[TargetPackage]) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    events: list[str] = []
    for package in packages:
        for index, follow_up in enumerate(package.follow_ups, start=1):
            uid = f"{slugify(package.target.company)}-{slugify(package.target.role)}-{index}@internship-auto"
            description = package.recommended_action.replace("\n", " ")
            events.append(
                "\n".join(
                    [
                        "BEGIN:VEVENT",
                        f"UID:{uid}",
                        f"DTSTAMP:{timestamp}",
                        f"DTSTART;VALUE=DATE:{follow_up.strftime('%Y%m%d')}",
                        f"SUMMARY:Follow up with {package.target.company} about {package.target.role}",
                        f"DESCRIPTION:{description}",
                        "END:VEVENT",
                    ]
                )
            )

    return "\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//internship-auto//EN",
            *events,
            "END:VCALENDAR",
            "",
        ]
    )


def write_csv_tracker(path: Path, packages: list[TargetPackage]) -> None:
    fieldnames = [
        "company",
        "role",
        "priority",
        "match_score",
        "matched_tracks",
        "pitch_angle",
        "contact_name",
        "contact_email",
        "job_url",
        "recommended_action",
        "follow_up_1",
        "follow_up_2",
        "matched_keywords",
        "company_file",
        "search_google",
        "search_linkedin",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for package in sorted(packages, key=lambda item: item.match_score, reverse=True):
            query = f"{package.target.company} {package.target.role} internship"
            writer.writerow(
                {
                    "company": package.target.company,
                    "role": package.target.role,
                    "priority": package.target.priority,
                    "match_score": package.match_score,
                    "matched_tracks": ", ".join(package.matched_tracks),
                    "pitch_angle": package.pitch_angle,
                    "contact_name": package.target.contact_name,
                    "contact_email": package.target.contact_email,
                    "job_url": package.target.job_url,
                    "recommended_action": package.recommended_action,
                    "follow_up_1": package.follow_ups[0].isoformat(),
                    "follow_up_2": package.follow_ups[1].isoformat(),
                    "matched_keywords": ", ".join(package.matched_keywords),
                    "company_file": package.output_file.name,
                    "search_google": f"https://www.google.com/search?q={quote_plus(query)}",
                    "search_linkedin": f"https://www.linkedin.com/search/results/all/?keywords={quote_plus(query)}",
                }
            )


def create_starter_files(force: bool) -> None:
    targets = {
        Path("profile.json"): PROFILE_TEMPLATE,
        Path("companies.csv"): COMPANIES_TEMPLATE,
    }
    for path, content in targets.items():
        if path.exists() and not force:
            print(f"Skipped existing file: {path}")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")


def import_cv(cv_path: Path, output_path: Path, availability: str, force: bool) -> None:
    if output_path.exists() and not force:
        raise SystemExit(f"{output_path} already exists. Re-run with --force to overwrite it.")
    profile = profile_from_cv_text(extract_pdf_text(cv_path), availability)
    output_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote CV-based profile to {output_path}")


def run_pipeline(profile_path: Path, companies_path: Path, output_dir: Path, campaign_start: date) -> None:
    profile = load_profile(profile_path)
    targets = load_targets(companies_path)
    if not targets:
        raise SystemExit("No company targets found in the CSV file.")

    output_dir.mkdir(parents=True, exist_ok=True)
    company_pages_dir = output_dir / "companies"
    company_pages_dir.mkdir(parents=True, exist_ok=True)

    packages = [build_package(profile, target, campaign_start, company_pages_dir) for target in targets]

    for package in packages:
        package.output_file.write_text(format_company_page(package), encoding="utf-8")

    write_csv_tracker(output_dir / "tracker.csv", packages)
    (output_dir / "dashboard.md").write_text(build_dashboard(packages, campaign_start), encoding="utf-8")
    (output_dir / "followups.ics").write_text(build_calendar(packages), encoding="utf-8")

    print(f"Generated {len(packages)} target packages in {output_dir}")
    print(f"Tracker: {output_dir / 'tracker.csv'}")
    print(f"Dashboard: {output_dir / 'dashboard.md'}")
    print(f"Calendar: {output_dir / 'followups.ics'}")


def show_status(tracker_path: Path) -> None:
    with tracker_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        print("Tracker is empty.")
        return

    rows.sort(key=lambda row: (-int(row["match_score"]), row["follow_up_1"]))
    print("Top internship targets:")
    for row in rows[:5]:
        print(
            f"- {row['company']} | {row['role']} | score {row['match_score']} | "
            f"angle: {row['pitch_angle']} | follow-up {row['follow_up_1']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automate your internship outreach pipeline with CV-aware profile generation and target matching."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create starter profile and company files.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing starter files.")

    import_parser = subparsers.add_parser("import-cv", help="Build profile.json from a CV PDF using pdftotext.")
    import_parser.add_argument("--cv", type=Path, required=True, help="Path to the CV PDF.")
    import_parser.add_argument("--output", type=Path, default=Path("profile.json"))
    import_parser.add_argument("--availability", type=str, default="Summer 2026")
    import_parser.add_argument("--force", action="store_true", help="Overwrite the output profile file.")

    run_parser = subparsers.add_parser("run", help="Generate tracker, outreach drafts, and follow-up calendar.")
    run_parser.add_argument("--profile", type=Path, default=Path("profile.json"))
    run_parser.add_argument("--companies", type=Path, default=Path("companies.csv"))
    run_parser.add_argument("--output", type=Path, default=Path("out"))
    run_parser.add_argument(
        "--campaign-start",
        type=str,
        default=None,
        help="Campaign start date in YYYY-MM-DD format. Defaults to today.",
    )

    status_parser = subparsers.add_parser("status", help="Show the top opportunities from a generated tracker.")
    status_parser.add_argument("--tracker", type=Path, default=Path("out/tracker.csv"))

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        create_starter_files(force=args.force)
        return

    if args.command == "import-cv":
        if not args.cv.exists():
            raise SystemExit(f"CV file not found: {args.cv}")
        import_cv(args.cv, args.output, args.availability, args.force)
        return

    if args.command == "run":
        if not args.profile.exists() or not args.companies.exists():
            raise SystemExit("Missing profile or companies file. Run `python3 main.py init` or `python3 main.py import-cv` first.")
        run_pipeline(args.profile, args.companies, args.output, parse_date(args.campaign_start))
        return

    if args.command == "status":
        if not args.tracker.exists():
            raise SystemExit("Tracker file not found. Run `python3 main.py run` first.")
        show_status(args.tracker)
        return

    raise SystemExit("Unknown command.")


if __name__ == "__main__":
    main()
