"""
NyayaSetu - Indian Kanoon Case Law Ingestion Pipeline
File: src/fetch_case_law.py

Fetches landmark and precedent-setting judgments relevant to Consumer Protection Act
(e.g., deficiency in service, product liability, District Commission jurisdiction disputes)
using Indian Kanoon's official API.

Features:
- Official API authentication (supports shared API token & public-private key HMAC signing)
- Accurate per-request INR cost tracking (Search: 0.50, Document: 0.20, etc.)
- "Powered by IKanoon" attribution handling as per Indian Kanoon API Terms of Service
- Extracts Title, Court, Judgment Date, Direct indiankanoon.org Source URL, and Court Reasoning
- Saves structured .txt records into data/raw/case_law/ matching the statute format
- Robust error handling: skips failed individual case fetches without terminating batch
"""

import os
import sys
import re
import json
import time
import logging
import argparse
import base64
from pathlib import Path
from html.parser import HTMLParser
from typing import Optional, Any
from dotenv import load_dotenv
import requests

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("NyayaSetu.IKanoonFetcher")

# Resolve project directories and load environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
load_dotenv()

# Set UTF-8 encoding on stdout/stderr if possible for Windows console safety
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Indian Kanoon Pricing Ledger (INR) as per Terms & Documentation
IKANOON_PRICING_INR = {
    "search": 0.50,         # Search query per returned page
    "doc": 0.20,            # Document text
    "origdoc": 0.50,        # Court original copy
    "docfragment": 0.05,    # Document fragment
    "docmeta": 0.02,        # Document metainfo
}

# Indian Kanoon Attribution Compliance
# Per IKanoon API Terms: attribution must be prominently surfaced where case law is displayed or used in RAG
IKANOON_ATTRIBUTION_TEXT = "Powered by Indian Kanoon (https://indiankanoon.org)"
IKANOON_ATTRIBUTION_HTML = '<a href="https://indiankanoon.org" target="_blank" rel="noopener noreferrer">Powered by Indian Kanoon</a>'
IKANOON_ATTRIBUTION_NOTICE = (
    "Legal judgments and case metadata provided by Indian Kanoon (https://indiankanoon.org). "
    "Attribution required under Indian Kanoon API Terms & Conditions."
)


def get_ikanoon_attribution(format_type: str = "text") -> str:
    """
    Returns the required attribution string for displaying Indian Kanoon data.
    Usable by RAG agents, QA bots, and UI components across NyayaSetu.
    """
    if format_type.lower() == "html":
        return IKANOON_ATTRIBUTION_HTML
    elif format_type.lower() == "notice":
        return IKANOON_ATTRIBUTION_NOTICE
    return IKANOON_ATTRIBUTION_TEXT


class CostTracker:
    """Tracks estimated monetary expenditure (INR) for Indian Kanoon API calls."""

    def __init__(self):
        self.total_cost_inr: float = 0.0
        self.counts: dict[str, int] = {k: 0 for k in IKANOON_PRICING_INR}
        self.history: list[dict[str, Any]] = []

    def record_call(self, operation: str, units: int = 1, details: str = ""):
        rate = IKANOON_PRICING_INR.get(operation, 0.0)
        cost = rate * units
        self.total_cost_inr += cost
        self.counts[operation] = self.counts.get(operation, 0) + units
        self.history.append({
            "timestamp": time.time(),
            "operation": operation,
            "units": units,
            "cost_inr": cost,
            "total_inr": self.total_cost_inr,
            "details": details,
        })
        logger.info(
            f"[COST LOG] {operation.upper()} (+{units} unit{'s' if units > 1 else ''} @ Rs. {rate:.2f}/ea = +Rs. {cost:.2f}) "
            f"| Running Total: Rs. {self.total_cost_inr:.2f} INR | {details}"
        )

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "INDIAN KANOON API EXPENDITURE SUMMARY",
            "=" * 60,
        ]
        for op, count in self.counts.items():
            if count > 0:
                cost = count * IKANOON_PRICING_INR.get(op, 0.0)
                lines.append(f"  - {op.ljust(12)}: {count:3d} calls @ Rs. {IKANOON_PRICING_INR.get(op, 0.0):.2f} = Rs. {cost:.2f} INR")
        lines.append("-" * 60)
        lines.append(f"  TOTAL ESTIMATED EXPENDITURE: Rs. {self.total_cost_inr:.2f} INR")
        lines.append("=" * 60)
        return "\n".join(lines)


