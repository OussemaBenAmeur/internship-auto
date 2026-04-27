#!/usr/bin/env python3
"""
scraper.py — AI/ML/DS internship scraper, Western Europe + Canada, Summer 2026
Scores every listing against cv.pdf and writes a ranked CSV + HTML report.

Activate the ml env first, then run:
    python scraper.py --cv cv.pdf
    python scraper.py --cv cv.pdf --output results.csv --html report.html --max 400
    python scraper.py --cv cv.pdf --sources wwr,muse,remoteok   # specific boards only
    python scraper.py --cv cv.pdf --no-playwright               # skip JS-heavy boards
"""
from __future__ import annotations

import argparse
import csv
import html as html_lib
import json
import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

# ── optional deps ──────────────────────────────────────────────────────────────
try:
    import pdfplumber  # type: ignore
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False

try:
    import fitz  # PyMuPDF  # type: ignore
    _HAS_PYMUPDF = True
except ImportError:
    _HAS_PYMUPDF = False

try:
    from playwright.sync_api import sync_playwright  # type: ignore
    from playwright.sync_api import TimeoutError as PwTimeout  # type: ignore
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

# ── logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scraper")

# ── keyword weights ────────────────────────────────────────────────────────────
# Tier 1 (×4): Agentic AI / RAG / LLMs — highest priority
# Tier 2 (×3): core ML/DL frameworks
# Tier 3 (×2): ML-adjacent
# Tier 4 (×1): general software eng
KEYWORD_WEIGHTS: dict[str, int] = {
    "agentic": 4, "multi-agent": 4, "rag": 4, "retrieval augmented": 4,
    "retrieval-augmented": 4, "llm": 4, "large language model": 4,
    "production ml": 4, "production machine learning": 4, "llmops": 4,
    "foundation model": 4, "autonomous agent": 4, "agent": 3,
    "pytorch": 3, "tensorflow": 3, "jax": 3, "computer vision": 3,
    "ocr": 3, "document ai": 3, "document intelligence": 3,
    "nlp": 3, "natural language processing": 3,
    "transformers": 3, "hugging face": 3, "huggingface": 3,
    "layoutlm": 3, "paddleocr": 3,
    "machine learning": 2, "deep learning": 2, "neural network": 2,
    "mlops": 2, "ml engineer": 2, "ml engineering": 2,
    "data science": 2, "data scientist": 2, "python": 2,
    "scikit-learn": 2, "sklearn": 2, "docker": 2, "kubernetes": 2,
    "mlflow": 2, "langchain": 2, "llamaindex": 2, "langgraph": 2,
    "vector database": 2, "embedding": 2, "semantic search": 2,
    "fine-tuning": 2, "fine tuning": 2, "inference": 2,
    "software engineer": 1, "backend": 1, "api": 1, "spring boot": 1,
    "react": 1, "javascript": 1, "java": 1, "c++": 1,
    "research": 1, "intern": 1, "student": 1, "undergraduate": 1,
    "remote": 1, "fully remote": 2,
}

COMPANY_TYPE_HINTS: dict[str, str] = {
    "inria": "Lab", "dfki": "Lab", "fraunhofer": "Lab", "max planck": "Lab",
    "mila": "Lab", "vector institute": "Lab", "cnrs": "Lab",
    "oxford": "Lab", "cambridge": "Lab", "eth": "Lab", "epfl": "Lab",
    "deepmind": "Lab", "rwth": "Lab",
    "google": "Company", "meta": "Company", "apple": "Company",
    "microsoft": "Company", "amazon": "Company", "netflix": "Company",
    "datadog": "Company", "stripe": "Company", "databricks": "Company",
    "ibm": "Company", "sap": "Company", "bosch": "Company", "siemens": "Company",
    "cohere": "Startup", "mistral": "Startup", "hugging face": "Startup",
    "nabla": "Startup", "qantev": "Startup", "pathway": "Startup",
    "mindee": "Startup", "instadeep": "Startup", "jina": "Startup",
    "aleph alpha": "Startup", "black forest": "Startup",
}

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/133.0.0.0 Safari/537.36",
]

CSV_FIELDS = [
    "Company", "Type", "Location", "Remote/Hybrid Chance",
    "Contact Email", "Careers / Apply Link",
    "Notes for 2nd-year ML/DS Student", "CV Match Score (1-10)",
    "Why it matches your CV", "Source",
]

# ── data models ────────────────────────────────────────────────────────────────

@dataclass
class JobListing:
    company: str
    title: str
    location: str
    description: str
    apply_url: str
    source: str
    company_type: str = "Company"
    remote_chance: str = "Unknown"
    contact_email: str = ""
    notes: str = ""
    match_score: int = 0
    why_matches: str = ""


@dataclass
class CVProfile:
    raw_text: str
    keywords: set[str]
    top_skills: list[str]

    @classmethod
    def from_text(cls, text: str) -> "CVProfile":
        lower = text.lower()
        found: set[str] = {kw for kw in KEYWORD_WEIGHTS if kw in lower}
        scored = sorted(
            ((kw, KEYWORD_WEIGHTS[kw]) for kw in found),
            key=lambda x: x[1], reverse=True,
        )
        return cls(raw_text=text, keywords=found, top_skills=[k for k, _ in scored[:14]])


# ── CV parsing ─────────────────────────────────────────────────────────────────

def extract_pdf_text(path: Path) -> str:
    if _HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            if text.strip():
                return text
        except Exception as exc:
            log.warning(f"pdfplumber: {exc}")
    if _HAS_PYMUPDF:
        try:
            doc = fitz.open(path)
            return "\n".join(page.get_text() for page in doc)
        except Exception as exc:
            log.warning(f"PyMuPDF: {exc}")
    import subprocess
    r = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout
    raise SystemExit(f"Cannot read {path}. Install pdfplumber: pip install pdfplumber")


# ── scoring ────────────────────────────────────────────────────────────────────

def infer_remote_chance(text: str) -> str:
    t = text.lower()
    if any(p in t for p in ["fully remote", "100% remote", "remote-first", "remote only"]):
        return "Fully Remote (High)"
    if "remote" in t and "hybrid" in t:
        return "Remote/Hybrid (Medium)"
    if "remote" in t:
        return "Remote possible (Medium)"
    if "hybrid" in t:
        return "Hybrid (Medium)"
    if any(p in t for p in ["on-site", "on site", "in-office", "onsite"]):
        return "Onsite (Low)"
    return "Unknown"


