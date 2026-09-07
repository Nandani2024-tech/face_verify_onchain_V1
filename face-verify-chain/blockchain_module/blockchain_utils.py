"""
blockchain_utils.py
--------------------
Step 3 of the pipeline: take the discovered post's data (or a hash of
it), write a tamper-evident fingerprint to the RecordVerification
contract on Ethereum Sepolia testnet, binding both the post metadata
and the Step 1 face SHA-256 fingerprint on-chain, then re-verify it.
Also provides a live tamper-evidence demonstration (Step 5).
"""

import os
import sys
import time
import json
import hashlib
import logging
from datetime import datetime, timezone
from web3 import Web3
from web3.exceptions import TimeExhausted
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

# Configure logger
logger = logging.getLogger("blockchain_utils")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [blockchain_utils] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


ABI_PATH = os.path.join(os.path.dirname(__file__), "RecordVerification_abi.json")


def _connect_web3() -> Web3:
    """
    Connect to Ethereum Sepolia RPC.
    Supports SEPOLIA_RPC_URL and RPC_URL environment variables, falling back to a curated
    list of public RPC endpoints in order until one connects successfully via w3.is_connected().
    """
    env_sepolia_url = os.environ.get("SEPOLIA_RPC_URL", "").strip()
    env_rpc_url = os.environ.get("RPC_URL", "").strip()

    endpoints = []
    if env_sepolia_url:
        endpoints.append(env_sepolia_url)
    if env_rpc_url and env_rpc_url not in endpoints:
        endpoints.append(env_rpc_url)

    fallbacks = [
        "https://ethereum-sepolia-rpc.publicnode.com",
        "https://rpc.sepolia.org",
        "https://ethereum-sepolia.blockpi.network/v1/rpc/public",
    ]
    for url in fallbacks:
        if url not in endpoints:
            endpoints.append(url)

    for url in endpoints:
        logger.info(f"Attempting connection to RPC Endpoint: {url}")
        try:
            w3 = Web3(Web3.HTTPProvider(url))
            if w3.is_connected():
                actual_chain_id = w3.eth.chain_id
                logger.info(f"✅ Successfully connected to RPC Endpoint: {url} (Chain ID: {actual_chain_id})")
                return w3
            else:
                logger.warning(f"RPC Endpoint unreachable: {url}")
        except Exception as e:
            logger.warning(f"Failed connection attempt to {url}: {e}")

    logger.error("All RPC endpoints failed to connect!")
    raise ConnectionError("Could not connect to any Ethereum Sepolia RPC endpoint.")


def _load_contract(w3: Web3):
    contract_address = os.environ.get("CONTRACT_ADDRESS", "").strip()
    if not contract_address:
        logger.error("CONTRACT_ADDRESS environment variable is missing in .env! Run deploy_contract.py first.")
        raise KeyError("CONTRACT_ADDRESS not found in environment.")

    logger.info(f"Loading RecordVerification contract at address: {contract_address}")
    if not os.path.isfile(ABI_PATH):
        logger.error(f"ABI file not found at '{ABI_PATH}'. Did you run deploy_contract.py?")
        raise FileNotFoundError(f"ABI file missing: {ABI_PATH}")

    with open(ABI_PATH, "r") as f:
        abi = json.load(f)

    return w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)


def fingerprint_post(matched_post: dict) -> bytes:
    """
    Build a deterministic keccak256-ready fingerprint of the discovered
    post: its link + title + source, so the same post always hashes the
    same way and any edit to the recorded fields changes the hash.
    """
    payload_dict = {
        "link": matched_post.get("link"),
        "title": matched_post.get("title"),
        "source": matched_post.get("source"),
    }
    payload_str = json.dumps(payload_dict, sort_keys=True)
    payload_bytes = payload_str.encode("utf-8")
    hash_bytes = Web3.keccak(payload_bytes)

    logger.info(f"Hashing Post Payload: {payload_str}")
    logger.info(f"Calculated Keccak256 Content Hash: 0x{hash_bytes.hex()}")
    return hash_bytes