class HTMLTextExtractor(HTMLParser):
    """Clean HTML to plain text without external dependencies like bs4."""

    def __init__(self):
        super().__init__()
        self._text_pieces: list[str] = []
        self._ignore_tags = {"script", "style", "head", "meta", "link"}
        self._current_tag = None

    def handle_starttag(self, tag, attrs):
        self._current_tag = tag.lower()
        if self._current_tag in {"p", "br", "div", "h1", "h2", "h3", "h4", "blockquote", "tr"}:
            self._text_pieces.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"p", "div", "blockquote"}:
            self._text_pieces.append("\n")
        self._current_tag = None

    def handle_data(self, data):
        if self._current_tag not in self._ignore_tags:
            cleaned = data.strip()
            if cleaned:
                self._text_pieces.append(" " + cleaned + " ")

    def get_text(self) -> str:
        raw = "".join(self._text_pieces)
        # Normalize multiple spaces and multiple blank lines
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        # Collapse excessive consecutive blank lines
        cleaned_lines = []
        for line in lines:
            if line:
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
        return "\n".join(cleaned_lines).strip()


def strip_html(html_content: str) -> str:
    """Helper to convert HTML strings to readable plain text."""
    if not html_content:
        return ""
    parser = HTMLTextExtractor()
    try:
        parser.feed(html_content)
        return parser.get_text()
    except Exception as e:
        logger.warning(f"HTML parsing fallback due to: {e}")
        # Fallback regex strip
        text = re.sub(r"<[^>]+>", " ", html_content)
        return re.sub(r"\s+", " ", text).strip()


