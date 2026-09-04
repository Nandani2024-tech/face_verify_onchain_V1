"""
blockchain_utils.py
--------------------
Step 3 of the pipeline: take the discovered post's data (or a hash of
it), write a tamper-evident fingerprint to the RecordVerification
contract on Ethereum Sepolia testnet, then re-read it back on-chain to
prove the record is genuinely there and unaltered.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()


ABI_PATH = os.path.join(os.path.dirname(__file__), "RecordVerification_abi.json")


def _load_contract(w3: Web3):
    contract_address = os.environ["CONTRACT_ADDRESS"]
    with open(ABI_PATH, "r") as f:
        abi = json.load(f)
    return w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)


def fingerprint_post(matched_post: dict) -> bytes:
    """
    Build a deterministic keccak256-ready fingerprint of the discovered
    post: its link + title + source, so the same post always hashes the
    same way and any edit to the recorded fields changes the hash.
    """
    payload = json.dumps(
        {
            "link": matched_post.get("link"),
            "title": matched_post.get("title"),
            "source": matched_post.get("source"),
        },
        sort_keys=True,
    ).encode("utf-8")

    return Web3.keccak(payload)


def upload_record(matched_post: dict):
    """
    Hash the matched post, store the hash + link on-chain, and return
    the transaction hash + content hash for later verification.
    """
    rpc_url = os.environ["RPC_URL"]
    private_key = os.environ["PRIVATE_KEY"]
    chain_id = int(os.environ.get("CHAIN_ID", 11155111))  # Sepolia

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = w3.eth.account.from_key(private_key)
    contract = _load_contract(w3)

    content_hash = fingerprint_post(matched_post)
    metadata_uri = matched_post.get("link", "")

    nonce = w3.eth.get_transaction_count(account.address)
    tx = contract.functions.storeRecord(content_hash, metadata_uri).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 300_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })

    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

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
    rpc_url = os.environ["RPC_URL"]
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    contract = _load_contract(w3)

    content_hash = fingerprint_post(matched_post)
    exists, submitter, timestamp, metadata_uri = contract.functions.verifyRecord(content_hash).call()

    if not exists:
        return None

    return {
        "content_hash": content_hash.hex(),
        "submitter": submitter,
        "timestamp_utc": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
        "metadata_uri": metadata_uri,
    }
