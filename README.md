# Face-verify-chain V1
> **Immutable digital identity verification using facial recognition, reverse web search, and the Ethereum blockchain.**

---

## Overview
In the modern digital landscape, proving the provenance and authenticity of one's digital footprint is increasingly difficult. Deepfakes, impersonation, and unverified social media profiles make it challenging to separate genuine online presence from fabricated identities. 

**Face-verify-chain V1** solves this by establishing a decentralized, tamper-proof anchor for an individual's digital identity. It allows a user to take a local photo, automatically locate their real-world footprint on the web (e.g., a verified social media or professional profile), and permanently record a cryptographic fingerprint binding the scanned face to that match on the Ethereum blockchain. By leveraging the immutability of smart contracts, this pipeline creates a verifiable, timestamped proof of identity that cannot be silently altered or erased, bridging physical biometric data, Web2 social presence, and Web3 decentralized trust.

---

## Pipeline Architecture
The system operates as an automated 5-stage pipeline with interactive verification:

`Face Image` → `Biometric Encoding` → `Multi-Feature Reverse Web Search & OCR` → `Human Candidate Selection` → `On-Chain Face+Post Binding` → `Re-Verification & Breakdown` → `Live Tamper Demonstration`

1. **Face Scan & Encoding (Step 1):** Detects human faces in the input image, extracts a 128-dimensional facial feature vector using `dlib` ResNet, and calculates a local SHA-256 biometric fingerprint (`faceHash`).
2. **Reverse Web Search & OCR (Step 2):** Queries Google Cloud Vision API using `WEB_DETECTION` and `TEXT_DETECTION`. Ranks exact image matches (`full_match`) over partial ones and extracts visible text/logos as disambiguation signals.
3. **Interactive Candidate Selection (Step 2.5):** Displays a console menu of up to 5 ranked candidates for human verification before writing irreversibly to the blockchain.
4. **Blockchain Upload & Binding (Step 3):** Hashes post metadata into a `keccak256` content hash and binds both the post metadata and the Step 1 `faceHash` on the Ethereum Sepolia blockchain.
5. **On-Chain Re-Verification & Breakdown (Step 4):** Reads back the stored state on-chain and outputs a 5-field proof breakdown (`submitter`, `timestamp`, `metadataURI`, `faceHash`, `contentHash`).
6. **Live Tamper Demonstration (Step 5):** Automatically queries the smart contract with a single-character tampered version of the payload to prove on-camera that altered data returns `exists: false`.

---

## Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.11 | Core runtime environment with ANSI terminal color styling. |
| **Face Recognition** | `face_recognition` / `dlib` | Detects bounding boxes and extracts 128-d HOG facial feature encodings. |
| **Reverse Search & OCR** | Google Cloud Vision API | Uses `WEB_DETECTION` and `TEXT_DETECTION` to scour the web for matches and visible text signals. |
| **Web3 / Blockchain** | `web3.py` (v6+) | Handles RPC failovers, 1.25x gas buffer, transaction signing, and contract interactions. |
| **Smart Contract** | Solidity (`^0.8.20`) | `RecordVerification.sol` contract deployed on Ethereum Sepolia testnet. |

---

## Blockchain Details & Smart Contract

