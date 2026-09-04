# Face → Search → Blockchain Verification Pipeline

A consent-based demo pipeline built for HH Goa 2026 Task 3: it detects a face
in a photo, uses that SAME photo to run a real reverse-image / web search and
find a matching public post, then writes a tamper-evident fingerprint of that
post to a blockchain and re-verifies it on-chain.

## ⚠️ Scope & consent

This project only ever searches for photos the operator owns or has explicit
permission to use (in this demo: my own photo / a teammate's photo, used with
their permission). It is **not** built or intended to identify or track
strangers, and does not include any stored database of faces to match
against. The face-encoding step exists to demonstrate genuine face detection;
the actual "search the web" step works by reverse-image-searching the photo
itself, not by matching a face against a third-party identity database.

## Pipeline

```
Local photo
    │
    ├──────────────────────────────┬──────────────────────────────┐
    ▼                               ▼
face_module/face_id.py    search_module/reverse_search.py
detects + encodes the      reverse-image-searches the SAME local
face (face_recognition/    photo directly via Google Cloud Vision's
dlib)                      WEB_DETECTION feature — no separate public
                            URL needed, the image bytes are sent
                            directly — returns real matching pages
                                            │
                                            ▼
                          blockchain_module/blockchain_utils.py
                          hashes the top matched page (link + title +
                          source), writes the hash on-chain to a
                          Solidity contract on Ethereum Sepolia testnet,
                          then reads it back to prove the record exists
                          and is unaltered
```

One local image drives both the face-scan step and the search step —
orchestrated end-to-end by `pipeline.py`.

## Web / social search: Google Cloud Vision API

**Why this instead of a URL-based reverse-image tool:** most reverse-image
search APIs (Google Lens via third-party wrappers, TinEye, Bing Visual
Search) require a **public URL** they can fetch, meaning you'd have to
upload your photo somewhere public first and copy its link. Google Cloud
Vision's `WEB_DETECTION` feature accepts the **raw image bytes directly**
(base64-encoded in the request body), so this pipeline can search using
just a local file path — matching the task's intended flow of "face scan
in → matching post out."

- Endpoint: `https://vision.googleapis.com/v1/images:annotate`
- Returns `pagesWithMatchingImages`: real URLs of web pages where that
  photo (or a near-duplicate/edited version) appears.
- **Free tier:** 1,000 requests/month at no charge, plus $300 in free
  trial credit for new Google Cloud accounts (valid 90 days).
- **Important:** Google requires a billing account (credit card on file)
  to enable the Vision API, even to use the free tier — this is an
  anti-abuse measure, not a hidden charge. You will not be billed as long
  as you stay under 1,000 requests/month.

## Blockchain used

**Ethereum Sepolia testnet** (chain ID `11155111`).
- Free public RPC endpoint (`https://ethereum-sepolia-rpc.publicnode.com`), no
  signup needed. (Alternatives if it's rate-limited: `https://rpc.sepolia.org`,
  `https://ethereum-sepolia.publicnode.com`.)