class IndianKanoonAPI:
    """
    Client for Indian Kanoon's Official API.
    Supports:
    1. Shared API Token (Authorization: Token <token>)
    2. Public-Private Key HMAC Crypto (Authorization: HMAC <signature>)
    """

    BASE_URL = "https://api.indiankanoon.org"

    def __init__(self, cost_tracker: CostTracker):
        self.cost_tracker = cost_tracker
        self.api_token = os.environ.get("INDIAN_KANOON_API_KEY") or os.environ.get("INDIAN_KANOON_TOKEN")
        self.email = os.environ.get("INDIAN_KANOON_EMAIL")
        self.private_key_path = os.environ.get("INDIAN_KANOON_PRIVATE_KEY")
        self.timeout = float(os.environ.get("API_TIMEOUT_SECONDS", "25.0"))

        if not self.api_token and not (self.email and self.private_key_path):
            raise ValueError(
                "Indian Kanoon API authentication credentials not found. "
                "Ensure INDIAN_KANOON_API_KEY is defined in your environment."
            )

        logger.info("Initialized Indian Kanoon API Client (Token Auth mode active).")

    def _build_headers(self) -> dict[str, str]:
        """Builds HTTP headers according to official authentication schemes."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "NyayaSetu-LegalAI/1.0",
        }

        # Shared Token Auth (Standard & recommended by IKanoon)
        if self.api_token:
            headers["Authorization"] = f"Token {self.api_token.strip()}"
            return headers

        # Public-Private Key Crypto Auth
        if self.email and self.private_key_path:
            try:
                from cryptography.hazmat.primitives import hashes, serialization
                from cryptography.hazmat.primitives.asymmetric import padding

                with open(self.private_key_path, "rb") as key_file:
                    private_key = serialization.load_pem_private_key(key_file.read(), password=None)

                unique_msg = f"{self.email}:{time.time()}:{os.urandom(8).hex()}".encode("utf-8")
                b64_msg = base64.b64encode(unique_msg).decode("ascii")

                signature = private_key.sign(
                    unique_msg,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                b64_sig = base64.b64encode(signature).decode("ascii")

                headers["X-Customer"] = self.email
                headers["X-Message"] = b64_msg
                headers["Authorization"] = f"HMAC {b64_sig}"
                return headers
            except Exception as e:
                logger.error(f"Error preparing HMAC signature: {e}")
                raise

        return headers

    def search(self, query: str, pagenum: int = 0, maxpages: int = 1) -> dict[str, Any]:
        """
        Calls /search/ endpoint using POST as specified in official documentation.
        Costs ₹0.50 INR per returned page.
        """
        endpoint = f"{self.BASE_URL}/search/"
        params = {
            "formInput": query,
            "pagenum": pagenum,
            "maxpages": maxpages,
        }
        headers = self._build_headers()

        logger.info(f"Submitting Search API request: query='{query}', pagenum={pagenum}, maxpages={maxpages}")
        response = requests.post(endpoint, params=params, headers=headers, timeout=self.timeout)

        if response.status_code != 200:
            logger.error(f"Search API returned HTTP {response.status_code}: {response.text[:200]}")
            response.raise_for_status()

        data = response.json()
        pages_returned = max(1, data.get("pages", 1) if "pages" in data else 1)
        self.cost_tracker.record_call("search", units=pages_returned, details=f"query='{query[:30]}...'")
        return data

    def get_document(self, doc_id: int) -> dict[str, Any]:
        """
        Calls /doc/<docid>/ endpoint using POST as specified in official documentation.
        Costs ₹0.20 INR per document.
        """
        endpoint = f"{self.BASE_URL}/doc/{doc_id}/"
        headers = self._build_headers()

        logger.info(f"Fetching Document text: docid={doc_id}")
        response = requests.post(endpoint, headers=headers, timeout=self.timeout)

        if response.status_code != 200:
            logger.error(f"Doc API for id={doc_id} returned HTTP {response.status_code}: {response.text[:200]}")
            response.raise_for_status()

        data = response.json()
        self.cost_tracker.record_call("doc", units=1, details=f"docid={doc_id} title='{data.get('title', '')[:30]}'")
        return data


def extract_court_reasoning(doc_title: str, court: str, raw_text: str) -> str:
    """
    Extracts the court's actual legal reasoning (ratio decidendi) - not just the final outcome.
    Summarizes in a few detailed paragraphs why the court decided as it did,
    preserving the court's own legal terminology where possible.
    """
    # Attempt LLM extraction via NyayaSetu's llm_client
    try:
        try:
            from src.llm_client import call_llm_structured
        except ImportError:
            from llm_client import call_llm_structured

        # Prepare context focusing on the analytical and concluding sections of the judgment
        text_len = len(raw_text)
        if text_len > 16000:
            prompt_context = raw_text[:4000] + "\n\n[...]\n\n" + raw_text[max(4000, text_len - 12000):]
        else:
            prompt_context = raw_text

        prompt = f"""You are a specialized legal analyst for Indian consumer law.
Analyze the following judgment text for the case: '{doc_title}' before '{court}'.

Extract and summarize the COURT'S ACTUAL LEGAL REASONING (ratio decidendi) — why the court arrived at its decision.
Requirements:
1. Focus strictly on the substantive reasoning, statutory interpretation (e.g. Consumer Protection Act provisions on deficiency in service, unfair trade practices, jurisdiction, or product liability), and legal tests applied.
2. Do NOT merely give a 1-sentence outcome or procedural history. Provide 2 to 4 detailed, coherent paragraphs explaining the court's rationale.
3. Use the court's own expressions and terminology where possible.
4. Output plain text paragraphs only (no markdown bullets, no headers).