def infer_company_type(name: str, desc: str) -> str:
    lower = name.lower()
    for hint, ctype in COMPANY_TYPE_HINTS.items():
        if hint in lower:
            return ctype
    combined = (name + " " + desc).lower()
    if any(t in combined for t in ["research lab", "research institute", "university", "institute of"]):
        return "Lab"
    if any(t in combined for t in ["startup", "seed stage", "series a", "yc-backed", "y combinator", "vc-backed"]):
        return "Startup"
    return "Company"


def score_listing(listing: JobListing, cv: CVProfile) -> tuple[int, str, str]:
    """Return (score 1-10, why_matches, notes)."""
    search = " ".join([listing.title, listing.company, listing.description, listing.location]).lower()

    raw = 0
    matched_high: list[str] = []
    matched_med: list[str] = []
    matched_low: list[str] = []

    for kw in cv.keywords:
        if kw in search:
            w = KEYWORD_WEIGHTS.get(kw, 1)
            raw += w
            if w >= 4:
                matched_high.append(kw)
            elif w >= 2:
                matched_med.append(kw)
            else:
                matched_low.append(kw)

    # Remote bonus (very relevant for Tunisia-based student)
    if any(p in search for p in ["fully remote", "100% remote", "remote-first"]):
        raw += 4
    elif "remote" in search:
        raw += 2

    # Student-explicit bonus
    if any(t in search for t in ["2nd year", "second year", "undergraduate", "bachelor", "bsc", "b.sc"]):
        raw += 2

    # Internship keyword bonus
    if any(t in search for t in ["stage", "praktikum", "internship", "intern"]):
        raw += 1

    score = min(10, max(1, 1 + round(raw / 3.0)))

    # why-it-matches text
    why_parts: list[str] = []
    if matched_high:
        why_parts.append(f"Directly matches your {', '.join(matched_high[:3])} focus")
    if matched_med:
        why_parts.append(f"overlaps with your {', '.join(matched_med[:3])} experience")
    if "remote" in search or "hybrid" in search:
        why_parts.append("remote/hybrid accessible from Tunisia")
    if not why_parts:
        why_parts.append("general software engineering overlap with your skills")
    why = "; ".join(why_parts) + "."
    why = why[0].upper() + why[1:]

    # notes
    notes_parts: list[str] = []
    if matched_high:
        notes_parts.append(f"Strong {matched_high[0]} signal — lead with your LLM/Agentic project work.")
    elif matched_med:
        notes_parts.append(f"Good ML fit; emphasize {matched_med[0]} background.")
    else:
        notes_parts.append("Solid engineering role; highlight Python and ML exposure.")

    loc_lower = listing.location.lower()
    if "remote" in search:
        notes_parts.append("Remote available — mention international availability.")
    elif "paris" in loc_lower or "france" in loc_lower:
        notes_parts.append("In France — apply in French or bilingual.")
    elif any(t in loc_lower for t in ["germany", "berlin", "münchen", "munich", "hamburg"]):
        notes_parts.append("In Germany — English applications OK at most tech companies.")
    elif "canada" in loc_lower or "toronto" in loc_lower or "montreal" in loc_lower:
        notes_parts.append("Canada role — check visa/permit requirements for internships.")

    return score, why, " ".join(notes_parts)


# ── HTTP session ───────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


# ── base scraper ───────────────────────────────────────────────────────────────

class BaseJobScraper(ABC):
    name: str = "base"
    base_delay: float = 1.5

    def __init__(self, session: requests.Session) -> None:
        self.session = session
        self.log = logging.getLogger(self.name)

    def _sleep(self, extra: float = 0.0) -> None:
        time.sleep(self.base_delay + random.uniform(0.3, 0.9) + extra)

    def _get(self, url: str, **kwargs) -> requests.Response | None:
        self._sleep()
        try:
            self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
            r = self.session.get(url, timeout=20, **kwargs)
            if r.status_code == 429:
                self.log.warning("Rate-limited (429) — sleeping 20 s")
                time.sleep(20)
                return None
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            self.log.warning(f"GET {url[:80]} → {exc}")
            return None

    def _get_json(self, url: str, **kwargs) -> dict | list | None:
        r = self._get(url, **kwargs)
        if r is None:
            return None
        try:
            return r.json()
        except ValueError:
            self.log.warning(f"Non-JSON from {url[:80]}")
            return None

    @abstractmethod
    def scrape(self) -> list[JobListing]:
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Scrapers
# ─────────────────────────────────────────────────────────────────────────────

class WeWorkRemotelyScraper(BaseJobScraper):
    """RSS feeds — very reliable, no JS required."""
    name = "wwr"
    FEEDS = [
        "https://weworkremotely.com/categories/remote-machine-learning-ai-jobs.rss",
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/remote-jobs/search.rss?term=machine+learning",
        "https://weworkremotely.com/remote-jobs/search.rss?term=data+science",
        "https://weworkremotely.com/remote-jobs/search.rss?term=AI+engineer",
    ]
    ML_TERMS = {"machine learning", "ml", "ai", "data science", "deep learning",
                "llm", "nlp", "neural", "pytorch", "tensorflow", "computer vision"}

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for feed_url in self.FEEDS:
            resp = self._get(feed_url, headers={"Accept": "application/rss+xml, application/xml, text/xml, */*"})
            if not resp:
                continue
            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as exc:
                self.log.warning(f"RSS parse error: {exc}")
                continue
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc_raw = (item.findtext("description") or "").strip()
                company_el = item.find("{https://weworkremotely.com}company_name")
                company = (company_el.text if company_el is not None else "").strip()
                region = (item.findtext("region") or "Remote").strip()
                if not company:
                    # WWR title formats:
                    # "Anywhere: ContentJet Inc. - Automation Engineer"
                    # "ContentJet Inc.: Automation & Integration Engineer"
                    # "Automation Engineer at ContentJet Inc."
                    _JOB_WORDS = {
                        "engineer", "developer", "scientist", "researcher",
                        "analyst", "designer", "intern", "architect",
                        "senior", "junior", "backend", "frontend", "full-stack",
                        "machine learning", "data", "software", "devops",
                    }
                    if ": " in title and " - " in title:
                        _, rest = title.split(": ", 1)
                        parts = rest.split(" - ", 1)
                        company = parts[0].strip()
                        title = parts[1].strip() if len(parts) > 1 else rest
                    elif ": " in title:
                        left, right = title.split(": ", 1)
                        # If left looks like a job title (contains job words), swap
                        left_lower = left.lower()
                        if any(w in left_lower for w in _JOB_WORDS):
                            company = right.strip()
                            title = left.strip()
                        else:
                            company = left.strip()
                            title = right.strip()
                    elif " at " in title:
                        parts = title.split(" at ", 1)
                        company = parts[1].strip()
                        title = parts[0].strip()
                    else:
                        company = "Unknown"
                desc = BeautifulSoup(desc_raw, "lxml").get_text(" ")
                combined = (title + " " + desc).lower()
                if not any(t in combined for t in self.ML_TERMS):
                    continue
                if link in seen:
                    continue
                seen.add(link)
                results.append(JobListing(
                    company=company, title=title,
                    location=region or "Remote", description=desc,
                    apply_url=link, source="We Work Remotely",
                    remote_chance="Fully Remote (High)",
                ))
        self.log.info(f"{len(results)} listings")
        return results


