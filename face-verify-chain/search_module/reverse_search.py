"""
reverse_search.py
------------------
Step 2 of the pipeline: given a LOCAL image file you already own (e.g. your
own photo), run a real reverse-image / web-detection search via Google
Cloud Vision API's WEB_DETECTION and TEXT_DETECTION features, returning
matching web pages prioritized by confidence (full_match vs partial_match).
"""

import os
import sys
import json
import base64
import logging
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

# Configure logger
logger = logging.getLogger("reverse_search")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [reverse_search] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"


class CandidateList(list):
    """
    List subclass containing candidate dicts, while carrying OCR text signals
    and web entity guesses as metadata attributes.
    """
    def __init__(self, candidates, text_signal=None, entity_guesses=None):
        super().__init__(candidates)
        self.text_signal = text_signal
        self.entity_guesses = entity_guesses or []


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def reverse_image_search(image_path: str, api_key: str = None, max_results: int = 10):
    """
    Run Google Cloud Vision WEB_DETECTION + TEXT_DETECTION search on local image at `image_path`.
    Returns a CandidateList of candidate web pages prioritized by confidence tier:
      - full_match: exact matching image on page
      - partial_match: partial matching image or page match
    Also carries .text_signal and .entity_guesses metadata.
    """
    logger.info("Initializing Google Cloud Vision Reverse Image Search (WEB_DETECTION + TEXT_DETECTION)...")
    api_key = api_key or os.environ.get("GOOGLE_VISION_API_KEY")
    if not api_key:
        logger.error("GOOGLE_VISION_API_KEY is missing! Check your .env file or environment variables.")
        raise EnvironmentError(
            "Missing Google Cloud Vision API key. Set GOOGLE_VISION_API_KEY in your environment or .env file."
        )

    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    logger.info(f"Using Google Cloud Vision API key: {masked_key}")

    if not os.path.isfile(image_path):
        logger.error(f"Target image file not found on disk at: '{image_path}'")
        raise FileNotFoundError(f"Image file not found: {image_path}")

    logger.info(f"Reading and base64-encoding image: '{image_path}'")
    encoded_image = _encode_image(image_path)
    file_size_kb = round(os.path.getsize(image_path) / 1024, 2)
    logger.info(f"Image encoded successfully (Base64 payload size: {round(len(encoded_image)/1024, 2)} KB, File size: {file_size_kb} KB)")

    payload = {
        "requests": [
            {
                "image": {"content": encoded_image},
                "features": [
                    {"type": "WEB_DETECTION", "maxResults": max_results},
                    {"type": "TEXT_DETECTION"},
                ],
            }
        ]
    }

    logger.info(f"Sending POST request to Google Vision API ({VISION_ENDPOINT})...")
    try:
        response = requests.post(
            VISION_ENDPOINT,
            params={"key": api_key},
            json=payload,
            timeout=30,
        )
        logger.info(f"HTTP Response received: Status Code {response.status_code}")
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Google Vision API HTTP Error {response.status_code}: {response.text}")
        raise
    except Exception as e:
        logger.error(f"Failed to connect to Google Vision API: {e}")
        raise

    result = data.get("responses", [{}])[0]

    if "error" in result:
        err_msg = result['error'].get('message', result['error'])
        logger.error(f"Google Vision API Returned Error: {err_msg}")
        raise RuntimeError(f"Vision API error: {err_msg}")

    # 1. Process OCR TEXT_DETECTION
    text_annotations = result.get("textAnnotations", [])
    detected_text_signal = None
    if text_annotations and len(text_annotations) > 0:
        raw_text = text_annotations[0].get("description", "").strip()
        if raw_text:
            detected_text_signal = " ".join(raw_text.split())
            logger.info(f"Detected Text Signals: '{detected_text_signal}'")

    # 2. Process WEB_DETECTION
    web_detection = result.get("webDetection", {})
    pages_matched = web_detection.get("pagesWithMatchingImages", [])
    full_matching = web_detection.get("fullMatchingImages", [])
    partial_matching = web_detection.get("partialMatchingImages", [])
    web_entities = web_detection.get("webEntities", [])
    best_guess_labels = web_detection.get("bestGuessLabels", [])

    logger.info(f"Web Detection Summary: {len(pages_matched)} matching pages, {len(full_matching)} full image matches, {len(partial_matching)} partial image matches, {len(web_entities)} web entities")

    best_guess_str = ", ".join([b.get("label", "") for b in best_guess_labels if b.get("label")])
    if not full_matching and (detected_text_signal or best_guess_str):
        fallback_hint = " | ".join(filter(None, [detected_text_signal, best_guess_str]))
        logger.info(f"Fallback text-based signal: {fallback_hint}")

    # Collect entity guesses (informational only)
    entity_guesses = []
    for ent in web_entities:
        desc = ent.get("description")
        if desc and desc not in entity_guesses:
            entity_guesses.append(desc)

    # 3. Categorize & Rank Candidate Web Pages (full_match vs partial_match)
    full_match_candidates = []
    partial_match_candidates = []
    seen_urls = set()

    for page in pages_matched:
        url = page.get("url", "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        title = page.get("pageTitle") or urlparse(url).netloc or url
        source = urlparse(url).netloc or "unknown"

        page_full_matches = page.get("fullMatchingImages", [])
        page_partial_matches = page.get("partialMatchingImages", [])

        thumbnail = None
        if page_full_matches:
            thumbnail = page_full_matches[0].get("url")
        elif page_partial_matches:
            thumbnail = page_partial_matches[0].get("url")

        is_full_match = len(page_full_matches) > 0 or len(full_matching) > 0 and any(
            fm.get("url") == url for fm in full_matching
        )

        candidate_obj = {
            "title": title,
            "link": url,
            "source": source,
            "thumbnail": thumbnail,
            "match_confidence_tier": "full_match" if is_full_match else "partial_match",
        }

        if is_full_match:
            full_match_candidates.append(candidate_obj)
        else:
            partial_match_candidates.append(candidate_obj)

    # Combine prioritized candidate list: full_match first, then partial_match
    ordered_candidates = full_match_candidates + partial_match_candidates

    # Cap list at top 5 candidates
    candidates = ordered_candidates[:5]

    if candidates:
        top_tier = candidates[0]["match_confidence_tier"]
        logger.info(f"Top Match Rank Tier: [{top_tier.upper()}] — '{candidates[0]['title']}' on {candidates[0]['source']} ({candidates[0]['link']})")
    else:
        logger.warning(f"No web page matches found for '{image_path}'.")

    return CandidateList(candidates, text_signal=detected_text_signal, entity_guesses=entity_guesses)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python reverse_search.py <path_to_local_image>")
        sys.exit(1)

    results = reverse_image_search(sys.argv[1])
    print(f"\nText Signal: {results.text_signal}")
    print(f"Entity Guesses: {results.entity_guesses}")
    print(f"Found {len(results)} candidate web pages:\n")
    for i, m in enumerate(results, 1):
        print(f"[{i}] [{m['match_confidence_tier'].upper()}] {m['title']}")
        print(f"    source: {m['source']}")
        print(f"    link:   {m['link']}\n")

    print(json.dumps(results, indent=2))
