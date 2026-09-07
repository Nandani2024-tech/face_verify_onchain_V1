"""
pipeline.py
-----------
End-to-end demo pipeline:

  1. Face scan     -> detect + encode a face from a local photo
  2. Web search     -> reverse-image-search that SAME local photo directly
                        (via Google Cloud Vision WEB_DETECTION + TEXT_DETECTION)
                        to find matching posts/pages on the web
  2.5 Selection    -> interactive console UI menu to pick candidate match
  3. Blockchain     -> hash the selected post, upload fingerprint + faceHash to
                        Ethereum Sepolia testnet
  4. Re-Verify      -> query smart contract to confirm record immutability
  5. Tamper Demo    -> demonstrate that single-char payload edits yield hash mismatches

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

# Terminal Colors & ANSI Styling
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_DIM = "\033[2m"
CLR_CYAN = "\033[36m"
CLR_GREEN = "\033[32m"
CLR_YELLOW = "\033[33m"
CLR_RED = "\033[31m"
CLR_MAGENTA = "\033[35m"
CLR_BLUE = "\033[34m"

CLR_B_CYAN = "\033[96;1m"
CLR_B_GREEN = "\033[92;1m"
CLR_B_YELLOW = "\033[93;1m"
CLR_B_MAGENTA = "\033[95;1m"
CLR_B_WHITE = "\033[97;1m"

if sys.platform == "win32":
    try:
        os.system("")  # Enable VT100 ANSI processing on Windows PowerShell/CMD
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Custom Logging Formatter with ANSI colors
class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[92;1m",     # Bright Green
        logging.WARNING: "\033[93;1m",  # Bright Yellow
        logging.ERROR: "\033[91;1m",    # Bright Red
        logging.CRITICAL: "\033[95;1m", # Bright Magenta
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, CLR_RESET)
        time_str = self.formatTime(record, self.datefmt)
        level_str = f"{color}[{record.levelname}]{CLR_RESET}"
        return f"[{time_str}] {level_str} {record.getMessage()}"

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
logger = logging.getLogger("pipeline")
logger.handlers = [handler]
logger.setLevel(logging.INFO)
logger.propagate = False

from face_id import encode_face
from reverse_search import reverse_image_search
from blockchain_utils import upload_record, verify_record, demonstrate_tamper_evidence


def print_step_header(step_num: int, title: str):
    print("\n" + CLR_B_CYAN + "=" * 70 + CLR_RESET)
    print(f"  {CLR_B_WHITE}STEP {step_num}{CLR_RESET} — {CLR_B_CYAN}{title.upper()}{CLR_RESET}")
    print(CLR_B_CYAN + "=" * 70 + CLR_RESET)


def log_fatal_bug(step_name: str, exc: Exception):
    tb = traceback.extract_tb(exc.__traceback__)
    last_frame = tb[-1] if tb else None
    
    print("\n" + CLR_RED + "!" * 70 + CLR_RESET)
    print(f"  ❌ {CLR_BOLD}FATAL FAILURE IN STEP: {step_name}{CLR_RESET}")
    print(CLR_RED + "!" * 70 + CLR_RESET)
    logger.error(f"Pipeline execution halted during [{step_name}]")
    logger.error(f"Error Type: {type(exc).__name__}")
    logger.error(f"Error Message: {exc}")
    
    if last_frame:
        filename = os.path.basename(last_frame.filename)
        logger.error(f"Bug Location: File '{filename}', Line {last_frame.lineno}, in Function '{last_frame.name}'")
        logger.error(f"Failing Line of Code: -> {last_frame.line}")
    
    print("\n--- Full Technical Traceback ---")
    traceback.print_exc()
    print(CLR_RED + "!" * 70 + CLR_RESET + "\n")


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
        face_fingerprint = face_result['fingerprint']
        logger.info(f"✅ STEP 1 COMPLETED in {round(time.time() - step1_start, 2)}s")
        print(f"   {CLR_B_WHITE}Face Location (top, right, bottom, left):{CLR_RESET} {CLR_CYAN}{face_result['location']}{CLR_RESET}")
        print(f"   {CLR_B_WHITE}Face Encoding SHA-256 Fingerprint:        {CLR_RESET}{CLR_B_MAGENTA}{face_fingerprint}{CLR_RESET}")
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

        # Display OCR text signal directly above candidate menu
        if text_signal:
            print(f"\n🔤 {CLR_B_YELLOW}Detected Text Signal:{CLR_RESET} {CLR_B_WHITE}{text_signal}{CLR_RESET}")
        if entity_guesses:
            print(f"💡 {CLR_B_CYAN}Related concepts detected:{CLR_RESET} {CLR_DIM}{', '.join(entity_guesses[:4])}{CLR_RESET}")

        # Filter valid selectable candidates (only items with real URLs)
        selectable_candidates = [m for m in matches if m.get("link")]

        if not selectable_candidates:
            print(f"\n{CLR_RED}❌ No confident web matches found for this image — skipping blockchain upload.{CLR_RESET}")
            return False

        if len(selectable_candidates) == 1:
            logger.info("Only one candidate found — auto-selecting.")
            selected_match = selectable_candidates[0]
        else:
            print("\n" + CLR_B_CYAN + "=" * 70 + CLR_RESET)
            print(f"  {CLR_B_WHITE}STEP 2 RESULTS — CANDIDATE MATCHES FOUND ({len(selectable_candidates)}){CLR_RESET}")
            print(CLR_B_CYAN + "=" * 70 + CLR_RESET)
            for idx, candidate in enumerate(selectable_candidates, 1):
                if candidate.get("match_confidence_tier") == "full_match":
                    tier_badge = f"{CLR_B_GREEN}⭐ FULL MATCH   {CLR_RESET}"
                else:
                    tier_badge = f"{CLR_B_YELLOW}◐ PARTIAL MATCH{CLR_RESET}"
                
                print(f"  {CLR_B_YELLOW}[{idx}]{CLR_RESET} {tier_badge} | {CLR_B_CYAN}{candidate.get('source')}{CLR_RESET}")
                print(f"      {CLR_B_WHITE}\"{candidate.get('title')}\"{CLR_RESET}")
                print(f"      {CLR_DIM}{candidate.get('link')}{CLR_RESET}\n")

            selected_match = None
            while selected_match is None:
                try:
                    user_input = input(f"{CLR_B_YELLOW}Select a result to verify on-chain [1-{len(selectable_candidates)}], or 's' to skip blockchain upload: {CLR_RESET}").strip().lower()
                    if user_input == 's':
                        logger.info("Blockchain upload skipped by user choice.")
                        return True
                    if user_input.isdigit():
                        choice_idx = int(user_input) - 1
                        if 0 <= choice_idx < len(selectable_candidates):
                            selected_match = selectable_candidates[choice_idx]
                            logger.info(f"User selected Candidate [{user_input}]: '{selected_match['title']}' on {selected_match['source']}")
                        else:
                            print(f"{CLR_RED}Invalid choice. Please enter a number between 1 and {len(selectable_candidates)}, or 's'.{CLR_RESET}")
                    else:
                        print(f"{CLR_RED}Invalid input. Please enter a number between 1 and {len(selectable_candidates)}, or 's'.{CLR_RESET}")
                except (KeyboardInterrupt, EOFError):
                    print(f"\n\n{CLR_YELLOW}Selection cancelled by user. Exiting pipeline.{CLR_RESET}")
                    return False

        print(f"\n   {CLR_B_WHITE}Selected Matched Web Page:{CLR_RESET}")
        print(f"     {CLR_B_CYAN}Title: {CLR_RESET} {CLR_B_WHITE}{selected_match['title']}{CLR_RESET}")
        print(f"     {CLR_B_CYAN}Source:{CLR_RESET} {CLR_YELLOW}{selected_match['source']}{CLR_RESET}")
        print(f"     {CLR_B_CYAN}Link:  {CLR_RESET} {CLR_DIM}{selected_match['link']}{CLR_RESET}")

    except Exception as e:
        log_fatal_bug("STEP 2: REVERSE WEB SEARCH", e)
        return False

    # -------------------------------------------------------------------------
    # STEP 3: BLOCKCHAIN UPLOAD
    # -------------------------------------------------------------------------
    print_step_header(3, "Blockchain Upload (Ethereum Sepolia Testnet)")
    step3_start = time.time()
    try:
        upload_result = upload_record(selected_match, face_fingerprint)
        logger.info(f"✅ STEP 3 COMPLETED in {round(time.time() - step3_start, 2)}s")
        
        c_hash = upload_result['content_hash']
        c_hash_str = c_hash if c_hash.startswith("0x") else f"0x{c_hash}"
        tx_val = upload_result['tx_hash']
        tx_str = tx_val if tx_val.startswith("0x") or tx_val == "ALREADY_STORED" else f"0x{tx_val}"
        
        contract_addr = upload_result.get('contract_address') or os.environ.get("CONTRACT_ADDRESS", "0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2").strip()
        contract_url = upload_result.get('contract_url') or f"https://sepolia.etherscan.io/address/{contract_addr}"
        tx_url = upload_result.get('tx_url') or (f"https://sepolia.etherscan.io/tx/{tx_str}" if tx_val != "ALREADY_STORED" else contract_url)

        print(f"   {CLR_B_WHITE}Keccak256 Content Hash:{CLR_RESET} {CLR_B_GREEN}{c_hash_str}{CLR_RESET}")
        print(f"   {CLR_B_WHITE}Ethereum Tx Hash:      {CLR_RESET} {CLR_B_YELLOW}{tx_str}{CLR_RESET}")
        print(f"   {CLR_B_WHITE}Tx Etherscan Link:     {CLR_RESET} {CLR_CYAN}{tx_url}{CLR_RESET}")
        print(f"   {CLR_B_WHITE}Contract Storage Link: {CLR_RESET} {CLR_CYAN}{contract_url}{CLR_RESET}")
        print(f"   {CLR_B_WHITE}Confirmed Block Number:{CLR_RESET} {CLR_B_CYAN}#{upload_result['block_number']}{CLR_RESET}")
        print(f"   {CLR_B_WHITE}Bound Face Hash:       {CLR_RESET} {CLR_B_MAGENTA}{upload_result['face_hash']}{CLR_RESET}")
    except Exception as e:
        log_fatal_bug("STEP 3: BLOCKCHAIN UPLOAD", e)
        return False

    # -------------------------------------------------------------------------
    # STEP 4: ON-CHAIN RE-VERIFICATION
    # -------------------------------------------------------------------------
    print_step_header(4, "On-Chain Re-Verification")
    step4_start = time.time()
    try:
        verification = verify_record(selected_match, face_fingerprint)
        if verification:
            logger.info(f"✅ STEP 4 COMPLETED in {round(time.time() - step4_start, 2)}s")
            print(f"\n🎉 {CLR_B_GREEN}SUCCESS: Record verified 100% authentic on Ethereum Sepolia Blockchain:{CLR_RESET}")
            print(CLR_CYAN + json.dumps(verification, indent=2) + CLR_RESET)

            # ON-CHAIN RECORD BREAKDOWN
            sub_addr = verification['submitter']
            sub_short = f"{sub_addr[:6]}...{sub_addr[-4:]}" if len(sub_addr) > 10 else sub_addr
            contract_addr = verification.get('contract_address') or os.environ.get("CONTRACT_ADDRESS", "0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2").strip()
            contract_url = verification.get('contract_url') or f"https://sepolia.etherscan.io/address/{contract_addr}"

            print("\n" + CLR_B_MAGENTA + "=" * 70 + CLR_RESET)
            print(f"  {CLR_B_WHITE}ON-CHAIN RECORD BREAKDOWN — WHAT EACH FIELD PROVES{CLR_RESET}")
            print(CLR_B_MAGENTA + "=" * 70 + CLR_RESET)
            print(f"  {CLR_B_CYAN}contractAddr {CLR_RESET}: {CLR_YELLOW}{contract_addr}{CLR_RESET} → {CLR_B_WHITE}Smart contract where record is stored{CLR_RESET}")
            print(f"                                   {CLR_CYAN}{contract_url}{CLR_RESET}")
            print(f"  {CLR_B_CYAN}submitter    {CLR_RESET}: {CLR_YELLOW}{sub_short:<16}{CLR_RESET} → {CLR_B_WHITE}Ethereum wallet that submitted this record{CLR_RESET}")
            print(f"  {CLR_B_CYAN}timestamp    {CLR_RESET}: {CLR_YELLOW}{verification['timestamp_utc']:<16}{CLR_RESET} → {CLR_B_WHITE}Exact UTC time this record was mined on-chain{CLR_RESET}")
            print(f"  {CLR_B_CYAN}metadataURI  {CLR_RESET}: {CLR_YELLOW}{verification['metadata_uri']}{CLR_RESET} → {CLR_B_WHITE}The verified web post this record refers to{CLR_RESET}")
            print(f"  {CLR_B_CYAN}faceHash     {CLR_RESET}: {CLR_B_MAGENTA}{verification['face_hash'][:12]}...{CLR_RESET}     → {CLR_B_WHITE}SHA-256 fingerprint of the face detected in{CLR_RESET}")
            print(f"                                   {CLR_DIM}Step 1 — cryptographically binds THIS face{CLR_RESET}")
            print(f"                                   {CLR_DIM}to THIS specific post, not just the post{CLR_RESET}")
            print(f"                                   {CLR_DIM}metadata alone{CLR_RESET}")
            print(f"  {CLR_B_CYAN}contentHash  {CLR_RESET}: {CLR_B_GREEN}0x{verification['content_hash'][:10]}...{CLR_RESET}   → {CLR_B_WHITE}Keccak256 hash used as the on-chain lookup{CLR_RESET}")
            print(f"                                   {CLR_DIM}key (derived from post title+source+link){CLR_RESET}")
            print(CLR_B_MAGENTA + "=" * 70 + CLR_RESET)
            print(f"✅ {CLR_B_GREEN}This proves: the face scanned in Step 1 was matched to the post above,{CLR_RESET}")
            print(f"   {CLR_B_GREEN}and that match was verified and timestamped immutably on Ethereum Sepolia.{CLR_RESET}\n")
        else:
            logger.error("❌ On-chain query returned False: Record not found in contract state!")
            return False
    except Exception as e:
        log_fatal_bug("STEP 4: ON-CHAIN RE-VERIFICATION", e)
        return False

    # -------------------------------------------------------------------------
    # STEP 5: LIVE TAMPER-EVIDENCE DEMONSTRATION
    # -------------------------------------------------------------------------
    step5_start = time.time()
    try:
        demonstrate_tamper_evidence(selected_match)
        logger.info(f"✅ STEP 5 COMPLETED in {round(time.time() - step5_start, 2)}s")
    except Exception as e:
        log_fatal_bug("STEP 5: TAMPER EVIDENCE DEMO", e)
        return False

    total_duration = round(time.time() - start_time, 2)
    print("\n" + CLR_B_CYAN + "=" * 70 + CLR_RESET)
    logger.info(f"🎉 PIPELINE EXECUTED SUCCESSFULLY IN {total_duration} SECONDS!")
    print(CLR_B_CYAN + "=" * 70 + CLR_RESET + "\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Face → Search → Blockchain verification pipeline")
    parser.add_argument("--face", required=True, help="Path to local photo — used for face detection and web search")
    args = parser.parse_args()

    run_pipeline(args.face)
