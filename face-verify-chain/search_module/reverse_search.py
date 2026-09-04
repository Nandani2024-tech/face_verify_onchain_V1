"""
reverse_search.py
------------------
Step 2 of the pipeline: given a LOCAL image file you already own (e.g. your
own photo), run a real reverse-image / web-detection search via Google
Cloud Vision API's WEB_DETECTION feature, and return matching web pages
where that photo (or a near-duplicate of it) appears.
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


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def reverse_image_search(image_path: str, api_key: str = None, max_results: int = 10):
    """
    Run a Google Cloud Vision WEB_DETECTION search on the local image at
    `image_path` and return a list of matching results in the same shape
    used elsewhere in this project: {title, link, source, thumbnail}.
    """
    logger.info("Initializing Google Cloud Vision Reverse Image Search...")
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
                "features": [{"type": "WEB_DETECTION", "maxResults": max_results}],
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

    web_detection = result.get("webDetection", {})
    pages_matched = web_detection.get("pagesWithMatchingImages", [])
    full_matching = web_detection.get("fullMatchingImages", [])
    partial_matching = web_detection.get("partialMatchingImages", [])
    web_entities = web_detection.get("webEntities", [])

    logger.info(f"Web Detection Summary: {len(pages_matched)} matching pages, {len(full_matching)} full image matches, {len(partial_matching)} partial image matches, {len(web_entities)} web entities")

    matches = []
    for page in pages_matched:
        url = page.get("url", "")
        title = page.get("pageTitle") or urlparse(url).netloc or url
        source = urlparse(url).netloc or "unknown"

        thumbnail = None
        full_matches = page.get("fullMatchingImages") or page.get("partialMatchingImages")
        if full_matches:
            thumbnail = full_matches[0].get("url")

        matches.append({
            "title": title,
            "link": url,
            "source": source,
            "thumbnail": thumbnail,
        })

    if matches:
        logger.info(f"Top Match Discovered: '{matches[0]['title']}' on {matches[0]['source']} ({matches[0]['link']})")
    else:
        logger.warning(f"No web page matches found for '{image_path}'. Image may not be publicly indexed.")

    return matches


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python reverse_search.py <path_to_local_image>")
        sys.exit(1)

    results = reverse_image_search(sys.argv[1])
    print(f"\nFound {len(results)} matching web pages:\n")
    for i, m in enumerate(results[:10], 1):
        print(f"{i}. {m['title']}")
        print(f"   source: {m['source']}")
        print(f"   link:   {m['link']}\n")

    print(json.dumps(results, indent=2))

