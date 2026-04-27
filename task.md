You are an expert Python scraping + AI-matching engineer. Build a complete, production-ready Python script (Python 3.11+) that scrapes AI/ML/Data Science/Agentic AI summer 2026 internships across Western Europe (France, Germany, UK, Netherlands, Switzerland, Belgium, Sweden, etc.) + Canada.

**Core requirements:**
1. **Input**: The user will provide a file called `cv.pdf`. 
   - Use pdfplumber or PyMuPDF to extract full text.
   - Automatically extract key skills, experience, projects, and keywords (e.g., Machine Learning, Data Science, PyTorch, TensorFlow, Agentic AI, RAG, LLMs, Python, part-time ML experience, 2nd-year Software Engineering student, etc.).
   - Create a keyword vector or embedding for matching.

2. **Target job boards** (scrape or search intelligently):
   - Welcome to the Jungle (welcometothejungle.com) – France/Europe focus
   - Otta (otta.com)
   - The Muse (themuse.com)
   - Moovijob (moovijob.com)
   - Joinrs (joinrs.com)
   - Next Station (nextstation.app or similar)
   - Wellfound / AngelList Talent (wellfound.com)
   - Built In (builtin.com – EU sections)
   - We Work Remotely (weworkremotely.com)
   - LinkedIn Jobs (linkedin.com/jobs) – use public search or API if possible
   - XING (xing.com/jobs) – Germany focus
   - EURES (eures.europa.eu)
   - Indeed (indeed.com or country versions)
   - WhatJobs (whatjobs.com)
3. **Search filters** (for every board):
   - Keywords: "machine learning" OR "AI" OR "agentic AI" OR "data science" OR "ML intern" OR "AI intern" OR "research intern" OR "stage" OR "praktikum" OR "summer internship" OR "2026 internship"
   - Locations: France, Germany, Paris, Berlin, London, Netherlands, Switzerland, Belgium, Sweden, Canada, Toronto, Montreal, remote Europe, remote Canada
   - Date: 2026 summer / Spring/Summer 2026 / June–August 2026 / rolling internships
   - Level: student / bachelor / 2nd year / undergraduate / early-career / internship

4. **Output CSV columns** (exactly like my previous ones, plus two new ones):
   Company,Type,Location,Remote/Hybrid Chance,Contact Email,Careers / Apply Link,Notes for 2nd-year ML/DS Student,CV Match Score (1-10),Why it matches your CV,Source

5. **Matching logic**:
   - Score each job 1–10 based on how well it matches keywords from the CV (higher weight on Agentic AI, RAG, PyTorch/TensorFlow, production ML, research experience).
   - In "Why it matches your CV" column, write 1–2 sentences referencing specific parts of the CV (e.g., "Matches your part-time ML experience and interest in agentic systems").

6. **Technical implementation**:
   - Use Playwright or Selenium for JavaScript-heavy sites + requests + BeautifulSoup where possible.
   - Respect robots.txt and rate limits (add delays, user-agent rotation).
   - Handle pagination and infinite scroll.
   - For LinkedIn/XING use public search URLs or official APIs if available.
   - Output one clean CSV + a summary HTML report of top 20 matches.
   - Make the script modular so I can easily add new boards later.
   - Include a `main()` that takes `cv.pdf` path as argument.

7. **TARGET** do not only target big companies or labs, I need this search to be realistic for a 2nd year software engineering student with a focus on machine learning and data science who also works part time ( student with working experience), target all companies that are willing to accept such a profile (even though i'm located in tunisia) meaning i prefer fully remote. 
you can use my local environment called ml , i will activate it in the terminal where you're active. 