class TheMuseScraper(BaseJobScraper):
    """Public JSON API — highly reliable."""
    name = "muse"
    API = "https://www.themuse.com/api/public/jobs"
    CATEGORIES = ["Software Engineer", "Data Science", "Data Analyst", "IT"]
    TARGET_LOCS = {"france", "germany", "uk", "netherlands", "switzerland",
                   "belgium", "canada", "remote", "flexible"}

    def _fetch_page(self, category: str, level: str, page: int) -> list[dict]:
        data = self._get_json(
            self.API,
            params={"category": category, "level": level,
                    "page": page, "descending": "true"},
        )
        if not data or not isinstance(data, dict):
            return []
        return data.get("results", [])

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        # Also search without level filter to catch more EU/remote listings
        search_configs = [
            (cat, "Internship") for cat in self.CATEGORIES
        ] + [
            (cat, "") for cat in ["Data Science", "Software Engineer"]
        ]
        for cat, level in search_configs:
            for page in range(3):
                items = self._fetch_page(cat, level, page)
                if not items:
                    break
                for job in items:
                    if not isinstance(job, dict):
                        continue
                    url = job.get("refs", {}).get("landing_page_url", "")
                    if url in seen:
                        continue
                    company = job.get("company", {}).get("name", "Unknown")
                    title = job.get("name", "")
                    desc = BeautifulSoup(job.get("contents", ""), "lxml").get_text(" ")
                    locations = job.get("locations", [])
                    location = ", ".join(
                        loc.get("name", "") for loc in locations
                        if isinstance(loc, dict)
                    ) or "Remote/Flexible"
                    combined = (title + " " + desc).lower()
                    if not any(t in combined for t in ["machine", "ml", "ai", "data", "learn", "neural", "nlp"]):
                        continue
                    seen.add(url)
                    results.append(JobListing(
                        company=company, title=title, location=location,
                        description=desc, apply_url=url, source="The Muse",
                    ))
                if len(items) < 10:
                    break
        self.log.info(f"{len(results)} listings")
        return results


class RemoteOKScraper(BaseJobScraper):
    """Public JSON API — reliable for remote ML roles."""
    name = "remoteok"
    API = "https://remoteok.com/api"
    TAGS = ["machine-learning", "ai", "data-science", "nlp", "deep-learning",
            "pytorch", "tensorflow", "llm", "computer-vision"]
    ML_TERMS = {"machine learning", "ml", "ai", "data science", "neural",
                "llm", "nlp", "deep learning", "computer vision"}
    INTERN_TERMS = {"intern", "internship", "stage", "praktikum", "student",
                    "junior", "entry level", "entry-level", "graduate"}

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for tag in self.TAGS[:6]:
            data = self._get_json(
                f"{self.API}?tag={tag}",
                headers={"User-Agent": random.choice(USER_AGENTS)},
            )
            if not data or not isinstance(data, list):
                continue
            for job in data:
                if not isinstance(job, dict) or not job.get("position"):
                    continue
                url = job.get("url", "")
                if url in seen:
                    continue
                title = job.get("position", "")
                company = job.get("company", "Unknown")
                desc_raw = job.get("description", "") or ""
                desc = BeautifulSoup(desc_raw, "lxml").get_text(" ") if desc_raw else ""
                location = job.get("location", "Remote") or "Remote"
                tags_list = job.get("tags", []) or []
                tag_str = " ".join(tags_list) if isinstance(tags_list, list) else ""
                combined = (title + " " + desc + " " + tag_str).lower()
                if not any(t in combined for t in self.ML_TERMS):
                    continue
                # Require intern signal in title OR (description + tags)
                title_lower = title.lower()
                has_intern_in_title = any(t in title_lower for t in self.INTERN_TERMS)
                has_intern_in_desc = any(t in (desc + " " + tag_str).lower() for t in self.INTERN_TERMS)
                if not (has_intern_in_title or has_intern_in_desc):
                    continue
                # Exclude obviously senior roles
                if any(t in title_lower for t in ["senior", "staff", "principal", "director", "vp ", "head of", "manager", "lead "]):
                    continue
                seen.add(url)
                results.append(JobListing(
                    company=company, title=title,
                    location=location, description=desc + " " + tag_str,
                    apply_url=url or f"https://remoteok.com",
                    source="Remote OK",
                    remote_chance="Fully Remote (High)",
                ))
        self.log.info(f"{len(results)} listings")
        return results


