"""
pipeline.py
-----------
End-to-end demo pipeline:

  1. Face scan     -> detect + encode a face from a local photo
  2. Web search     -> reverse-image-search that SAME local photo directly
                        (via Google Cloud Vision WEB_DETECTION) to find a
                        real matching post/page on the web
  3. Blockchain     -> hash the matched post, upload the fingerprint to
                        Ethereum Sepolia testnet, then re-verify it on-chain

A single local image drives the whole pipeline — no separate public URL
is needed; Google Cloud Vision accepts the image bytes directly.

Usage:
  python pipeline.py --face samples/my_photo.jpg

Requires a .env file (see .env.example) with:
  GOOGLE_VISION_API_KEY, RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS
"""

import os
import sys
import argparse
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), "face_module"))
sys.path.append(os.path.join(os.path.dirname(__file__), "search_module"))
sys.path.append(os.path.join(os.path.dirname(__file__), "blockchain_module"))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


from face_id import encode_face
from reverse_search import reverse_image_search
from blockchain_utils import upload_record, verify_record


def run_pipeline(face_image_path: str):
    load_dotenv()

    print("=" * 60)
    print("STEP 1 — FACE SCAN")
    print("=" * 60)
    face_result = encode_face(face_image_path)
    print(f"Face detected at: {face_result['location']}")
    print(f"Encoding fingerprint: {face_result['fingerprint']}\n")

    print("=" * 60)
    print("STEP 2 — WEB / SOCIAL MEDIA SEARCH (Google Cloud Vision)")
    print("=" * 60)
    matches = reverse_image_search(face_image_path)
    if not matches:
        print("No matches found. This image may not be indexed publicly yet, "
              "or may not have been posted anywhere else on the web. Exiting.")
        return

    top_match = matches[0]
    print(f"Top match found:")
    print(f"  Title:  {top_match['title']}")
    print(f"  Source: {top_match['source']}")
    print(f"  Link:   {top_match['link']}\n")

    print("=" * 60)
    print("STEP 3 — BLOCKCHAIN UPLOAD")
    print("=" * 60)
    upload_result = upload_record(top_match)
    print(f"Content hash:  {upload_result['content_hash']}")
    print(f"Tx hash:       {upload_result['tx_hash']}")
    print(f"Block number:  {upload_result['block_number']}\n")

    print("=" * 60)
    print("STEP 4 — ON-CHAIN RE-VERIFICATION")
    print("=" * 60)
    verification = verify_record(top_match)
    if verification:
        print("✅ Record verified on-chain:")
        print(json.dumps(verification, indent=2))
    else:
        print("❌ Record not found on-chain (something went wrong).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Face → Search → Blockchain verification pipeline")
    parser.add_argument("--face", required=True, help="Path to local photo — used for both face detection and the web search")
    args = parser.parse_args()

    run_pipeline(args.face)
