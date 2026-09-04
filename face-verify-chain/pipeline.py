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

Usage:
  python pipeline.py --face samples/my_photo.jpg
"""

import os
import sys
import time
import json
import logging
import argparse
import traceback
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

# Configure main pipeline logger
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")

from face_id import encode_face
from reverse_search import reverse_image_search
from blockchain_utils import upload_record, verify_record


def print_step_header(step_num: int, title: str):
    print("\n" + "=" * 70)
    print(f"  STEP {step_num} — {title.upper()}")
    print("=" * 70)


def log_fatal_bug(step_name: str, exc: Exception):
    tb = traceback.extract_tb(exc.__traceback__)
    last_frame = tb[-1] if tb else None
    
    print("\n" + "!" * 70)
    print(f"  ❌ FATAL FAILURE IN STEP: {step_name}")
    print("!" * 70)
    logger.error(f"Pipeline execution halted during [{step_name}]")
    logger.error(f"Error Type: {type(exc).__name__}")
    logger.error(f"Error Message: {exc}")
    
    if last_frame:
        filename = os.path.basename(last_frame.filename)
        logger.error(f"Bug Location: File '{filename}', Line {last_frame.lineno}, in Function '{last_frame.name}'")
        logger.error(f"Failing Line of Code: -> {last_frame.line}")
    
    print("\n--- Full Technical Traceback ---")
    traceback.print_exc()
    print("!" * 70 + "\n")


def run_pipeline(face_image_path: str):
    start_time = time.time()
    logger.info("Starting Face -> Search -> Blockchain Verification Pipeline...")
    load_dotenv()

    # -------------------------------------------------------------------------
    # STEP 1: FACE SCAN & ENCODING
    # -------------------------------------------------------------------------
    print_step_header(1, "Face Scan & Encoding (face_id.py)")
    step1_start = time.time()
    try:
        face_result = encode_face(face_image_path)
        logger.info(f"✅ STEP 1 COMPLETED in {round(time.time() - step1_start, 2)}s")
        print(f"   Face Location (top, right, bottom, left): {face_result['location']}")
        print(f"   Face Encoding SHA-256 Fingerprint:        {face_result['fingerprint']}")
    except Exception as e:
        log_fatal_bug("STEP 1: FACE SCAN", e)
        return False

    # -------------------------------------------------------------------------
    # STEP 2: REVERSE IMAGE SEARCH
    # -------------------------------------------------------------------------
    print_step_header(2, "Web / Social Media Search (Google Cloud Vision)")
    step2_start = time.time()
    try:
        matches = reverse_image_search(face_image_path)
        if not matches:
            logger.warning("No web matches found for this photo. Image is not publicly indexed. Pipeline exiting gracefully.")
            return False

        top_match = matches[0]
        logger.info(f"✅ STEP 2 COMPLETED in {round(time.time() - step2_start, 2)}s ({len(matches)} matches found)")
        print(f"   Top Matched Web Page:")
        print(f"     Title:  {top_match['title']}")
        print(f"     Source: {top_match['source']}")
        print(f"     Link:   {top_match['link']}")
    except Exception as e:
        log_fatal_bug("STEP 2: REVERSE WEB SEARCH", e)
        return False

    # -------------------------------------------------------------------------
    # STEP 3: BLOCKCHAIN UPLOAD
    # -------------------------------------------------------------------------
    print_step_header(3, "Blockchain Upload (Ethereum Sepolia Testnet)")
    step3_start = time.time()
    try:
        upload_result = upload_record(top_match)
        logger.info(f"✅ STEP 3 COMPLETED in {round(time.time() - step3_start, 2)}s")
        print(f"   Keccak256 Content Hash: 0x{upload_result['content_hash']}")
        print(f"   Ethereum Tx Hash:       0x{upload_result['tx_hash']}")
        print(f"   Confirmed Block Number: #{upload_result['block_number']}")
    except Exception as e:
        log_fatal_bug("STEP 3: BLOCKCHAIN UPLOAD", e)
        return False

    # -------------------------------------------------------------------------
    # STEP 4: ON-CHAIN RE-VERIFICATION
    # -------------------------------------------------------------------------
    print_step_header(4, "On-Chain Re-Verification")
    step4_start = time.time()
    try:
        verification = verify_record(top_match)
        if verification:
            logger.info(f"✅ STEP 4 COMPLETED in {round(time.time() - step4_start, 2)}s")
            print("\n🎉 SUCCESS: Record verified 100% authentic on Ethereum Sepolia Blockchain:")
            print(json.dumps(verification, indent=2))
        else:
            logger.error("❌ On-chain query returned False: Record not found in contract state!")
            return False
    except Exception as e:
        log_fatal_bug("STEP 4: ON-CHAIN RE-VERIFICATION", e)
        return False

    total_duration = round(time.time() - start_time, 2)
    print("\n" + "=" * 70)
    logger.info(f"🎉 PIPELINE EXECUTED SUCCESSFULLY IN {total_duration} SECONDS!")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Face → Search → Blockchain verification pipeline")
    parser.add_argument("--face", required=True, help="Path to local photo — used for face detection and web search")
    args = parser.parse_args()

    run_pipeline(args.face)