class WelcomeToTheJungleScraper(BaseJobScraper):
    """WTTJ — top European job board for tech startups."""
    name = "wttj"
    BASE = "https://www.welcometothejungle.com"
    QUERIES = [
        "machine learning intern",
        "AI intern",
        "data science stage",
        "NLP intern",
        "agentic AI",
        "deep learning intern",
        "MLOps intern",
    ]

    def _search(self, query: str) -> list[JobListing]:
        params = {
            "query": query,
            "refinementList[contract_type_names.en][]": "Internship",
        }
        resp = self._get(f"{self.BASE}/en/jobs", params=params)
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results: list[JobListing] = []

        # Try Next.js data
        for script in soup.select("script#__NEXT_DATA__"):
            try:
                data = json.loads(script.string or "")
                jobs = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("jobs", [])
                )
                for job in jobs:
                    if not isinstance(job, dict):
                        continue
                    title = job.get("name", "")
                    org = job.get("organization", {})
                    company = org.get("name", "Unknown") if isinstance(org, dict) else "Unknown"
                    office = job.get("office", {})
                    city = office.get("city", "") if isinstance(office, dict) else ""
                    country = office.get("country", {})
                    country_name = country.get("name", "") if isinstance(country, dict) else ""
                    location = f"{city}, {country_name}".strip(", ")
                    slug = job.get("slug", "")
                    org_slug = org.get("slug", "") if isinstance(org, dict) else ""
                    url = f"{self.BASE}/en/companies/{org_slug}/jobs/{slug}" if slug else ""
                    desc = job.get("description", "")
                    results.append(JobListing(
                        company=company, title=title,
                        location=location or "France",
                        description=desc, apply_url=url,
                        source="Welcome to the Jungle",
                    ))
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        # Fallback: HTML card extraction
        if not results:
            for card in soup.select("li[data-testid], article[class*='Job'], div[class*='JobCard']")[:30]:
                title_el = card.select_one("h2, h3, [data-testid*='title'], [class*='title']")
                company_el = card.select_one("[class*='company'], [data-testid*='company']")
                location_el = card.select_one("[class*='location'], [data-testid*='location']")
                link_el = card.select_one("a[href]")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                location = location_el.get_text(strip=True) if location_el else "France"
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"{self.BASE}{href}"
                results.append(JobListing(
                    company=company, title=title, location=location,
                    description=card.get_text(" ", strip=True),
                    apply_url=href, source="Welcome to the Jungle",
                ))
        return results

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for q in self.QUERIES[:5]:
            for job in self._search(q):
                key = job.apply_url or (job.company + job.title)
                if key not in seen:
                    seen.add(key)
                    results.append(job)
        self.log.info(f"{len(results)} listings")
        return results