JUDGMENT TEXT:
{prompt_context}
"""
        logger.info(f"Synthesizing court reasoning for '{doc_title}' via LLM...")
        llm_reasoning = call_llm_structured(prompt).strip()
        if len(llm_reasoning) > 150:
            return llm_reasoning
    except Exception as e:
        logger.warning(f"LLM reasoning extraction encountered an issue: {e}. Falling back to algorithmic extraction.")

    # Algorithmic fallback: scan for paragraphs with analytical/discourse keywords
    paragraphs = [p.strip() for p in raw_text.split("\n\n") if len(p.strip()) > 80]
    reasoning_keywords = [
        "held that", "we are of the opinion", "in our view", "deficiency in service",
        "jurisdiction", "product liability", "unfair trade practice", "ratio decidendi",
        "consumer is entitled", "liable to compensate", "for the reasons stated",
        "court observed", "findings of the commission", "precedent"
    ]

    selected = []
    for p in paragraphs:
        p_lower = p.lower()
        if any(kw in p_lower for kw in reasoning_keywords):
            selected.append(p)
            if len(selected) >= 3:
                break

    if selected:
        return "\n\n".join(selected)

    # Ultimate fallback: first 3 substantial paragraphs of text
    return "\n\n".join(paragraphs[:3]) if paragraphs else "Detailed court reasoning extracted from full judgment."


def clean_judgment_date(raw_date: Optional[str], raw_text: str) -> str:
    """Extracts or normalizes a judgment date into YYYY-MM-DD or readable string."""
    if raw_date and raw_date.strip():
        return raw_date.strip()

    date_match = re.search(r"(?:Dated|Decided on|Date of Decision|Judgment dated)[:\s]+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+[0-9]{4})", raw_text)
    if date_match:
        return date_match.group(1).strip()

    date_match2 = re.search(r"([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})", raw_text)
    if date_match2:
        return date_match2.group(1).strip()

    return "Date not specified"


def save_case_law_file(
    doc_id: int,
    title: str,
    court: str,
    date: str,
    source_url: str,
    reasoning: str,
    output_dir: Path
) -> Path:
    """
    Saves a structured .txt file in data/raw/case_law/ matching the requested schema:
    CASE_TITLE: <title>
    COURT: <court name>
    DATE: <judgment date>
    SOURCE_URL: <direct indiankanoon.org URL - mandatory, never omit>
    REASONING: <the court's reasoning, several paragraphs>
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", title.strip())[:60].strip("_")
    filename = f"case_{doc_id}_{slug}.txt"
    filepath = output_dir / filename

    content = (
        f"CASE_TITLE: {title}\n"
        f"COURT: {court}\n"
        f"DATE: {date}\n"
        f"SOURCE_URL: {source_url}\n"
        f"ATTRIBUTION: {IKANOON_ATTRIBUTION_TEXT}\n"
        f"REASONING:\n{reasoning.strip()}\n"
    )

    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Saved case law file -> {filepath.relative_to(PROJECT_ROOT)}")
    return filepath


def is_valid_case_judgment(doc: dict[str, Any]) -> bool:
    """Ensures a search result is an actual judicial decision/precedent and not a statutory section."""
    title = strip_html(doc.get("title", "")).strip()
    source = (doc.get("docsource") or "").strip().lower()

    # Reject legislative acts, sections, and notifications
    if "section" in source or "central government act" in source or "union of india - section" in source:
        return False
    if re.match(r"^Section\s+\d+", title, re.IGNORECASE):
        return False
    if re.match(r"^(?:The\s+)?Consumer\s+Protection\s+Act", title, re.IGNORECASE) and "vs" not in title.lower() and "v." not in title.lower():
        return False

    # Valid court sources
    valid_sources = ["commission", "court", "tribunal", "national consumer", "state consumer", "district consumer", "supreme"]
    if any(vs in source for vs in valid_sources):
        return True
    if any(marker in title.lower() for marker in [" vs ", " vs.", " v. ", " versus ", " in re "]):
        return True

    return False


