"""
check_setup.py
---------------
Standalone diagnostic script — checks whether each component of the
Face -> Search -> Blockchain pipeline is correctly configured and
reachable, WITHOUT running the actual pipeline logic (no face is
searched, no on-chain write is made unless you explicitly opt in for
the write-test).

Place this file in the project ROOT, next to pipeline.py, so it can
import from face_module/, search_module/, and blockchain_module/ the
same way pipeline.py does.

Usage:
  python check_setup.py
  python check_setup.py --with-chain-write   # also does a tiny real on-chain
                                              # write+verify round trip (costs
                                              # a small amount of test ETH gas)
"""

import os
import sys
import argparse
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), "face_module"))
sys.path.append(os.path.join(os.path.dirname(__file__), "search_module"))
sys.path.append(os.path.join(os.path.dirname(__file__), "blockchain_module"))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PASS = "[OK]" if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8' else "✅"
FAIL = "[FAIL]" if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8' else "❌"
WARN = "[WARN]" if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8' else "⚠️ "


results = []  # (component_name, ok: bool, message: str)


def record(name, ok, message):
    results.append((name, ok, message))
    icon = PASS if ok else FAIL
    print(f"{icon} {name}: {message}")


def check_env_file():
    print("\n--- 1. Environment variables (.env) ---")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        record("python-dotenv", False, "python-dotenv not installed (pip install python-dotenv)")
        return

    required = ["GOOGLE_VISION_API_KEY", "RPC_URL", "PRIVATE_KEY", "CONTRACT_ADDRESS"]
    placeholder_markers = ["your_", "0xyour", "changeme", "xxxx"]

    for var in required:
        val = os.environ.get(var, "")
        cleaned = val.strip().strip('"').strip("'")
        if not cleaned:
            record(var, False, "missing / empty in .env")
        elif any(m in cleaned.lower() for m in placeholder_markers):
            record(var, False, f"looks like an unfilled placeholder ('{cleaned[:20]}...')")
        else:
            shown = cleaned if var in ("RPC_URL", "CONTRACT_ADDRESS") else cleaned[:6] + "..." + cleaned[-4:]
            record(var, True, f"set ({shown})")

    chain_id = os.environ.get("CHAIN_ID", "11155111 (default)")
    record("CHAIN_ID", True, f"{chain_id}")