class WellfoundScraper(BaseJobScraper):
    """Wellfound (AngelList Talent) — startup ML/AI jobs."""
    name = "wellfound"
    SEARCH_URL = "https://wellfound.com/jobs"

    def _scrape_html(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for q in ["machine learning intern", "AI intern remote", "data science intern"]:
            resp = self._get(
                self.SEARCH_URL,
                params={"q": q, "remote": "true"},
            )
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select("div[class*='job'], li[class*='job'], article")[:20]:
                title_el = card.select_one("h2, h3, a[class*='title']")
                company_el = card.select_one("[class*='company']")
                location_el = card.select_one("[class*='location']")
                link_el = card.select_one("a[href]")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Startup"
                location = location_el.get_text(strip=True) if location_el else "Remote"
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://wellfound.com{href}"
                key = href or (company + title)
                if key not in seen:
                    seen.add(key)
                    results.append(JobListing(
                        company=company, title=title, location=location,
                        description=card.get_text(" ", strip=True),
                        apply_url=href, source="Wellfound",
                        company_type="Startup",
                    ))
        return results

    def _scrape_playwright(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        queries = ["machine learning intern", "AI intern", "data science intern"]
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=random.choice(USER_AGENTS))
                page = ctx.new_page()
                for q in queries[:2]:
                    url = f"https://wellfound.com/jobs?q={quote_plus(q)}&remote=true"
                    try:
                        page.goto(url, timeout=30000)
                        page.wait_for_load_state("networkidle", timeout=15000)
                        time.sleep(2)
                        cards = page.query_selector_all(
                            "div[class*='job'], li[class*='job'], article"
                        )
                        for card in cards[:25]:
                            text = card.inner_text()
                            link_el = card.query_selector("a[href]")
                            href = link_el.get_attribute("href") if link_el else ""
                            if href and not href.startswith("http"):
                                href = f"https://wellfound.com{href}"
                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            title = lines[0] if lines else "Unknown"
                            company = lines[1] if len(lines) > 1 else "Startup"
                            key = href or (company + title)
                            if key not in seen:
                                seen.add(key)
                                results.append(JobListing(
                                    company=company, title=title, location="Remote",
                                    description=text, apply_url=href,
                                    source="Wellfound", company_type="Startup",
                                ))
                    except Exception as exc:
                        self.log.warning(f"Wellfound PW timeout/error: {exc}")
                    time.sleep(2)
                browser.close()
        except Exception as exc:
            self.log.warning(f"Playwright failed: {exc}")
        return results

    def scrape(self) -> list[JobListing]:
        results = self._scrape_playwright() if _HAS_PLAYWRIGHT else self._scrape_html()
        self.log.info(f"{len(results)} listings")
        return results


class LinkedInScraper(BaseJobScraper):
    """LinkedIn public job search (rate-limited — do not abuse)."""
    name = "linkedin"
    BASE = "https://www.linkedin.com/jobs/search/"
    QUERIES = [
        ("machine learning intern", "France"),
        ("AI intern", "Germany"),
        ("data science intern", "Netherlands"),
        ("machine learning internship", "Canada"),
        ("agentic AI intern", "Europe"),
        ("ML engineer intern", "Remote"),
        ("stage machine learning", "France"),
        ("praktikum machine learning", "Germany"),
    ]

    def _search(self, query: str, location: str) -> list[JobListing]:
        params = {
            "keywords": query,
            "location": location,
            "f_JT": "I",       # Internship
            "f_TP": "1,2,3",   # Posted in last month
        }
        resp = self._get(self.BASE, params=params)
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        selectors = [
            "div.job-search-card",
            "li.jobs-search__results-list-item",
            "div.base-card",
        ]
        cards = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                break
        for card in cards[:20]:
            title_el = card.select_one("h3.base-search-card__title, h3, .job-title")
            company_el = card.select_one("h4.base-search-card__subtitle, .company")
            location_el = card.select_one("span.job-search-card__location, .location")
            link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
            if not title_el or not link_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            loc = location_el.get_text(strip=True) if location_el else location
            href = link_el.get("href", "").split("?")[0]
            results.append(JobListing(
                company=company, title=title, location=loc,
                description=card.get_text(" ", strip=True),
                apply_url=href, source="LinkedIn",
            ))
        return results

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for query, location in self.QUERIES[:5]:
            for job in self._search(query, location):
                key = job.apply_url or (job.company + job.title)
                if key not in seen:
                    seen.add(key)
                    results.append(job)
            time.sleep(random.uniform(3, 6))
        self.log.info(f"{len(results)} listings")
        return results


class IndeedScraper(BaseJobScraper):
    """Indeed — multiple country domains."""
    name = "indeed"
    SITES: dict[str, list[str]] = {
        "fr.indeed.com": ["machine learning stagiaire", "stage data scientist"],
        "de.indeed.com": ["machine learning praktikum", "KI Praktikum"],
        "indeed.com": ["machine learning intern remote", "AI intern Europe"],
        "ca.indeed.com": ["machine learning intern", "AI intern Canada"],
        "uk.indeed.com": ["machine learning intern London", "AI intern UK"],
    }

    def _search(self, domain: str, query: str) -> list[JobListing]:
        resp = self._get(
            f"https://{domain}/jobs",
            params={"q": query, "sort": "date", "fromage": "30", "limit": "25"},
        )
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for card in soup.select(
            "div.job_seen_beacon, li.css-5lfssm, div[class*='result']"
        )[:25]:
            title_el = card.select_one("h2.jobTitle, a[data-testid='job-title'], h2 span")
            company_el = card.select_one("[data-testid='company-name'], .companyName")
            location_el = card.select_one("[data-testid='job-location'], .companyLocation")
            link_el = card.select_one("a[data-jk], a[id^='job_']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            loc = location_el.get_text(strip=True) if location_el else domain.split(".")[0].upper()
            data_jk = link_el.get("data-jk", "") if link_el else ""
            href = f"https://{domain}/viewjob?jk={data_jk}" if data_jk else ""
            if not href and link_el:
                href = urljoin(f"https://{domain}", link_el.get("href", ""))
            results.append(JobListing(
                company=company, title=title, location=loc,
                description=card.get_text(" ", strip=True),
                apply_url=href, source=f"Indeed ({domain})",
            ))
        return results

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for domain, queries in list(self.SITES.items())[:4]:
            for q in queries[:2]:
                for job in self._search(domain, q):
                    key = job.apply_url or (job.company + job.title)
                    if key not in seen:
                        seen.add(key)
                        results.append(job)
        self.log.info(f"{len(results)} listings")
        return results


class XINGScraper(BaseJobScraper):
    """XING — Germany's major professional/job platform."""
    name = "xing"
    BASE = "https://www.xing.com"
    QUERIES = [
        "machine learning praktikum",
        "KI Praktikum",
        "data science praktikum",
        "AI intern Germany",
        "deep learning praktikum",
    ]

    def _search(self, query: str) -> list[JobListing]:
        resp = self._get(
            f"{self.BASE}/jobs/search",
            params={"keywords": query, "location": "Deutschland,Österreich,Schweiz"},
        )
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for card in soup.select("article[class*='job'], div[class*='JobCard'], li[class*='job']")[:20]:
            title_el = card.select_one("h2, h3, [class*='title']")
            company_el = card.select_one("[class*='company'], [class*='employer']")
            location_el = card.select_one("[class*='location'], [class*='city']")
            link_el = card.select_one("a[href]")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            loc = location_el.get_text(strip=True) if location_el else "Germany"
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = f"{self.BASE}{href}"
            results.append(JobListing(
                company=company, title=title, location=loc or "Germany",
                description=card.get_text(" ", strip=True),
                apply_url=href, source="XING",
            ))
        return results

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for q in self.QUERIES[:4]:
            for job in self._search(q):
                key = job.apply_url or (job.company + job.title)
                if key not in seen:
                    seen.add(key)
                    results.append(job)
        self.log.info(f"{len(results)} listings")
        return results


class BuiltInScraper(BaseJobScraper):
    """Built In — remote ML/AI jobs."""
    name = "builtin"
    BASE = "https://builtin.com"
    PATHS = [
        "/jobs/machine-learning?remote=true",
        "/jobs/dev-engineering?remote=true&search=AI+intern",
        "/jobs/data-science?remote=true",
        "/jobs/machine-learning",
    ]

    def _fetch_page(self, path: str) -> list[JobListing]:
        resp = self._get(f"{self.BASE}{path}")
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        ML_TERMS = {"machine learning", "ml", "ai", "data science", "neural", "llm", "nlp"}
        for card in soup.select(
            "article[class*='job'], div[class*='JobCard'], "
            "li[class*='job-listing'], div[data-id='job-card']"
        )[:30]:
            title_el = card.select_one("h2, h3, a[data-id='job-card-title']")
            company_el = card.select_one("[class*='company'], [data-id='company-title']")
            location_el = card.select_one("[class*='location'], [class*='remote']")
            link_el = card.select_one("a[href*='/jobs/']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            loc = location_el.get_text(strip=True) if location_el else "Remote"
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = f"{self.BASE}{href}"
            desc = card.get_text(" ", strip=True)
            if not any(t in desc.lower() for t in ML_TERMS):
                continue
            results.append(JobListing(
                company=company, title=title, location=loc,
                description=desc, apply_url=href, source="Built In",
            ))
        return results

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for path in self.PATHS:
            for job in self._fetch_page(path):
                key = job.apply_url or (job.company + job.title)
                if key not in seen:
                    seen.add(key)
                    results.append(job)
        self.log.info(f"{len(results)} listings")
        return results


class WhatJobsScraper(BaseJobScraper):
    """WhatJobs — global aggregator."""
    name = "whatjobs"
    BASE = "https://www.whatjobs.com"
    PATHS = [
        "/jobs/machine-learning/internship/",
        "/jobs/machine-learning/intern/remote/",
        "/jobs/ai-intern/remote/",
        "/jobs/data-science/internship/",
    ]

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for path in self.PATHS:
            resp = self._get(f"{self.BASE}{path}")
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select(
                "div.job, article.job, div[class*='job-listing'], li.job-item"
            )[:25]:
                title_el = card.select_one("h2, h3, .job-title, a[class*='title']")
                company_el = card.select_one(".company, .employer, [class*='company']")
                location_el = card.select_one(".location, [class*='location']")
                link_el = card.select_one("a[href]")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                loc = location_el.get_text(strip=True) if location_el else "Remote"
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = urljoin(self.BASE, href)
                key = href or (company + title)
                if key not in seen:
                    seen.add(key)
                    results.append(JobListing(
                        company=company, title=title, location=loc,
                        description=card.get_text(" ", strip=True),
                        apply_url=href, source="WhatJobs",
                    ))
        self.log.info(f"{len(results)} listings")
        return results


class MoovijobScraper(BaseJobScraper):
    """Moovijob — French job board for students."""
    name = "moovijob"
    BASE = "https://www.moovijob.com"
    QUERIES = ["machine learning", "data science", "intelligence artificielle", "AI engineer"]

    def _search(self, query: str) -> list[JobListing]:
        resp = self._get(
            f"{self.BASE}/recherche",
            params={"q": query, "contract[]": ["INTERNSHIP", "APPRENTICESHIP"]},
        )
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for card in soup.select("article.job, div.job-card, li.offer, div[class*='offer']")[:20]:
            title_el = card.select_one("h2, h3, .offer-title, a[class*='title']")
            company_el = card.select_one(".company, .employer, [class*='company']")
            location_el = card.select_one(".location, .city, [class*='location']")
            link_el = card.select_one("a[href]")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            loc = location_el.get_text(strip=True) if location_el else "France"
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = f"{self.BASE}{href}"
            results.append(JobListing(
                company=company, title=title, location=loc or "France",
                description=card.get_text(" ", strip=True),
                apply_url=href, source="Moovijob",
            ))
        return results

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for q in self.QUERIES[:3]:
            for job in self._search(q):
                key = job.apply_url or (job.company + job.title)
                if key not in seen:
                    seen.add(key)
                    results.append(job)
        self.log.info(f"{len(results)} listings")
        return results


class EURESScraper(BaseJobScraper):
    """EURES — European Employment Services portal."""
    name = "eures"
    QUERIES = [
        "machine learning intern",
        "data science internship",
        "AI intern",
        "NLP intern",
        "ML stage",
    ]

    def _search_html(self, query: str) -> list[JobListing]:
        url = f"https://eures.europa.eu/en/jobs"
        resp = self._get(url, params={"query": query})
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for card in soup.select(
            "article, div[class*='job-card'], div[class*='job-item'], li[class*='job']"
        )[:20]:
            title_el = card.select_one("h2, h3, .job-title, .title, [class*='title']")
            company_el = card.select_one(".company-name, .employer, .organisation, [class*='company']")
            location_el = card.select_one(".location, .country, [class*='location']")
            link_el = card.select_one("a[href]")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            loc = location_el.get_text(strip=True) if location_el else "Europe"
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = urljoin("https://eures.europa.eu", href)
            results.append(JobListing(
                company=company, title=title, location=loc,
                description=card.get_text(" ", strip=True),
                apply_url=href, source="EURES",
            ))
        return results

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for q in self.QUERIES[:3]:
            for job in self._search_html(q):
                key = job.apply_url or (job.company + job.title)
                if key not in seen:
                    seen.add(key)
                    results.append(job)
        self.log.info(f"{len(results)} listings")
        return results


class JoinrsScraper(BaseJobScraper):
    """Joinrs — student-focused European job platform."""
    name = "joinrs"
    BASE = "https://www.joinrs.com"
    QUERIES = ["machine learning intern", "AI intern", "data science intern"]

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for q in self.QUERIES[:2]:
            resp = self._get(
                f"{self.BASE}/en/jobs/search/",
                params={"query": q},
            )
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select("div.job-card, article, li[class*='job']")[:25]:
                title_el = card.select_one("h2, h3, .title, a[class*='title']")
                company_el = card.select_one(".company, [class*='company']")
                location_el = card.select_one(".location, [class*='location']")
                link_el = card.select_one("a[href]")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                loc = location_el.get_text(strip=True) if location_el else "Europe"
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = urljoin(self.BASE, href)
                key = href or (company + title)
                if key not in seen:
                    seen.add(key)
                    results.append(JobListing(
                        company=company, title=title, location=loc,
                        description=card.get_text(" ", strip=True),
                        apply_url=href, source="Joinrs",
                    ))
        self.log.info(f"{len(results)} listings")
        return results


class OttaScraper(BaseJobScraper):
    """Otta (Reed Talent) — European tech job board."""
    name = "otta"
    BASE = "https://app.otta.com"

    def scrape(self) -> list[JobListing]:
        if not _HAS_PLAYWRIGHT:
            return []
        results: list[JobListing] = []
        seen: set[str] = set()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=random.choice(USER_AGENTS))
                page = ctx.new_page()
                for q in ["machine learning intern", "AI intern", "data science"]:
                    url = f"{self.BASE}/jobs/search?q={quote_plus(q)}&jobType=INTERNSHIP"
                    try:
                        page.goto(url, timeout=30000)
                        page.wait_for_load_state("networkidle", timeout=15000)
                        time.sleep(3)
                        cards = page.query_selector_all("li, article, div[class*='job']")
                        for card in cards[:25]:
                            text = card.inner_text()
                            link_el = card.query_selector("a[href]")
                            href = link_el.get_attribute("href") if link_el else ""
                            if href and not href.startswith("http"):
                                href = f"{self.BASE}{href}"
                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            if not lines:
                                continue
                            title = lines[0]
                            company = lines[1] if len(lines) > 1 else "Unknown"
                            key = href or (company + title)
                            if key not in seen and len(title) > 3:
                                seen.add(key)
                                results.append(JobListing(
                                    company=company, title=title, location="Europe",
                                    description=text, apply_url=href, source="Otta",
                                ))
                    except Exception as exc:
                        self.log.warning(f"Otta error: {exc}")
                    time.sleep(2)
                browser.close()
        except Exception as exc:
            self.log.warning(f"Otta Playwright failed: {exc}")
        self.log.info(f"{len(results)} listings")
        return results


class NextStationScraper(BaseJobScraper):
    """Next Station — international tech internships."""
    name = "nextstation"
    BASE = "https://nextstation.app"

    def scrape(self) -> list[JobListing]:
        results: list[JobListing] = []
        seen: set[str] = set()
        for q in ["machine learning", "AI intern", "data science"]:
            resp = self._get(
                f"{self.BASE}/jobs",
                params={"q": q, "type": "internship"},
            )
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select("article, div[class*='job'], li[class*='job']")[:20]:
                title_el = card.select_one("h2, h3, [class*='title']")
                company_el = card.select_one("[class*='company']")
                location_el = card.select_one("[class*='location']")
                link_el = card.select_one("a[href]")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                loc = location_el.get_text(strip=True) if location_el else "Europe"
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = urljoin(self.BASE, href)
                key = href or (company + title)
                if key not in seen:
                    seen.add(key)
                    results.append(JobListing(
                        company=company, title=title, location=loc,
                        description=card.get_text(" ", strip=True),
                        apply_url=href, source="Next Station",
                    ))
        self.log.info(f"{len(results)} listings")
        return results


# ── output writers ─────────────────────────────────────────────────────────────

def write_csv(path: Path, listings: list[JobListing]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for j in listings:
            writer.writerow({
                "Company": j.company,
                "Type": j.company_type,
                "Location": j.location,
                "Remote/Hybrid Chance": j.remote_chance,
                "Contact Email": j.contact_email,
                "Careers / Apply Link": j.apply_url,
                "Notes for 2nd-year ML/DS Student": j.notes,
                "CV Match Score (1-10)": j.match_score,
                "Why it matches your CV": j.why_matches,
                "Source": j.source,
            })


def write_html(path: Path, listings: list[JobListing], cv_path: Path) -> None:
    top20 = listings[:20]

    def score_color(s: int) -> str:
        if s >= 8:
            return "#22c55e"
        if s >= 5:
            return "#f59e0b"
        return "#6b7280"

    rows_html = "".join(
        f"""<tr>
          <td class="rank">{i}</td>
          <td><strong>{html_lib.escape(j.company)}</strong><br>
              <small style="color:#64748b">{html_lib.escape(j.company_type)}</small></td>
          <td>{html_lib.escape(j.title)}</td>
          <td>{html_lib.escape(j.location)}</td>
          <td>{html_lib.escape(j.remote_chance)}</td>
          <td><span class="score" style="background:{score_color(j.match_score)}">{j.match_score}/10</span></td>
          <td style="font-size:0.8rem">{html_lib.escape(j.why_matches)}</td>
          <td style="font-size:0.8rem">{html_lib.escape(j.notes)}</td>
          <td><a href="{html_lib.escape(j.apply_url)}" target="_blank" rel="noopener">Apply →</a></td>
          <td><small>{html_lib.escape(j.source)}</small></td>
        </tr>"""
        for i, j in enumerate(top20, 1)
    )

    source_counts: dict[str, int] = {}
    for j in listings:
        source_counts[j.source] = source_counts.get(j.source, 0) + 1
    source_rows = "".join(
        f"<tr><td>{html_lib.escape(src)}</td><td>{cnt}</td></tr>"
        for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1])
    )

    strong_matches = sum(1 for j in listings if j.match_score >= 8)
    good_matches = sum(1 for j in listings if j.match_score >= 5)
    remote_friendly = sum(1 for j in listings if "Remote" in j.remote_chance)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Internship Report — {date.today().isoformat()}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
  h1 {{ color: #38bdf8; margin-bottom: 6px; font-size: 1.6rem; }}
  h2 {{ color: #94a3b8; border-bottom: 1px solid #334155; padding-bottom: 8px; margin: 28px 0 14px; }}
  .meta {{ color: #64748b; font-size: 0.8rem; margin-bottom: 20px; }}
  .stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 28px; }}
  .stat {{ background: #1e293b; border-radius: 10px; padding: 14px 20px; min-width: 130px; text-align: center; }}
  .stat-num {{ font-size: 1.6rem; font-weight: 700; color: #38bdf8; }}
  .stat-label {{ font-size: 0.75rem; color: #64748b; margin-top: 2px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.82rem; overflow-x: auto; display: block; }}
  th {{ background: #1e293b; color: #94a3b8; padding: 10px 12px; text-align: left; white-space: nowrap; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; vertical-align: top; }}
  tr:hover td {{ background: #1e293b33; }}
  .rank {{ font-weight: bold; color: #38bdf8; white-space: nowrap; }}
  .score {{ display: inline-block; padding: 2px 10px; border-radius: 999px; color: #fff; font-weight: 700; }}
  a {{ color: #38bdf8; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>AI/ML/DS Internship Hunt — Summer 2026</h1>
<p class="meta">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | CV: {html_lib.escape(str(cv_path))} | Total: {len(listings)} listings</p>
<div class="stats">
  <div class="stat"><div class="stat-num">{len(listings)}</div><div class="stat-label">Total Listings</div></div>
  <div class="stat"><div class="stat-num">{strong_matches}</div><div class="stat-label">Strong Matches 8–10</div></div>
  <div class="stat"><div class="stat-num">{good_matches}</div><div class="stat-label">Good Matches 5+</div></div>
  <div class="stat"><div class="stat-num">{remote_friendly}</div><div class="stat-label">Remote Friendly</div></div>
</div>
<h2>Top 20 Matches</h2>
<table>
<thead><tr>
  <th>#</th><th>Company</th><th>Role</th><th>Location</th><th>Remote?</th>
  <th>Score</th><th>Why It Matches</th><th>Notes</th><th>Apply</th><th>Source</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<h2>Listings by Source</h2>
<table>
<thead><tr><th>Source</th><th>Listings Found</th></tr></thead>
<tbody>{source_rows}</tbody>
</table>
<p class="meta" style="margin-top:20px">Full {len(listings)} listings in the CSV. Apply top matches first — aim for score ≥ 7.</p>
</body>
</html>"""
    path.write_text(html_content, encoding="utf-8")


# ── registry ───────────────────────────────────────────────────────────────────

ALL_SCRAPERS: list[type[BaseJobScraper]] = [
    WeWorkRemotelyScraper,   # name = wwr
    TheMuseScraper,          # name = muse
    RemoteOKScraper,         # name = remoteok
    WelcomeToTheJungleScraper,  # name = wttj
    WellfoundScraper,        # name = wellfound
    LinkedInScraper,         # name = linkedin
    IndeedScraper,           # name = indeed
    XINGScraper,             # name = xing
    BuiltInScraper,          # name = builtin
    WhatJobsScraper,         # name = whatjobs
    MoovijobScraper,         # name = moovijob
    EURESScraper,            # name = eures
    JoinrsScraper,           # name = joinrs
    OttaScraper,             # name = otta
    NextStationScraper,      # name = nextstation
]
SCRAPER_MAP = {cls.name: cls for cls in ALL_SCRAPERS}


# ── pipeline ───────────────────────────────────────────────────────────────────

def run_scrapers(
    sources: list[str] | None,
    session: requests.Session,
    use_playwright: bool,
) -> list[JobListing]:
    selected = [SCRAPER_MAP[s] for s in sources] if sources else ALL_SCRAPERS
    all_listings: list[JobListing] = []
    for cls in selected:
        log.info(f"Running scraper: {cls.name} ...")
        try:
            scraper = cls(session)
            if not use_playwright and cls in (WellfoundScraper, OttaScraper):
                listings = (
                    scraper._scrape_html()
                    if hasattr(scraper, "_scrape_html")
                    else []
                )
            else:
                listings = scraper.scrape()
            all_listings.extend(listings)
        except Exception as exc:
            log.error(f"Scraper {cls.name} failed: {exc}", exc_info=False)
    return all_listings


def deduplicate(listings: list[JobListing]) -> list[JobListing]:
    seen_urls: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    unique: list[JobListing] = []
    for j in listings:
        url_key = j.apply_url.split("?")[0].rstrip("/") if j.apply_url else ""
        pair_key = (
            re.sub(r"\s+", " ", j.company.lower().strip()),
            re.sub(r"\s+", " ", j.title.lower().strip()),
        )
        if url_key and url_key in seen_urls:
            continue
        if pair_key in seen_pairs:
            continue
        if url_key:
            seen_urls.add(url_key)
        seen_pairs.add(pair_key)
        unique.append(j)
    return unique


_SENIOR_SIGNALS = frozenset([
    "senior", "staff ", "principal", "director", "vp ", "head of",
    "chief ", "president", "partner ", "lead engineer", "lead developer",
    "engineering manager", "product manager",
])


def enrich(listings: list[JobListing], cv: CVProfile) -> list[JobListing]:
    result: list[JobListing] = []
    for j in listings:
        # Drop obviously senior/management roles (check both title and company field)
        combined_check = (j.title + " " + j.company).lower()
        if any(sig in combined_check for sig in _SENIOR_SIGNALS):
            continue
        if not j.remote_chance or j.remote_chance == "Unknown":
            j.remote_chance = infer_remote_chance(j.description + " " + j.location)
        if j.company_type == "Company":
            j.company_type = infer_company_type(j.company, j.description)
        j.match_score, j.why_matches, j.notes = score_listing(j, cv)
        result.append(j)
    return result


# ── entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape AI/ML/DS internships (Western Europe + Canada, Summer 2026)"
    )
    parser.add_argument("--cv", type=Path, default=Path("cv.pdf"),
                        help="Path to your CV PDF (default: cv.pdf)")
    parser.add_argument("--output", type=Path, default=Path("scraped_internships.csv"))
    parser.add_argument("--html", type=Path, default=Path("report.html"))
    parser.add_argument("--max", type=int, default=500,
                        help="Max listings to keep in output (default: 500)")
    parser.add_argument("--min-score", type=int, default=2,
                        help="Drop listings below this CV match score (default: 2)")
    parser.add_argument("--no-playwright", action="store_true",
                        help="Skip Playwright-based scrapers (Wellfound, Otta)")
    parser.add_argument(
        "--sources", type=str, default=None,
        help=(
            "Comma-separated subset of sources. "
            f"Available: {', '.join(SCRAPER_MAP.keys())}"
        ),
    )
    args = parser.parse_args()

    if not args.cv.exists():
        raise SystemExit(f"CV not found: {args.cv}  —  pass --cv path/to/cv.pdf")

    log.info(f"Reading CV: {args.cv}")
    cv_text = extract_pdf_text(args.cv)
    cv = CVProfile.from_text(cv_text)
    log.info(f"CV keywords detected: {', '.join(sorted(cv.keywords)[:20])}{'...' if len(cv.keywords) > 20 else ''}")
    log.info(f"Top skills (by weight): {', '.join(cv.top_skills[:10])}")

    sources: list[str] | None = (
        [s.strip() for s in args.sources.split(",")] if args.sources else None
    )
    use_playwright = _HAS_PLAYWRIGHT and not args.no_playwright
    if not _HAS_PLAYWRIGHT and not args.no_playwright:
        log.info("Playwright not available — Wellfound/Otta will use HTML fallback")

    session = make_session()

    log.info("Scraping job boards ...")
    raw = run_scrapers(sources, session, use_playwright)
    log.info(f"Raw listings: {len(raw)}")

    unique = deduplicate(raw)
    log.info(f"After dedup: {len(unique)}")

    enriched = enrich(unique, cv)

    final = sorted(
        [j for j in enriched if j.match_score >= args.min_score],
        key=lambda j: j.match_score,
        reverse=True,
    )[: args.max]
    log.info(f"Final listings (score ≥ {args.min_score}): {len(final)}")

    write_csv(args.output, final)
    log.info(f"CSV  → {args.output}")

    write_html(args.html, final, args.cv)
    log.info(f"HTML → {args.html}")

    if final:
        log.info("─── Top 5 matches ───")
        for i, j in enumerate(final[:5], 1):
            log.info(f"  {i}. [{j.match_score}/10] {j.company} | {j.title} | {j.source}")

    log.info(f"Done — {len(final)} listings saved to {args.output}")


if __name__ == "__main__":
    main()