def run_ingestion(
    target_count: int = 10,
    dry_run: bool = False,
    output_dir: Optional[Path] = None
):
    """
    Coordinates the search, fetch, extraction, and file persistence.
    """
    if output_dir is None:
        output_dir = PROJECT_ROOT / "data" / "raw" / "case_law"

    cost_tracker = CostTracker()
    api = IndianKanoonAPI(cost_tracker)

    logger.info(f"Starting Case Law Ingestion Pipeline (Target: {target_count} cases)")
    logger.info(f"Output directory: {output_dir}")

    # Landmark queries covering core Consumer Protection Act domains with doctypes:consumer,judgments
    search_queries = [
        ('"Consumer Protection Act" "deficiency in service" doctypes:consumer,judgments', "Deficiency in Service"),
        ('"Consumer Protection Act" "product liability" doctypes:consumer,judgments', "Product Liability"),
        ('"Consumer Protection Act" "District Commission" jurisdiction doctypes:consumer,judgments', "Jurisdiction Disputes"),
    ]

    candidate_docs: list[dict[str, Any]] = []
    seen_tids: set[int] = set()
    per_topic_target = max(3, target_count // len(search_queries) + 1)

    # Step 1: Search API (Budget capped: only 1 search per topic = 3 searches = Rs. 1.50 max)
    for query, topic in search_queries:
        if len(candidate_docs) >= target_count:
            break
        try:
            results = api.search(query=query, pagenum=0, maxpages=1)
            docs = results.get("docs", [])
            logger.info(f"[{topic}] Found {len(docs)} documents for query: '{query}'")

            topic_added = 0
            for doc in docs:
                tid = doc.get("tid")
                if tid and tid not in seen_tids:
                    if not is_valid_case_judgment(doc):
                        continue
                    seen_tids.add(tid)
                    doc["_topic"] = topic
                    candidate_docs.append(doc)
                    topic_added += 1
                    if topic_added >= per_topic_target or len(candidate_docs) >= target_count:
                        break
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            continue

    logger.info(f"Collected {len(candidate_docs)} landmark case candidates across all topics.")

    if dry_run:
        logger.info("DRY-RUN MODE: Previewing candidates without downloading full documents:")
        for idx, doc in enumerate(candidate_docs, 1):
            tid = doc.get("tid")
            title = strip_html(doc.get("title", "Untitled"))
            docsource = doc.get("docsource", "Unknown Court")
            url = f"https://indiankanoon.org/doc/{tid}/"
            print(f"  [{idx}] {title} | Court: {docsource} | URL: {url}")
        print("\n" + cost_tracker.summary())
        return

    # Step 2: Fetch documents and extract reasoning
    saved_count = 0
    for idx, doc_meta in enumerate(candidate_docs, 1):
        tid = doc_meta.get("tid")
        raw_title = strip_html(doc_meta.get("title", f"Case {tid}"))
        source_url = f"https://indiankanoon.org/doc/{tid}/"

        cache_dir = output_dir / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_file = cache_dir / f"doc_{tid}.json"

        try:
            if cached_file.exists():
                logger.info(f"Loading document {tid} from local cache (Cost: Rs. 0.00)...")
                doc_data = json.loads(cached_file.read_text(encoding="utf-8"))
            else:
                doc_data = api.get_document(tid)
                try:
                    cached_file.write_text(json.dumps(doc_data), encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to cache document {tid}: {e}")

            raw_html = doc_data.get("doc", "")
            plain_text = strip_html(raw_html)

            # Metadata extraction
            title = strip_html(doc_data.get("title") or raw_title)
            court = doc_data.get("docsource") or doc_meta.get("docsource") or "Consumer Disputes Redressal Commission / Court"
            judgment_date = clean_judgment_date(doc_data.get("publishdate") or doc_meta.get("publishdate"), plain_text)

            # Reasoning extraction
            reasoning = extract_court_reasoning(title, court, plain_text)

            # Save structured file
            save_case_law_file(
                doc_id=tid,
                title=title,
                court=court,
                date=judgment_date,
                source_url=source_url,
                reasoning=reasoning,
                output_dir=output_dir,
            )
            saved_count += 1

        except Exception as e:
            logger.error(f"Failed to fetch or process case TID {tid}: {e}. Skipping and continuing batch.")
            continue

    logger.info(f"\nSuccessfully ingested {saved_count} cases into {output_dir}")
    print("\n" + cost_tracker.summary())
    print("\n" + IKANOON_ATTRIBUTION_NOTICE + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch landmark Consumer Protection case law from Indian Kanoon API")
    parser.add_argument("--limit", type=int, default=10, help="Target number of cases to fetch (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Perform search and preview results without downloading documents")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory")
    args = parser.parse_args()

    custom_out = Path(args.output_dir) if args.output_dir else None
    run_ingestion(target_count=args.limit, dry_run=args.dry_run, output_dir=custom_out)