- Free Sepolia test ETH from a faucet — use one that does **not** require an
  existing mainnet ETH balance:
  - [QuickNode Sepolia faucet](https://faucet.quicknode.com/ethereum/sepolia) — no account, no mainnet balance required.
  - [Google Cloud Web3 faucet](https://cloud.google.com/application/web3/faucet/ethereum/sepolia) — free Google account login, no mainnet balance required.
- Block explorer: [sepolia.etherscan.io](https://sepolia.etherscan.io) — paste
  in the printed tx hash or contract address to inspect the on-chain record
  visually during your recording.
- Contract: `blockchain_module/contracts/RecordVerification.sol` — a minimal
  Solidity contract that stores `keccak256(post data) → {submitter, timestamp,
  metadataURI}` in a mapping, emits an event on write, and exposes a `view`
  function to re-verify a hash against the stored record.

## Setup

### 1. Clone and install dependencies

```bash
git clone <this-repo>
cd face-verify-chain
pip install -r requirements.txt
```

Note: `face_recognition` depends on `dlib`, which needs `cmake` and a C++
compiler to build from source. On Windows, install `dlib-bin` instead
(prebuilt wheels, no compiler needed): `pip install dlib-bin face_recognition`.

### 2. Set up Google Cloud Vision API (from scratch)

1. Go to **https://console.cloud.google.com/** and sign in with a Google
   account.
2. Click the project dropdown (top left) → **New Project** → give it any
   name (e.g. `face-verify-chain`) → **Create**. Make sure this new project
   is selected before continuing.
3. **Enable billing** (required by Google even for free-tier usage):
   - Go to **Billing** in the left sidebar → **Link a billing account**.
   - If you don't have one, create one — you'll enter a credit card. New
     accounts get **$300 in free credit for 90 days**, and Vision API's
     first 1,000 requests/month are always free regardless.
   - You will not be charged unless you exceed the free tier and your free
     trial credit is exhausted.
4. **Enable the Vision API**:
   - Go to **APIs & Services → Library**.
   - Search for **"Cloud Vision API"** → click it → **Enable**.
5. **Create an API key**:
   - Go to **APIs & Services → Credentials**.
   - Click **Create Credentials → API key**.
   - Copy the generated key.
   - (Recommended) Click **Restrict key**, and under "API restrictions"
     select **Cloud Vision API only**, so the key can't be misused for
     other Google Cloud services if leaked.
6. Paste this key into your `.env` file as `GOOGLE_VISION_API_KEY` (see
   step 4 below).

### 3. Get a testnet wallet + funds

- Create a fresh wallet (e.g. in MetaMask) — **use a testnet-only wallet,
  never a wallet holding real funds.**
- Switch MetaMask's network to Sepolia (chain ID `11155111`).
- Fund it with free Sepolia test ETH from a faucet that doesn't require an
  existing mainnet balance, e.g.
  https://faucet.quicknode.com/ethereum/sepolia or
  https://cloud.google.com/application/web3/faucet/ethereum/sepolia
- Export its private key.

### 4. Configure environment

```bash
cp .env.example .env
# fill in GOOGLE_VISION_API_KEY and PRIVATE_KEY
```

### 5. Deploy the contract (one-time)

```bash
python blockchain_module/deploy_contract.py
```
Copy the printed `CONTRACT_ADDRESS` into your `.env`.

### 6. Run the full pipeline

```bash
python pipeline.py --face samples/my_photo.jpg
```

A single local image file drives the entire pipeline: it's used for face
detection in Step 1, and sent directly to Google Cloud Vision for the web
search in Step 2 — no separate public URL required.

The script prints each pipeline stage as it runs: face detected → top web
match found → transaction hash of the on-chain upload → re-verification
result read back from the contract.

### Optional: health check before recording

A standalone diagnostic script (`check_setup.py`, kept alongside
`pipeline.py`) checks all four components — `.env`, face detection, Vision
API connectivity, and the deployed contract — without running the full
pipeline. Run it before your demo recording:
```bash
python check_setup.py
```

## Individual modules (can also be run standalone)

```bash
python face_module/face_id.py samples/my_photo.jpg
python search_module/reverse_search.py samples/my_photo.jpg
```

## Known limitations

- **Reverse image search quality depends on how widely indexed the photo
  is.** A brand-new photo that has never been posted anywhere else on the
  public web will correctly return zero matches — that's expected
  behavior, not a bug. Test candidate photos manually at
  images.google.com first if you want a guaranteed non-empty result for a
  demo recording.
- **Google Cloud Vision requires a billing account (card on file)** even
  for free-tier usage, unlike some competing APIs that offer card-free
  trials. You will not be charged as long as usage stays under 1,000
  requests/month.
- The face-encoding step and the search step are **not cryptographically
  linked** in this demo — the encoding proves a face was detected locally;
  the search is a separate web-detection call on the same image file. A
  production version would need a licensed face-search API to combine
  these safely and legally.
- `storeRecord` reverts if the exact same content hash is submitted twice,
  so re-running the pipeline on a photo that returns the identical top
  match will fail on the upload step unless the contract state is reset or
  a different photo/match is used.
- This is a testnet demo; no mainnet funds, real user data beyond the
  operator's own consenting photo, or production security hardening
  (e.g. key management) are involved.
- Some Sepolia faucets (e.g. Alchemy's, Infura's) require you to already
  hold a small mainnet ETH balance — this project deliberately documents
  faucets that don't (QuickNode, Google Cloud) to avoid that blocker.

## Repo structure

```
face-verify-chain/
├── pipeline.py                          # end-to-end orchestrator
├── check_setup.py                       # standalone health-check for all components
├── face_module/
│   └── face_id.py                       # Step 1: face detect + encode
├── search_module/
│   └── reverse_search.py                # Step 2: reverse image search (Google Cloud Vision)
├── blockchain_module/
│   ├── contracts/RecordVerification.sol # on-chain record contract
│   ├── deploy_contract.py               # compile + deploy to Sepolia
│   └── blockchain_utils.py              # Step 3: upload + verify
├── samples/                             # sample consenting test photo(s)
├── requirements.txt
├── .env.example
└── README.md
```
