import sys
import argparse
import json
from web3 import Web3

sys.path.append('blockchain_module')
from blockchain_utils import _connect_web3, _load_contract, fingerprint_post

def main():
    parser = argparse.ArgumentParser(description="Standalone verification tool for Face-verify-chain")
    parser.add_argument("--hash", type=str, help="Content hash (hex string) to verify")
    parser.add_argument("--link", type=str, help="Link of the post")
    parser.add_argument("--title", type=str, help="Title of the post")
    parser.add_argument("--source", type=str, help="Source of the post")
    args = parser.parse_args()

    content_hash = None

    if args.hash:
        if args.hash.startswith("0x"):
            content_hash = bytes.fromhex(args.hash[2:])
        else:
            content_hash = bytes.fromhex(args.hash)
        print(f"Using provided hash: 0x{content_hash.hex()}")
    elif args.link and args.title and args.source:
        matched_post = {"link": args.link, "title": args.title, "source": args.source}
        print("Hashing provided metadata...")
        content_hash = fingerprint_post(matched_post)
    else:
        print("Error: You must provide either --hash OR (--link, --title, and --source)")
        sys.exit(1)

    print("Connecting to Ethereum Sepolia...")
    w3 = _connect_web3()
    contract = _load_contract(w3)
    
    print(f"Executing read-only view call verifyRecord(0x{content_hash.hex()})...")
    
    try:
        exists, submitter, timestamp, metadata_uri = contract.functions.verifyRecord(content_hash).call()
    except Exception as e:
        print(f"Failed to query verifyRecord on contract: {e}")
        sys.exit(1)

    if not exists:
        print(f"❌ NO RECORD FOUND on-chain for content hash 0x{content_hash.hex()}")
        sys.exit(1)

    from datetime import datetime, timezone
    dt_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    
    print("\n🎉 ON-CHAIN RECORD VERIFIED!")
    print(f"   Submitter:    {submitter}")
    print(f"   Timestamp:    {dt_str}")
    print(f"   Metadata URI: {metadata_uri}")

if __name__ == "__main__":
    main()
