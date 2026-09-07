"""
deploy_contract.py
-------------------
Compiles RecordVerification.sol and deploys it to Ethereum Sepolia testnet
(or any EVM chain you point RPC_URL/CHAIN_ID at). Run this ONCE; save the
printed contract address into your .env as CONTRACT_ADDRESS for later use.

Requires:
  - PRIVATE_KEY   : private key of a testnet wallet funded with free Sepolia
                    test ETH (get some from a faucet that doesn't require an
                    existing mainnet balance, e.g.
                    https://faucet.quicknode.com/ethereum/sepolia)
  - RPC_URL       : e.g. https://ethereum-sepolia-rpc.publicnode.com
  - CHAIN_ID      : 11155111 (Sepolia)
"""

import os
import json
import solcx
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()


CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "contracts", "RecordVerification.sol")
SOLC_VERSION = "0.8.20"


def compile_contract():
    solcx.install_solc(SOLC_VERSION)
    with open(CONTRACT_PATH, "r") as f:
        source = f.read()

    compiled = solcx.compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
    )
    contract_id, contract_interface = list(compiled.items())[0]
    return contract_interface["abi"], contract_interface["bin"]


def deploy():
    rpc_url = os.environ["RPC_URL"]
    private_key = os.environ["PRIVATE_KEY"]
    chain_id = int(os.environ.get("CHAIN_ID", 11155111))  # Sepolia

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    assert w3.is_connected(), f"Could not connect to RPC at {rpc_url}"

    actual_chain_id = w3.eth.chain_id
    if actual_chain_id != chain_id:
        print(f"WARNING: RPC reports chain ID {actual_chain_id}, expected {chain_id} (Sepolia).")

    account = w3.eth.account.from_key(private_key)
    print(f"Deploying from account: {account.address}")
    print(f"Balance: {w3.from_wei(w3.eth.get_balance(account.address), 'ether')} Sepolia ETH")

    abi, bytecode = compile_contract()
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    nonce = w3.eth.get_transaction_count(account.address)
    tx = Contract.constructor().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 2_000_000,
        "gasPrice": int(w3.eth.gas_price * 1.25),
        "chainId": chain_id,
    })

    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"Deployment tx sent: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = receipt.contractAddress
    print(f"Contract deployed at: {contract_address}")

    # Save ABI locally so blockchain_utils.py can load it
    abi_path = os.path.join(os.path.dirname(__file__), "RecordVerification_abi.json")
    with open(abi_path, "w") as f:
        json.dump(abi, f)
    print(f"ABI saved to {abi_path}")

    print("\nAdd this to your .env file:")
    print(f"CONTRACT_ADDRESS={contract_address}")

    return contract_address, abi


if __name__ == "__main__":
    deploy()
