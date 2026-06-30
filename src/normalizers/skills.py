"""
Skills canonicalizer — maps aliases/misspellings to canonical names.
Unknown skills are returned as-is (title-cased) with lower confidence.
"""

from typing import Optional

# Canonical name → list of known aliases (lowercase)
SKILL_ALIASES: dict[str, list[str]] = {
    "Python": ["python", "py", "python3", "python 3", "python2"],
    "JavaScript": ["javascript", "js", "java script", "ecmascript", "es6", "es2015"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java", "java8", "java 8", "java11"],
    "C++": ["c++", "cpp", "c plus plus"],
    "C": ["c language", " c "],
    "C#": ["c#", "csharp", "c sharp"],
    "Go": ["golang", "go lang", "go language"],
    "Rust": ["rust", "rust-lang"],
    "Ruby": ["ruby", "ruby on rails"],
    "PHP": ["php", "php7", "php8"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "Scala": ["scala"],
    "R": ["r language", "r programming", "rlang"],
    "SQL": ["sql", "structured query language"],
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search", "elk"],
    "React": ["react", "reactjs", "react.js"],
    "Next.js": ["nextjs", "next.js", "next js"],
    "Vue.js": ["vue", "vuejs", "vue.js"],
    "Angular": ["angular", "angularjs"],
    "Node.js": ["node", "nodejs", "node.js"],
    "Express.js": ["express", "expressjs", "express.js"],
    "FastAPI": ["fastapi", "fast api"],
    "Django": ["django"],
    "Flask": ["flask"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    "Docker": ["docker", "docker container"],
    "Kubernetes": ["kubernetes", "k8s", "k 8s"],
    "AWS": ["aws", "amazon web services", "amazon aws"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Azure": ["azure", "microsoft azure"],
    "Git": ["git", "github", "gitlab", "version control"],
    "Linux": ["linux", "ubuntu", "debian", "centos"],
    "Machine Learning": ["machine learning", "ml", "supervised learning", "unsupervised learning"],
    "Deep Learning": ["deep learning", "dl", "neural networks", "neural network"],
    "NLP": ["nlp", "natural language processing", "text mining"],
    "Computer Vision": ["computer vision", "cv", "image processing"],
    "TensorFlow": ["tensorflow", "tf"],
    "PyTorch": ["pytorch", "torch"],
    "Scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Matplotlib": ["matplotlib"],
    "LangChain": ["langchain", "lang chain"],
    "LangGraph": ["langgraph", "lang graph"],
    "REST API": ["rest", "rest api", "restful", "restful api"],
    "GraphQL": ["graphql", "graph ql"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous deployment"],
    "Agile": ["agile", "scrum", "kanban"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "Power BI": ["power bi", "powerbi", "power-bi"],
    "DBMS": ["dbms", "database management systems", "database management system"],
    "LLM Applications": ["llm applications", "llm application", "llms"],
    "TF-IDF": ["tf-idf", "tfidf", "tf idf"],
}

# Build reverse lookup: alias → canonical
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in SKILL_ALIASES.items():
    _ALIAS_TO_CANONICAL[canonical.lower()] = canonical
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower().strip()] = canonical


def canonicalize_skill(raw: str) -> str:
    """
    Return canonical skill name. Falls back to title-cased raw input for
    unknown skills — except when the raw token is already a short
    all-caps acronym (e.g. "DBMS", "API", "AI"), since `.title()` would
    otherwise lowercase it to "Dbms"/"Api"/"Ai". Known multi-word
    acronym-bearing skills (Power BI, TF-IDF, ...) are handled by explicit
    alias entries above rather than this heuristic.
    """
    if not raw:
        return raw
    stripped = raw.strip()
    key = stripped.lower()
    if key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[key]
    if stripped.isupper() and 2 <= len(stripped) <= 6:
        return stripped
    return stripped.title()