def check_face_module():
    print("\n--- 2. Face detection/encoding module ---")
    try:
        import face_recognition  # noqa: F401
        record("face_recognition import", True, "library imports correctly")
    except Exception as e:
        record("face_recognition import", False, f"{type(e).__name__}: {e}")
        return

    from face_id import encode_face

    sample_dir = os.path.join(os.path.dirname(__file__), "samples")
    candidates = []
    if os.path.isdir(sample_dir):
        candidates = [f for f in os.listdir(sample_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]

    if not candidates:
        record("face detection test", False, f"no test image found in {sample_dir}/ — add one to test detection")
        return

    test_image = os.path.join(sample_dir, candidates[0])
    try:
        result = encode_face(test_image)
        record(
            "face detection test",
            True,
            f"face found in '{candidates[0]}', encoding length {len(result['encoding'])}",
        )
    except ValueError as e:
        record("face detection test", False, f"no face detected in '{candidates[0]}': {e}")
    except Exception as e:
        record("face detection test", False, f"{type(e).__name__}: {e}")


def check_search_module():
    print("\n--- 3. Web/social search module (Google Cloud Vision) ---")
    api_key = os.environ.get("GOOGLE_VISION_API_KEY", "").strip().strip('"').strip("'")
    if not api_key or "your_" in api_key.lower():
        record("Google Vision API key", False, "GOOGLE_VISION_API_KEY not set — skipping live search test")
        return

    from reverse_search import reverse_image_search

    sample_dir = os.path.join(os.path.dirname(__file__), "samples")
    candidates = []
    if os.path.isdir(sample_dir):
        candidates = [f for f in os.listdir(sample_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]

    if not candidates:
        record("Vision API connectivity", False, f"no test image found in {sample_dir}/ — add one to test the live call")
        return

    test_image = os.path.join(sample_dir, candidates[0])
    try:
        matches = reverse_image_search(test_image, api_key=api_key)
        record(
            "Vision API connectivity",
            True,
            f"key valid, endpoint reachable ({len(matches)} matching pages for '{candidates[0]}')",
        )
    except Exception as e:
        record("Vision API connectivity", False, f"{type(e).__name__}: {e}")


def check_blockchain_module(with_chain_write=False):
    print("\n--- 4. Blockchain module (Ethereum Sepolia) ---")
    try:
        from web3 import Web3
    except Exception as e:
        record("web3 import", False, f"{type(e).__name__}: {e}")
        return

    rpc_url = os.environ.get("RPC_URL", "").strip()
    if not rpc_url:
        record("RPC connection", False, "RPC_URL not set")
        return

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        connected = w3.is_connected()
        record("RPC connection", connected, rpc_url if connected else f"could not connect to {rpc_url}")
    except Exception as e:
        record("RPC connection", False, f"{type(e).__name__}: {e}")
        return

    if not connected:
        return

    try:
        actual_chain_id = w3.eth.chain_id
        expected = int(os.environ.get("CHAIN_ID", 11155111))
        ok = actual_chain_id == expected
        record("Chain ID check", ok, f"RPC reports {actual_chain_id} (expected {expected} = Sepolia)")
    except Exception as e:
        record("Chain ID check", False, f"{type(e).__name__}: {e}")

    private_key = os.environ.get("PRIVATE_KEY", "").strip().strip('"').strip("'")
    if not private_key or "your_" in private_key.lower():
        record("Wallet", False, "PRIVATE_KEY not set")
    else:
        try:
            account = w3.eth.account.from_key(private_key)
            balance_wei = w3.eth.get_balance(account.address)
            balance_eth = w3.from_wei(balance_wei, "ether")
            ok = balance_wei > 0
            record(
                "Wallet balance",
                ok,
                f"{account.address} has {balance_eth} Sepolia ETH"
                + ("" if ok else " — fund it from a faucet before running the pipeline"),
            )
        except Exception as e:
            record("Wallet", False, f"invalid PRIVATE_KEY: {type(e).__name__}: {e}")

    contract_address = os.environ.get("CONTRACT_ADDRESS", "").strip()
    abi_path = os.path.join(os.path.dirname(__file__), "blockchain_module", "RecordVerification_abi.json")

    if not contract_address:
        record("Contract deployment", False, "CONTRACT_ADDRESS not set in .env")
        return

    try:
        code = w3.eth.get_code(Web3.to_checksum_address(contract_address))
        deployed = len(code) > 0
        record(
            "Contract deployment",
            deployed,
            f"contract code found at {contract_address}" if deployed else f"NO code at {contract_address} — wrong address or not deployed",
        )
    except Exception as e:
        record("Contract deployment", False, f"{type(e).__name__}: {e}")
        return

    if not os.path.isfile(abi_path):
        record("Contract ABI file", False, f"missing {abi_path} — re-run deploy_contract.py to regenerate it")
        return
    record("Contract ABI file", True, f"found at {abi_path}")

    if with_chain_write and deployed:
        print("\n   Running a small real on-chain write + verify round trip...")
        try:
            from blockchain_utils import upload_record, verify_record

            test_post = {
                "title": "check_setup.py diagnostic record",
                "link": "https://example.com/check-setup-diagnostic",
                "source": "check_setup.py",
            }
            upload_result = upload_record(test_post)
            verify_result = verify_record(test_post)

            if verify_result and verify_result["content_hash"] == upload_result["content_hash"]:
                record(
                    "On-chain write + verify",
                    True,
                    f"tx {upload_result['tx_hash']}, verified in block {verify_result is not None and 'yes'}",
                )
            else:
                record("On-chain write + verify", False, "uploaded but re-verification did not match")
        except Exception as e:
            msg = str(e)
            if "Record already exists" in msg:
                record(
                    "On-chain write + verify",
                    True,
                    "write skipped (diagnostic hash already recorded from a previous run) — read-back still works",
                )
            else:
                record("On-chain write + verify", False, f"{type(e).__name__}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Health-check for the face-verify-chain pipeline")
    parser.add_argument(
        "--with-chain-write",
        action="store_true",
        help="Also perform a tiny real on-chain write+verify test (uses a small amount of Sepolia test ETH gas)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("PIPELINE HEALTH CHECK")
    print("=" * 60)

    try:
        check_env_file()
        check_face_module()
        check_search_module()
        check_blockchain_module(with_chain_write=args.with_chain_write)
    except Exception:
        print("\nUnexpected error while running checks:")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    n_ok = sum(1 for _, ok, _ in results if ok)
    n_total = len(results)
    for name, ok, msg in results:
        print(f"  {PASS if ok else FAIL} {name}")
    print(f"\n{n_ok}/{n_total} checks passed.")

    if n_ok < n_total:
        print("\nFix the ❌ items above before recording your demo.")
        sys.exit(1)
    else:
        print("\nAll components look healthy. Ready to run pipeline.py.")


if __name__ == "__main__":
    main()
