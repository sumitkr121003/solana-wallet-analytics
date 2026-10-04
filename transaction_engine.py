import os
import json
import struct
import urllib.request
import urllib.error
import base58

LAMPORTS_PER_SOL = 1_000_000_000
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"


def make_rpc_request(method, params):
    api_key = os.environ.get("HELIUS_API_KEY")
    if not api_key:
        raise RuntimeError("HELIUS_API_KEY is missing.")

    url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    if "error" in data:
        raise RuntimeError(f"Helius error: {data['error']}")

    return data.get("result")


def get_wallet_balance(wallet_address):
    result = make_rpc_request("getBalance", [wallet_address])

    lamports = result["value"]

    return {
        "lamports": lamports,
        "sol": lamports / LAMPORTS_PER_SOL,
    }


def get_transaction_signatures(wallet_address, limit=10):
    return make_rpc_request(
        "getSignaturesForAddress",
        [wallet_address, {"limit": limit}],
    ) or []


def get_transaction_details(signature):
    return make_rpc_request(
        "getTransaction",
        [
            signature,
            {
                "encoding": "json",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    )


def get_wallet_net_change(details, wallet_address):
    transaction = details.get("transaction") or {}
    message = transaction.get("message") or {}
    meta = details.get("meta") or {}

    account_keys = message.get("accountKeys", [])
    pre_balances = meta.get("preBalances", [])
    post_balances = meta.get("postBalances", [])

    for index, account in enumerate(account_keys):
        if isinstance(account, dict):
            address = account.get("pubkey")
        else:
            address = account

        if address == wallet_address:
            if index >= len(pre_balances) or index >= len(post_balances):
                return None

            change = post_balances[index] - pre_balances[index]

            return {
                "lamports": change,
                "sol": change / LAMPORTS_PER_SOL,
                "fee": meta.get("fee", 0),
                "failed": meta.get("err") is not None,
            }

    return None


def decode_sol_transfers(message):
    account_keys = message.get("accountKeys", [])
    instructions = message.get("instructions", [])

    for instruction in instructions:
        program_index = instruction.get("programIdIndex")

        if program_index is None or program_index >= len(account_keys):
            continue

        program = account_keys[program_index]

        if isinstance(program, dict):
            program = program.get("pubkey")

        if program != SYSTEM_PROGRAM_ID:
            continue

        try:
            raw_data = base58.b58decode(instruction.get("data", ""))
        except (ValueError, TypeError):
            continue

        if len(raw_data) != 12:
            continue

        instruction_type = struct.unpack("<I", raw_data[:4])[0]

        if instruction_type != 2:
            continue

        accounts = instruction.get("accounts", [])

        if len(accounts) < 2:
            continue

        sender_index = accounts[0]
        recipient_index = accounts[1]

        if (
            sender_index >= len(account_keys)
            or recipient_index >= len(account_keys)
        ):
            continue

        sender = account_keys[sender_index]
        recipient = account_keys[recipient_index]

        if isinstance(sender, dict):
            sender = sender.get("pubkey")

        if isinstance(recipient, dict):
            recipient = recipient.get("pubkey")

        lamports = struct.unpack("<Q", raw_data[4:12])[0]

        yield {
            "sender": sender,
            "recipient": recipient,
            "sol": lamports / LAMPORTS_PER_SOL,
        }


def main():
    print("Solana Wallet Analytics")
    print("=======================")

    wallet_address = input(
        "Enter public Solana wallet address: "
    ).strip()

    try:
        balance = get_wallet_balance(wallet_address)

        print(f"\nCurrent SOL balance: {balance['sol']:.9f} SOL")
        print(f"Current balance: {balance['lamports']} lamports")

        transactions = get_transaction_signatures(wallet_address)

        print(f"\nTransactions found: {len(transactions)}")

        total_net_change = 0
        successful_changes = 0

        for number, item in enumerate(transactions, start=1):
            signature = item["signature"]

            print(f"\nTransaction {number}")
            print("Signature:", signature)

            try:
                details = get_transaction_details(signature)

                if details is None:
                    print("Transaction details unavailable.")
                    continue

                meta = details.get("meta") or {}
                fee = meta.get("fee", 0)
                failed = meta.get("err") is not None

                print("Slot:", details.get("slot"))
                print("Block time:", details.get("blockTime"))
                print(f"Fee: {fee / LAMPORTS_PER_SOL:.9f} SOL")
                print("Status:", "Failed" if failed else "Success")

                change = get_wallet_net_change(
                    details,
                    wallet_address,
                )

                if change is not None:
                    sol_change = change["sol"]

                    print(f"Wallet net SOL change: {sol_change:+.9f} SOL")

                    if not failed:
                        total_net_change += sol_change
                        successful_changes += 1
                else:
                    print("Wallet balance change unavailable.")

                message = (
                    (details.get("transaction") or {}).get("message")
                    or {}
                )

                transfers = list(decode_sol_transfers(message))

                if transfers:
                    print("Top-level SOL transfers:")
                    for transfer in transfers:
                        print("  From:", transfer["sender"])
                        print("  To:", transfer["recipient"])
                        print(f"  Amount: {transfer['sol']:.9f} SOL")

            except (
                RuntimeError,
                urllib.error.URLError,
                TimeoutError,
                ValueError,
                KeyError,
                TypeError,
            ) as error:
                print("Could not process transaction:", error)

        print("\nWallet Transaction Summary")
        print("==========================")
        print("Transactions fetched:", len(transactions))
        print("Successful balance changes counted:", successful_changes)
        print(
            "Net SOL change across counted transactions:",
            f"{total_net_change:+.9f} SOL",
        )

        print(
            "\nNote: The net change includes transaction fees. "
            "The summary covers only the fetched transactions, "
            "not the wallet's entire history."
        )

    except (
        RuntimeError,
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        print("Could not fetch wallet data:", error)


if __name__ == "__main__":
    main()