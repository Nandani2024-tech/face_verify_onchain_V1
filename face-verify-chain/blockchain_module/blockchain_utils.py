"""
blockchain_utils.py
--------------------
Step 3 of the pipeline: take the discovered post's data (or a hash of
it), write a tamper-evident fingerprint to the RecordVerification
contract on Ethereum Sepolia testnet, then re-read it back on-chain to
prove the record is genuinely there and unaltered.
"""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime, timezone
from web3 import Web3
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


def upload_record(matched_post: dict):
    """
    Hash the matched post, store the hash + link on-chain, and return
    the transaction hash + content hash for later verification.
    """
    logger.info("Initializing Blockchain Upload to Ethereum Sepolia...")
    rpc_url = os.environ.get("RPC_URL", "").strip()
    private_key = os.environ.get("PRIVATE_KEY", "").strip()
    chain_id = int(os.environ.get("CHAIN_ID", 11155111))

    if not rpc_url:
        logger.error("RPC_URL missing in .env!")
        raise KeyError("RPC_URL missing in .env")
    if not private_key:
        logger.error("PRIVATE_KEY missing in .env!")
        raise KeyError("PRIVATE_KEY missing in .env")

    logger.info(f"Connecting to RPC Endpoint: {rpc_url} (Expected Chain ID: {chain_id})")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        logger.error(f"Failed to connect to Ethereum RPC endpoint at: '{rpc_url}'")
        raise ConnectionError(f"Could not connect to RPC at {rpc_url}")

    actual_chain_id = w3.eth.chain_id
    logger.info(f"RPC Connection Established (Actual Chain ID: {actual_chain_id})")

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

    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price
    logger.info(f"Building storeRecord() Tx: Nonce={nonce}, GasPrice={w3.from_wei(gas_price, 'gwei'):.2f} Gwei, MetadataURI='{metadata_uri}'")

    try:
        tx = contract.functions.storeRecord(content_hash, metadata_uri).build_transaction({
            "from": account.address,
            "nonce": nonce,
            "gas": 300_000,
            "gasPrice": gas_price,
            "chainId": chain_id,
        })
    except Exception as e:
        logger.error(f"Failed to build storeRecord transaction (Hash may already exist on-chain): {e}")
        raise

    logger.info("Signing transaction with wallet private key...")
    signed_tx = account.sign_transaction(tx)

    logger.info("Broadcasting raw transaction to Ethereum network...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    logger.info(f"Transaction Broadcasted! Tx Hash: 0x{tx_hash.hex()}")
    logger.info("Waiting for block confirmation (mining)...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    tx_status = "SUCCESS (1)" if receipt.status == 1 else "REVERTED (0)"
    logger.info(f"Transaction Mined! Block #{receipt.blockNumber} | Status: {tx_status} | Gas Used: {receipt.gasUsed}")

    if receipt.status == 0:
        logger.error(f"Transaction REVERTED on-chain! Tx Hash: 0x{tx_hash.hex()}. Check if content hash was already submitted.")
        raise RuntimeError(f"On-chain transaction reverted for tx 0x{tx_hash.hex()}")

    return {
        "content_hash": content_hash.hex(),
        "tx_hash": tx_hash.hex(),
        "block_number": receipt.blockNumber,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def verify_record(matched_post: dict):
    """
    Recompute the hash of `matched_post` and check it against the
    on-chain record. Returns the on-chain record if found, else None.
    """
    logger.info("Initializing On-Chain Re-Verification...")
    rpc_url = os.environ.get("RPC_URL", "").strip()
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    contract = _load_contract(w3)

    content_hash = fingerprint_post(matched_post)
    logger.info(f"Executing read-only view call verifyRecord(0x{content_hash.hex()})...")

    try:
        exists, submitter, timestamp, metadata_uri = contract.functions.verifyRecord(content_hash).call()
    except Exception as e:
        logger.error(f"Failed to query verifyRecord on contract: {e}")
        raise

    if not exists:
        logger.warning(f"NO RECORD FOUND on-chain for content hash 0x{content_hash.hex()}")
        return None

    dt_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    logger.info(f"ON-CHAIN RECORD VERIFIED! Submitter: {submitter}, Timestamp: {dt_str}, MetadataURI: '{metadata_uri}'")

    return {
        "content_hash": content_hash.hex(),
        "submitter": submitter,
        "timestamp_utc": dt_str,
        "metadata_uri": metadata_uri,
    }