- **Network:** Ethereum Sepolia Testnet (Chain ID: `11155111`)
- **Smart Contract Name:** `RecordVerification.sol`
- **Deployed Contract Address:** [`0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2`](https://sepolia.etherscan.io/address/0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2#code)
- **✅ Verified Source Code:** [https://sepolia.etherscan.io/address/0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2#code](https://sepolia.etherscan.io/address/0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2#code)

### Contract Functions

- **`storeRecord(bytes32 contentHash, string calldata metadataURI, bytes32 faceHash)`**:
  Stores a new verification record. Hashes the post payload into `contentHash`, stores the target `metadataURI`, and cryptographically binds the Step 1 `faceHash` (SHA-256 face fingerprint). Reverts if `contentHash` already exists.
- **`verifyRecord(bytes32 contentHash)`**:
  A read-only (`view`) function returning `(bool exists, address submitter, uint256 timestamp, string memory metadataURI, bytes32 faceHash)`.

---

## Why Face-Hash Binding Matters

In simple Web3 verification systems, storing a post URL or content hash only proves that a post existed at a certain time. It does **not** prove who was in the photo or which face was scanned.

By adding `bytes32 faceHash` directly into the smart contract state and `storeRecord` signature, **Face-verify-chain V1** cryptographically links:

$$\text{Local Biometric Face Fingerprint} \longleftrightarrow \text{Web Search Match Metadata} \longleftrightarrow \text{Ethereum Blockchain Record}$$

This ensures that the on-chain record doesn't just verify a web URL — it proves that **this specific scanned face** was matched to **this specific web post**, establishing genuine end-to-end provenance.

---

## Interactive Multi-Candidate Search

Because blockchain writes are permanent and cost gas, automatic selection of a single web search result can lead to incorrect state on-chain. Step 2 in **Face-verify-chain V1** returns up to 5 ranked candidates categorized into confidence tiers:
- **`⭐ FULL MATCH`**: Exact matching image found on the web page.
- **`◐ PARTIAL MATCH`**: Partial image match or related page match.

Before any transaction is created, the system presents an interactive menu:

```text
======================================================================
  STEP 2 RESULTS — CANDIDATE MATCHES FOUND (5)
======================================================================
  [1] ⭐ FULL MATCH    | medium.com
      "Anshuman Singh of Scaler: Five Things You Need To Create A ..."
      https://medium.com/authority-magazine/anshuman-singh-of-scaler-five-things-you-need-to-create-a-highly-successful-startup-f73346e7a39e

  [2] ◐ PARTIAL MATCH | www.youtube.com
      "Captain #Anshuman Singh's wife Smt Smriti shares the story of her ..."
      https://www.youtube.com/watch?v=xYqmKwW5Ck4

Select a result to verify on-chain [1-5], or 's' to skip blockchain upload: 
```

The operator can inspect candidates, confirm the correct match, or press `'s'` to skip the transaction entirely. If only 1 candidate exists, it auto-selects.

---

## OCR-Assisted Disambiguation

Google Cloud Vision's `TEXT_DETECTION` feature scans the photo for printed text, clothing logos, brand names, or captions. For example, scanning a photo with a shirt logo extracts text signals:
```text
🔤 Detected Text Signal: SCA ER ACADMY
💡 Related concepts detected: Anshuman Singh, IIIT-H, InterviewBit, Kirti Chakra
```
These OCR signals display directly above the candidate menu, providing crucial context for the human operator when choosing between visually similar candidates.

---

## Network Reliability (RPC Fallback & Gas Handling)

To eliminate testnet timeouts (`web3.exceptions.TimeExhausted`) and RPC failures during live demos, the system incorporates:
1. **Multi-RPC Fallback List:** Automatically tries `SEPOLIA_RPC_URL`, `RPC_URL`, `publicnode.com`, `rpc.sepolia.org`, and `blockpi.network` in order until a healthy connection is established via `w3.is_connected()`.
2. **1.25x Gas Price Buffer:** Multiplies current `gas_price` by 1.25x to ensure transactions are prioritized by miners during network congestion.
3. **Extended 180s Timeout + Polling Retry:** If initial confirmation times out, the system polls `get_transaction_receipt` every 5 seconds for up to 120 additional seconds.
4. **Pre-Upload Duplicate Check:** Calls `verifyRecord()` before broadcasting `storeRecord()`. If the content hash already exists on-chain, it skips transaction creation (`tx_hash: 0xALREADY_STORED`), saving testnet ETH gas.

---

## Step 5: Live Tamper-Evidence Demonstration

Immediately after Step 4, the pipeline automatically demonstrates tamper-evidence:
1. Takes the verified post metadata payload `{link, source, title}`.
2. Creates a single-character mutated copy (e.g. appending a period to the title).
3. Hashes both original and tampered payloads via `keccak256`.
4. Executes a read-only `verifyRecord` call for the tampered hash.

```text
======================================================================
  STEP 5 — LIVE TAMPER-EVIDENCE DEMONSTRATION
======================================================================
  Original title:  "Captain #Anshuman Singh's wife Smt Smriti shares the story of her ..."
  Tampered title:  "Captain #Anshuman Singh's wife Smt Smriti shares the story of her ...." (1 char changed)

  Original Keccak256 hash : 0x2750934180104aa2df2865adfaefee96b901da4855d2bb77e83dcdb1473339fd  → ✅ EXISTS on-chain
  Tampered Keccak256 hash : 0x19aa3dd7047edabc811008d3b6158502d9f93648c830d54a331d5f00cfdfa6d3  → ❌ NOT FOUND on-chain

  ✅ TAMPER-EVIDENCE CONFIRMED: Even a single-character change produces a
     completely different hash, and that altered hash has no matching
     on-chain record. This proves the blockchain record cannot be silently
     modified — any tampering is immediately detectable by hash mismatch.
======================================================================
```
*Because this is a read-only view call, it runs instantly with 0 gas cost.*

---

## Integrity Warning: Cross-Face Detection

Before uploading, the system checks whether the selected web post's content hash was previously recorded under a **different face fingerprint**. If a match exists but `faceHash` does not match the current run's biometric scan, it logs a warning:
```text
⚠️ INTEGRITY WARNING: This post was previously verified against a different face fingerprint.
   Current Face Fingerprint:  17c505d55df714da38c3815c...
   On-Chain Face Fingerprint: a74eff834249816a7c9f4dc5...
```
This integrity check guards against misattributing an already-verified post to a different individual.

---

## Independent Verification (No Trust Required)

Anyone (including evaluators or third parties) can independently verify any on-chain record **without running the full AI pipeline** using either method:

### Method A: Direct on Sepolia Etherscan (No Code Needed)
1. Visit the verified contract on Etherscan: [Sepolia Etherscan Read Contract Tab](https://sepolia.etherscan.io/address/0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2#readContract).
2. Query `verifyRecord` by entering any recorded 32-byte `contentHash` (e.g. `0x2750934180104aa2df2865adfaefee96b901da4855d2bb77e83dcdb1473339fd`).
3. Click **Query** to see `exists: true`, submitter address, UTC timestamp, `metadataURI`, and `faceHash`.

### Method B: Standalone Verification Script (`verify_only.py`)
Run the lightweight verifier script using a content hash:
```bash
python verify_only.py --hash 0x2750934180104aa2df2865adfaefee96b901da4855d2bb77e83dcdb1473339fd
```
Or verify by passing raw post fields:
```bash
python verify_only.py --link "https://www.youtube.com/watch?v=xYqmKwW5Ck4" --title "Captain #Anshuman Singh's wife Smt Smriti shares the story of her ..." --source "www.youtube.com"
```

---

## Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Nandani2024-tech/face_verify_onchain_V1.git
   cd face_verify_onchain_V1/face-verify-chain
   ```

2. **Create and activate virtual environment:**
   ```powershell
   # Windows PowerShell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Copy `.env.example` to `.env` and fill in:
   - `GOOGLE_VISION_API_KEY`: Your Google Cloud Vision API Key.
   - `RPC_URL`: `https://ethereum-sepolia-rpc.publicnode.com`
   - `PRIVATE_KEY`: Testnet wallet private key funded with free Sepolia ETH.
   - `CONTRACT_ADDRESS`: `0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2`

---

## Usage & Terminal Output

### Diagnostic Health Check
```powershell
python check_setup.py
```
*(Confirms 13/13 environment checks pass).*

### Running the Full Pipeline
```powershell
python pipeline.py --face samples/anshuman.jpg
```

**Actual Terminal Output:**

```text
[2026-09-07 13:08:29] [INFO] Starting Face -> Search -> Blockchain Verification Pipeline...

======================================================================
  STEP 1 — FACE SCAN & ENCODING (FACE_ID.PY)
======================================================================
[2026-09-07 13:08:29] [INFO] [face_id] Loading image from path: 'samples/anshuman.jpg'
[2026-09-07 13:08:29] [INFO] [face_id] Detected 1 face(s) in image.
[2026-09-07 13:08:30] [INFO] [face_id] Local Face SHA-256 Fingerprint: a74eff834249816a7c9f4dc5fce5239f59ec7d7acc383c283dd2fb1a04545501
[2026-09-07 13:08:30] [INFO] ✅ STEP 1 COMPLETED in 0.88s
   Face Location (top, right, bottom, left): (219, 752, 374, 597)
   Face Encoding SHA-256 Fingerprint:        a74eff834249816a7c9f4dc5fce5239f59ec7d7acc383c283dd2fb1a04545501

======================================================================
  STEP 2 — WEB / SOCIAL MEDIA SEARCH (GOOGLE CLOUD VISION)
======================================================================
[2026-09-07 13:08:31] [INFO] [reverse_search] Detected Text Signals: 'SCA ER ACADMY'
[2026-09-07 13:08:31] [INFO] ✅ STEP 2 COMPLETED in 1.27s

🔤 Detected Text Signal: SCA ER ACADMY
💡 Related concepts detected: Anshuman Singh, IIIT-H, InterviewBit, Kirti Chakra

======================================================================
  STEP 2 RESULTS — CANDIDATE MATCHES FOUND (5)
======================================================================
  [1] ⭐ FULL MATCH    | medium.com
      "Anshuman Singh of Scaler: Five Things You Need To Create A ..."
      https://medium.com/authority-magazine/anshuman-singh-of-scaler-five-things-you-need-to-create-a-highly-successful-startup-f73346e7a39e

  [2] ◐ PARTIAL MATCH | www.youtube.com
      "Captain #Anshuman Singh's wife Smt Smriti shares the story of her ..."
      https://www.youtube.com/watch?v=xYqmKwW5Ck4

Select a result to verify on-chain [1-5], or 's' to skip blockchain upload: 2
[2026-09-07 13:08:37] [INFO] User selected Candidate [2]: 'Captain #Anshuman Singh's wife Smt Smriti...'

======================================================================
  STEP 3 — BLOCKCHAIN UPLOAD (ETHEREUM SEPOLIA TESTNET)
======================================================================
[2026-09-07 17:42:07] [INFO] [blockchain_utils] Transaction Broadcasted! Tx Hash: 0x00219a0996024d0ce43313ff26ff94f96925c59b5d99297c1ddb5f35629987a3
[2026-09-07 17:42:07] [INFO] [blockchain_utils]   └─ Sepolia Etherscan Tx Link: https://sepolia.etherscan.io/tx/0x00219a0996024d0ce43313ff26ff94f96925c59b5d99297c1ddb5f35629987a3
[2026-09-07 17:42:07] [INFO] [blockchain_utils]   └─ Contract Storage Link:     https://sepolia.etherscan.io/address/0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2
[2026-09-07 17:42:13] [INFO] ✅ STEP 3 COMPLETED in 9.92s
   Keccak256 Content Hash: 0x5f0c50885078501e6e2ddcd45af6ff664a86e71924ff7492d39c74085172f336
   Ethereum Tx Hash:       0x00219a0996024d0ce43313ff26ff94f96925c59b5d99297c1ddb5f35629987a3
   Tx Etherscan Link:      https://sepolia.etherscan.io/tx/0x00219a0996024d0ce43313ff26ff94f96925c59b5d99297c1ddb5f35629987a3
   Contract Storage Link:  https://sepolia.etherscan.io/address/0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2
   Confirmed Block Number: #11654088
   Bound Face Hash:        67eca8e6993971a3c19d4974c028d23b7c2836d81ef925dbd6c09e5887855eab

======================================================================
  STEP 4 — ON-CHAIN RE-VERIFICATION
======================================================================
[2026-09-07 17:42:15] [INFO] ✅ STEP 4 COMPLETED in 1.51s

🎉 SUCCESS: Record verified 100% authentic on Ethereum Sepolia Blockchain:
{
  "content_hash": "5f0c50885078501e6e2ddcd45af6ff664a86e71924ff7492d39c74085172f336",
  "submitter": "0x897Cd1ec614FC08Db1e42EB68Dc3d27bA8CB59df",
  "timestamp_utc": "2026-09-07T12:12:12+00:00",
  "metadata_uri": "https://en.wikipedia.org/wiki/Sam_Altman",
  "face_hash": "67eca8e6993971a3c19d4974c028d23b7c2836d81ef925dbd6c09e5887855eab",
  "contract_address": "0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2",
  "contract_url": "https://sepolia.etherscan.io/address/0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2"
}

======================================================================
  ON-CHAIN RECORD BREAKDOWN — WHAT EACH FIELD PROVES
======================================================================
  contractAddr : 0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2 → Smart contract where record is stored
                                   https://sepolia.etherscan.io/address/0xC7aCba7522EF4c6f1b3c738Fa879773f0A69EBd2
  submitter    : 0x897C...59df    → Ethereum wallet that submitted this record
  timestamp    : 2026-09-07T12:12:12+00:00 → Exact UTC time this record was mined on-chain
  metadataURI  : https://en.wikipedia.org/wiki/Sam_Altman → The verified web post this record refers to
  faceHash     : 67eca8e69939...     → SHA-256 fingerprint of the face detected in
                                   Step 1 — cryptographically binds THIS face
                                   to THIS specific post, not just the post
                                   metadata alone
  contentHash  : 0x5f0c508850...   → Keccak256 hash used as the on-chain lookup
                                   key (derived from post title+source+link)
======================================================================
✅ This proves: the face scanned in Step 1 was matched to the post above,
   and that match was verified and timestamped immutably on Ethereum Sepolia.

======================================================================
  STEP 5 — LIVE TAMPER-EVIDENCE DEMONSTRATION
======================================================================
  Original title:  "Captain #Anshuman Singh's wife Smt Smriti shares the story of her ..."
  Tampered title:  "Captain #Anshuman Singh's wife Smt Smriti shares the story of her ...." (1 char changed)

  Original Keccak256 hash : 0x2750934180104aa2df2865adfaefee96b901da4855d2bb77e83dcdb1473339fd  → ✅ EXISTS on-chain
  Tampered Keccak256 hash : 0x19aa3dd7047edabc811008d3b6158502d9f93648c830d54a331d5f00cfdfa6d3  → ❌ NOT FOUND on-chain

  ✅ TAMPER-EVIDENCE CONFIRMED: Even a single-character change produces a
     completely different hash, and that altered hash has no matching
     on-chain record. This proves the blockchain record cannot be silently
     modified — any tampering is immediately detectable by hash mismatch.
======================================================================

[2026-09-07 13:08:44] [INFO] ✅ STEP 5 COMPLETED in 2.38s
[2026-09-07 13:08:44] [INFO] 🎉 PIPELINE EXECUTED SUCCESSFULLY IN 15.24 SECONDS!
```

---

## Project Structure

```text
face-verify-chain/
├── blockchain_module/
│   ├── contracts/
│   │   └── RecordVerification.sol     # Smart contract with faceHash binding
│   ├── blockchain_utils.py            # Hashes, uploads, verifies, and runs Step 5 tamper demo
│   ├── deploy_contract.py             # Compiles & deploys contract to Sepolia
│   └── RecordVerification_abi.json    # Compiled contract ABI
│
├── face_module/
│   └── face_id.py                     # Detects face and extracts 128-d face encoding + SHA-256 fingerprint
│
├── search_module/
│   └── reverse_search.py              # Google Cloud Vision WEB_DETECTION + TEXT_DETECTION & ranking
│
├── samples/                           # Sample test photos
├── pipeline.py                        # Main 5-stage interactive orchestrator
├── verify_only.py                     # Standalone verification tool for cross-session checking
├── check_setup.py                     # Diagnostic script checking 13/13 system requirements
├── requirements.txt                   # Project dependencies
├── .env.example                       # Environment template
└── README.md                          # Project documentation
```

---

## Known Limitations
- **API Dependency & Search Coverage:** Reverse image search relies on Google Cloud Vision's index. Candidate lists are capped at the top 5 results; individuals with sparse public web presence may return zero usable candidates.


---

## Future Improvements
- **Closed-Loop Remote Image Rescraping:** Enhancing `search_module` to download images from matched web pages and run them back through `face_module` for dual-sided biometric verification.
- **IPFS Metadata Storage:** Anchoring decentralized IPFS CIDs on-chain alongside metadata URIs to prevent web link rot.
- **Mainnet / L2 Deployment:** Transitioning smart contracts to an Ethereum L2 (Arbitrum/Optimism) for real economic security with sub-cent gas fees.

---

## License
MIT License
