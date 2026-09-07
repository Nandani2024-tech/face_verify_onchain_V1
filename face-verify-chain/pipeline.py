"""
pipeline.py
-----------
End-to-end demo pipeline:

  1. Face scan     -> detect + encode a face from a local photo
  2. Web search     -> reverse-image-search that SAME local photo directly
                        (via Google Cloud Vision WEB_DETECTION + TEXT_DETECTION)
                        to find matching posts/pages on the web
  2.5 Selection    -> interactive console UI menu to pick candidate match
  3. Blockchain     -> hash the selected post, upload fingerprint to
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
        logger.info(f"✅ STEP 2 COMPLETED in {round(time.time() - step2_start, 2)}s")

        text_signal = getattr(matches, "text_signal", None)
        entity_guesses = getattr(matches, "entity_guesses", [])

        # Display OCR text signal directly above the candidate menu
        if text_signal:
            print(f"\n🔤 Detected Text Signal: {text_signal}")
        if entity_guesses:
            print(f"💡 Related concepts detected: {', '.join(entity_guesses[:4])}")

        # Filter valid selectable candidates (only items with real URLs)
        selectable_candidates = [m for m in matches if m.get("link")]

        if not selectable_candidates:
            print("\n❌ No confident web matches found for this image — skipping blockchain upload.")
            return False

        if len(selectable_candidates) == 1:
            logger.info("Only one candidate found — auto-selecting.")
            selected_match = selectable_candidates[0]
        else:
            print("\n" + "=" * 70)
            print(f"  STEP 2 RESULTS — CANDIDATE MATCHES FOUND ({len(selectable_candidates)})")
            print("=" * 70)
            for idx, candidate in enumerate(selectable_candidates, 1):
                tier_badge = "⭐ FULL MATCH   " if candidate.get("match_confidence_tier") == "full_match" else "◐ PARTIAL MATCH"
                print(f"  [{idx}] {tier_badge} | {candidate.get('source')}")
                print(f"      \"{candidate.get('title')}\"")
                print(f"      {candidate.get('link')}\n")

            selected_match = None
            while selected_match is None:
                try:
                    user_input = input(f"Select a result to verify on-chain [1-{len(selectable_candidates)}], or 's' to skip blockchain upload: ").strip().lower()
                    if user_input == 's':
                        logger.info("Blockchain upload skipped by user choice.")
                        return True
                    if user_input.isdigit():
                        choice_idx = int(user_input) - 1
                        if 0 <= choice_idx < len(selectable_candidates):
                            selected_match = selectable_candidates[choice_idx]
                            logger.info(f"User selected Candidate [{user_input}]: '{selected_match['title']}' on {selected_match['source']}")
                        else:
                            print(f"Invalid choice. Please enter a number between 1 and {len(selectable_candidates)}, or 's'.")
                    else:
                        print(f"Invalid input. Please enter a number between 1 and {len(selectable_candidates)}, or 's'.")
                except (KeyboardInterrupt, EOFError):
                    print("\n\nSelection cancelled by user. Exiting pipeline.")
                    return False

        print(f"\n   Selected Matched Web Page:")
        print(f"     Title:  {selected_match['title']}")
        print(f"     Source: {selected_match['source']}")
        print(f"     Link:   {selected_match['link']}")

    except Exception as e:
        log_fatal_bug("STEP 2: REVERSE WEB SEARCH", e)
        return False

    # -------------------------------------------------------------------------
    # STEP 3: BLOCKCHAIN UPLOAD
    # -------------------------------------------------------------------------
    print_step_header(3, "Blockchain Upload (Ethereum Sepolia Testnet)")
    step3_start = time.time()
    try:
        upload_result = upload_record(selected_match)
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
        verification = verify_record(selected_match)
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
