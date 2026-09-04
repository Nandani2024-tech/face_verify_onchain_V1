"""
reverse_search.py
------------------
Step 2 of the pipeline: given a LOCAL image file you already own (e.g. your
own photo), run a real reverse-image / web-detection search via Google
Cloud Vision API's WEB_DETECTION feature, and return matching web pages
where that photo (or a near-duplicate of it) appears.

Unlike search tools that require a public URL, Cloud Vision accepts the
raw image bytes directly (base64-encoded) in the request body, so no
manual "upload it somewhere public first" step is needed — you just point
this at a file on disk.

This is a genuine live search call against Google's index (not a
hardcoded result). You need a Google Cloud project with the Vision API
enabled and an API key: https://console.cloud.google.com/apis/library/vision.googleapis.com

IMPORTANT (consent / scope):
Only run this against images you own or have explicit permission to
search for. This module does not do bulk lookups, does not accept
third-party photos of strangers, and is intended purely as a personal-
verification demo.
"""

import os
import sys
import json
import base64
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
    api_key = api_key or os.environ.get("GOOGLE_VISION_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Missing Google Cloud Vision API key. Set GOOGLE_VISION_API_KEY in your environment or .env file."
        )

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    encoded_image = _encode_image(image_path)

    payload = {
        "requests": [
            {
                "image": {"content": encoded_image},
                "features": [{"type": "WEB_DETECTION", "maxResults": max_results}],
            }
        ]
    }

    response = requests.post(
        VISION_ENDPOINT,
        params={"key": api_key},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    result = data.get("responses", [{}])[0]

    if "error" in result:
        raise RuntimeError(f"Vision API error: {result['error'].get('message', result['error'])}")

    web_detection = result.get("webDetection", {})

    matches = []
    for page in web_detection.get("pagesWithMatchingImages", []):
        url = page.get("url", "")
        title = page.get("pageTitle") or urlparse(url).netloc or url
        source = urlparse(url).netloc or "unknown"

        # A matched page may include one or more matching image URLs on it;
        # use the first as a thumbnail reference if present.
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

    return matches



    return matches


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python reverse_search.py <path_to_local_image>")
        sys.exit(1)

    results = reverse_image_search(sys.argv[1])
    print(f"Found {len(results)} matching web pages:\n")
    for i, m in enumerate(results[:10], 1):
        print(f"{i}. {m['title']}")
        print(f"   source: {m['source']}")
        print(f"   link:   {m['link']}\n")

    print(json.dumps(results, indent=2))