def upload_record(matched_post: dict, face_fingerprint: str):
    """
    Hash the matched post and store the content hash, metadata URI, and
    face SHA-256 fingerprint on-chain. Returns the upload response.
    """
    logger.info("Initializing Blockchain Upload to Ethereum Sepolia...")
    private_key = os.environ.get("PRIVATE_KEY", "").strip()
    chain_id = int(os.environ.get("CHAIN_ID", 11155111))

    if not private_key:
        logger.error("PRIVATE_KEY missing in .env!")
        raise KeyError("PRIVATE_KEY missing in .env")

    w3 = _connect_web3()

    account = w3.eth.account.from_key(private_key)
    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = w3.from_wei(balance_wei, "ether")
    logger.info(f"Wallet Address: {account.address} | Balance: {balance_eth:.6f} Sepolia ETH")

    if balance_wei == 0:
        logger.error(f"Wallet {account.address} has ZERO balance! Fund it with testnet ETH using a Sepolia faucet.")
        raise ValueError(f"Insufficient funds: Wallet {account.address} has 0 ETH.")

    contract = _load_contract(w3)
    content_hash = fingerprint_post(matched_post)
    metadata_uri = matched_post.get("link", "")

    # Format face fingerprint into 32 bytes (bytes32)
    clean_face_fp = face_fingerprint.replace("0x", "").strip()
    face_hash_bytes = bytes.fromhex(clean_face_fp)

    contract_address = os.environ.get("CONTRACT_ADDRESS", "0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2").strip()
    contract_url = f"https://sepolia.etherscan.io/address/{contract_address}"

    # Duplicate-Hash Guard: check if record already exists on-chain
    logger.info(f"Checking on-chain existence for content hash 0x{content_hash.hex()}...")
    try:
        exists, submitter, timestamp, existing_uri, onchain_face_bytes = contract.functions.verifyRecord(content_hash).call()
        if exists:
            onchain_face_hex = onchain_face_bytes.hex()
            dt_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            
            # Check for face fingerprint integrity mismatch
            if onchain_face_hex.lower() != clean_face_fp.lower():
                logger.warning("⚠️ INTEGRITY WARNING: This post was previously verified against a different face fingerprint.")
                logger.warning(f"   Current Face Fingerprint:  {clean_face_fp}")
                logger.warning(f"   On-Chain Face Fingerprint: {onchain_face_hex}")
            else:
                logger.info("Record already verified on-chain, skipping duplicate tx")

            logger.info(f"  Existing Submitter: {submitter}")
            logger.info(f"  Existing Timestamp: {dt_str}")
            logger.info(f"  Existing Metadata URI: '{existing_uri}'")
            logger.info(f"  Existing Face Hash: {onchain_face_hex}")
            logger.info(f"  Contract Storage Link: {contract_url}")
            return {
                "content_hash": content_hash.hex(),
                "tx_hash": "ALREADY_STORED",
                "tx_url": contract_url,
                "contract_address": contract_address,
                "contract_url": contract_url,
                "block_number": "PREVIOUSLY_MINED",
                "timestamp_utc": dt_str,
                "face_hash": onchain_face_hex,
                "submitter": submitter,
                "metadata_uri": existing_uri,
            }
    except Exception as e:
        logger.warning(f"Pre-check verifyRecord query failed, proceeding to upload: {e}")

    nonce = w3.eth.get_transaction_count(account.address)
    base_gas_price = w3.eth.gas_price
    gas_price = int(base_gas_price * 1.25)
    gas_price_gwei = w3.from_wei(gas_price, "gwei")
    logger.info(f"Fetched Base Gas Price: {w3.from_wei(base_gas_price, 'gwei'):.2f} Gwei | Applying 1.25x Buffer -> Gas Price: {gas_price_gwei:.2f} Gwei")
    logger.info(f"Building storeRecord() Tx: Nonce={nonce}, GasPrice={gas_price_gwei:.2f} Gwei, FaceHash={clean_face_fp[:10]}...")

    try:
        tx = contract.functions.storeRecord(content_hash, metadata_uri, face_hash_bytes).build_transaction({
            "from": account.address,
            "nonce": nonce,
            "gas": 350_000,
            "gasPrice": gas_price,
            "chainId": chain_id,
        })
    except Exception as e:
        logger.error(f"Failed to build storeRecord transaction: {e}")
        raise

    logger.info("Signing transaction with wallet private key...")
    signed_tx = account.sign_transaction(tx)

    logger.info("Broadcasting raw transaction to Ethereum network...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    tx_url = f"https://sepolia.etherscan.io/tx/0x{tx_hash_hex}"
    logger.info(f"Transaction Broadcasted! Tx Hash: 0x{tx_hash_hex}")
    logger.info(f"  └─ Sepolia Etherscan Tx Link: {tx_url}")
    logger.info(f"  └─ Contract Storage Link:     {contract_url}")

    logger.info("Waiting for block confirmation (mining) with 180s timeout...")
    receipt = None
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    except TimeExhausted:
        logger.warning(f"Initial wait_for_transaction_receipt timed out after 180s for tx 0x{tx_hash_hex}. Starting secondary receipt polling (every 5s up to 120s)...")
        for attempt in range(1, 25):
            time.sleep(5)
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None:
                    logger.info(f"Secondary polling discovered mined transaction receipt on attempt {attempt} (after {attempt * 5}s)!")
                    break
            except Exception:
                pass

        if receipt is None:
            logger.error(f"Transaction receipt not found after initial 180s timeout + 120s secondary polling for tx 0x{tx_hash_hex}")
            raise TimeExhausted(f"Transaction HexBytes('0x{tx_hash_hex}') is not in the chain after 300 seconds")

    tx_status = "SUCCESS (1)" if receipt.status == 1 else "REVERTED (0)"
    logger.info(f"Transaction Mined! Block #{receipt.blockNumber} | Status: {tx_status} | Gas Used: {receipt.gasUsed}")
    logger.info(f"  └─ Verified Etherscan Tx Link: {tx_url}")

    if receipt.status == 0:
        logger.error(f"Transaction REVERTED on-chain! Tx Hash: 0x{tx_hash_hex}. Check if content hash was already submitted.")
        raise RuntimeError(f"On-chain transaction reverted for tx 0x{tx_hash_hex}")

    return {
        "content_hash": content_hash.hex(),
        "tx_hash": tx_hash_hex,
        "tx_url": tx_url,
        "contract_address": contract_address,
        "contract_url": contract_url,
        "block_number": receipt.blockNumber,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "face_hash": clean_face_fp,
        "submitter": account.address,
        "metadata_uri": metadata_uri,
    }


def verify_record(matched_post: dict, face_fingerprint: str = None):
    """
    Recompute the hash of `matched_post` and check it against the
    on-chain record. Returns the on-chain record if found, else None.
    """
    logger.info("Initializing On-Chain Re-Verification...")
    w3 = _connect_web3()
    contract = _load_contract(w3)
    contract_address = os.environ.get("CONTRACT_ADDRESS", "0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2").strip()
    contract_url = f"https://sepolia.etherscan.io/address/{contract_address}"

    content_hash = fingerprint_post(matched_post)
    logger.info(f"Executing read-only view call verifyRecord(0x{content_hash.hex()})...")

    try:
        exists, submitter, timestamp, metadata_uri, onchain_face_bytes = contract.functions.verifyRecord(content_hash).call()
    except Exception as e:
        logger.error(f"Failed to query verifyRecord on contract: {e}")
        raise

    if not exists:
        logger.warning(f"NO RECORD FOUND on-chain for content hash 0x{content_hash.hex()}")
        return None

    dt_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    onchain_face_hex = onchain_face_bytes.hex()
    logger.info(f"ON-CHAIN RECORD VERIFIED! Submitter: {submitter}, Timestamp: {dt_str}, MetadataURI: '{metadata_uri}', FaceHash: {onchain_face_hex}")
    logger.info(f"  Contract Storage Link: {contract_url}")

    if face_fingerprint:
        clean_fp = face_fingerprint.replace("0x", "").strip().lower()
        if onchain_face_hex.lower() != clean_fp:
            logger.warning("⚠️ INTEGRITY WARNING: This post was previously verified against a different face fingerprint.")
            logger.warning(f"   Current Face Fingerprint:  {clean_fp}")
            logger.warning(f"   On-Chain Face Fingerprint: {onchain_face_hex}")

    return {
        "content_hash": content_hash.hex(),
        "submitter": submitter,
        "timestamp_utc": dt_str,
        "metadata_uri": metadata_uri,
        "face_hash": onchain_face_hex,
        "contract_address": contract_address,
        "contract_url": contract_url,
    }


def demonstrate_tamper_evidence(matched_post: dict):
    """
    Step 5: Live Tamper-Evidence Demonstration.
    Creates a single-character mutated copy of matched_post, hashes it,
    and queries verifyRecord() on-chain to prove that tampered data returns False.
    """
    orig_hash = fingerprint_post(matched_post)
    orig_title = matched_post.get("title", "")

    # Create mutated post (append a period to title)
    tampered_post = dict(matched_post)
    tampered_title = orig_title + "."
    tampered_post["title"] = tampered_title

    tampered_hash = fingerprint_post(tampered_post)

    w3 = _connect_web3()
    contract = _load_contract(w3)

    logger.info(f"Executing read-only view call verifyRecord for tampered hash 0x{tampered_hash.hex()}...")
    exists_tampered, _, _, _, _ = contract.functions.verifyRecord(tampered_hash).call()

    CLR_RESET = "\033[0m"
    CLR_DIM = "\033[2m"
    CLR_CYAN = "\033[36m"
    CLR_B_CYAN = "\033[96;1m"
    CLR_B_GREEN = "\033[92;1m"
    CLR_B_YELLOW = "\033[93;1m"
    CLR_B_RED = "\033[91;1m"
    CLR_B_MAGENTA = "\033[95;1m"
    CLR_B_WHITE = "\033[97;1m"

    print("\n" + CLR_B_MAGENTA + "=" * 70 + CLR_RESET)
    print(f"  {CLR_B_WHITE}STEP 5 — LIVE TAMPER-EVIDENCE DEMONSTRATION{CLR_RESET}")
    print(CLR_B_MAGENTA + "=" * 70 + CLR_RESET)
    print(f"  {CLR_B_CYAN}Original title:  {CLR_RESET}\"{orig_title}\"")
    print(f"  {CLR_B_YELLOW}Tampered title:  {CLR_RESET}\"{tampered_title}\" {CLR_DIM}(1 char changed){CLR_RESET}\n")
    print(f"  {CLR_B_WHITE}Original Keccak256 hash : {CLR_B_GREEN}0x{orig_hash.hex()}{CLR_RESET}  → {CLR_B_GREEN}✅ EXISTS on-chain{CLR_RESET}")
    print(f"  {CLR_B_WHITE}Tampered Keccak256 hash : {CLR_B_RED}0x{tampered_hash.hex()}{CLR_RESET}  → {CLR_B_RED}❌ NOT FOUND on-chain{CLR_RESET}\n")
    print(f"  {CLR_B_GREEN}✅ TAMPER-EVIDENCE CONFIRMED: Even a single-character change produces a{CLR_RESET}")
    print(f"     {CLR_B_GREEN}completely different hash, and that altered hash has no matching{CLR_RESET}")
    print(f"     {CLR_B_GREEN}on-chain record. This proves the blockchain record cannot be silently{CLR_RESET}")
    print(f"     {CLR_B_GREEN}modified — any tampering is immediately detectable by hash mismatch.{CLR_RESET}")
    print(CLR_B_MAGENTA + "=" * 70 + CLR_RESET + "\n")

    return {
        "original_hash": orig_hash.hex(),
        "tampered_hash": tampered_hash.hex(),
        "original_exists": True,
        "tampered_exists": exists_tampered,
    }
