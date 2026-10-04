import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

LAMPORTS_PER_SOL = 1_000_000_000

app = FastAPI(
    title="Solana Wallet Analytics API",
    description="Solana wallet analytics and rule-based risk indicators",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def helius_request(method, params):
    api_key = os.environ.get("HELIUS_API_KEY")

    if not api_key:
        raise RuntimeError(
            "HELIUS_API_KEY environment variable is missing."
        )

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
        raise RuntimeError(str(data["error"]))

    return data.get("result")


def get_recent_transactions(address, limit):
    return helius_request(
        "getSignaturesForAddress",
        [address, {"limit": limit}],
    ) or []



def get_transaction_details(signature):
    return helius_request(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    )


@app.get("/api/debug/transaction/{signature}")
def debug_transaction(signature: str):
    try:
        transaction = get_transaction_details(signature)

        if not transaction:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found.",
            )

        message = (
            transaction.get("transaction", {})
            .get("message", {})
        )

        return {
            "transaction_found": True,
            "transaction_version": transaction.get("version"),
            "account_keys": message.get("accountKeys", []),
            "instructions": message.get("instructions", []),
            "meta_err": transaction.get("meta", {}).get("err"),
            "inner_instructions": transaction.get("meta", {}).get(
                "innerInstructions", []
            ),
        }

    except HTTPException:
        raise
    except (RuntimeError, TypeError, OSError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not inspect transaction: {error}",
        )


def get_account_keys(transaction):
    message = (
        transaction.get("transaction", {})
        .get("message", {})
    )

    keys = message.get("accountKeys", [])

    # JSON encoding usually returns strings; handle parsed objects too.
    return [
        key if isinstance(key, str) else key.get("pubkey", "")
        for key in keys
    ]



def extract_native_sol_transfers(transaction):
    """Extract parsed top-level native SOL transfers."""
    message = (
        transaction.get("transaction", {})
        .get("message", {})
    )

    transfers = []

    for instruction in message.get("instructions", []):
        if instruction.get("programId") != (
            "11111111111111111111111111111111"
        ):
            continue

        parsed = instruction.get("parsed")
        if not isinstance(parsed, dict):
            continue

        if parsed.get("type") != "transfer":
            continue

        info = parsed.get("info", {})
        source = info.get("source")
        destination = info.get("destination")
        lamports = info.get("lamports")

        if not source or not destination:
            continue

        if not isinstance(lamports, int) or lamports <= 0:
            continue

        transfers.append({
            "source": source,
            "destination": destination,
            "sol": lamports / LAMPORTS_PER_SOL,
        })

    return transfers


@app.get("/api/wallet/{address}/counterparties")
def wallet_counterparties(address: str, limit: int = 20):
    if limit < 1 or limit > 50:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 50.",
        )

    try:
        signatures = get_recent_transactions(address, limit)
        counterparties = {}
        analyzed = 0
        skipped = 0

        for item in signatures:
            signature = item.get("signature")

            if not signature or item.get("err") is not None:
                skipped += 1
                continue

            transaction = get_transaction_details(signature)

            if not transaction:
                skipped += 1
                continue

            analyzed += 1

            for transfer in extract_native_sol_transfers(transaction):
                source = transfer["source"]
                destination = transfer["destination"]

                if source == address:
                    other_wallet = destination
                    direction = "outgoing"
                elif destination == address:
                    other_wallet = source
                    direction = "incoming"
                else:
                    continue

                if other_wallet == address:
                    continue

                entry = counterparties.setdefault(
                    other_wallet,
                    {
                        "wallet": other_wallet,
                        "incoming_transfers": 0,
                        "outgoing_transfers": 0,
                        "incoming_sol": 0.0,
                        "outgoing_sol": 0.0,
                    },
                )

                if direction == "incoming":
                    entry["incoming_transfers"] += 1
                    entry["incoming_sol"] += transfer["sol"]
                else:
                    entry["outgoing_transfers"] += 1
                    entry["outgoing_sol"] += transfer["sol"]

        results = sorted(
            counterparties.values(),
            key=lambda entry: (
                entry["incoming_transfers"]
                + entry["outgoing_transfers"]
            ),
            reverse=True,
        )

        for entry in results:
            entry["incoming_sol"] = round(entry["incoming_sol"], 9)
            entry["outgoing_sol"] = round(entry["outgoing_sol"], 9)
            entry["total_transfers"] = (
                entry["incoming_transfers"]
                + entry["outgoing_transfers"]
            )

        return {
            "wallet": address,
            "transactions_requested": limit,
            "transactions_analyzed": analyzed,
            "transactions_skipped": skipped,
            "counterparties_found": len(results),
            "counterparties": results,
            "limitations": [
                "Only parsed top-level native SOL transfers are counted.",
                "SPL token transfers and inner instructions are not included.",
                "Some destination or source accounts may be token accounts, "
                "program-related accounts, or temporary accounts rather than "
                "independent user wallets.",
                "Swap transactions can contain multiple account movements; "
                "these results do not establish the economic counterparty.",
                "Very small transfers may be rent, account setup, or other "
                "technical movements and should not be treated as suspicious "
                "without additional evidence.",
                "Repeated interaction alone is not proof of suspicious behavior.",
            ],
        }

    except (RuntimeError, TypeError, OSError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not analyze wallet counterparties: {error}",
        )


@app.get("/")
def home():
    return {
        "message": "Solana Wallet Analytics API is running",
        "docs": "/docs",
        "risk_endpoint": "/api/wallet/{address}/risk",
    }


@app.get("/api/wallet/{address}/balance")
def wallet_balance(address: str):
    try:
        result = helius_request("getBalance", [address])
        lamports = result["value"]

        return {
            "wallet": address,
            "lamports": lamports,
            "sol": lamports / LAMPORTS_PER_SOL,
        }

    except (RuntimeError, KeyError, TypeError, OSError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not retrieve wallet balance: {error}",
        )


@app.get("/api/wallet/{address}/transactions")
def wallet_transactions(address: str, limit: int = 10):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 100.",
        )

    try:
        transactions = get_recent_transactions(address, limit)

        return {
            "wallet": address,
            "count": len(transactions),
            "transactions": [
                {
                    "signature": item.get("signature"),
                    "slot": item.get("slot"),
                    "block_time": item.get("blockTime"),
                    "status": (
                        "Success"
                        if item.get("err") is None
                        else "Failed"
                    ),
                    "confirmation_status": item.get(
                        "confirmationStatus"
                    ),
                }
                for item in transactions
            ],
        }

    except (RuntimeError, TypeError, OSError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not retrieve transactions: {error}",
        )


@app.get("/api/wallet/{address}/risk")
def wallet_risk(address: str, limit: int = 100):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 100.",
        )

    try:
        transactions = get_recent_transactions(address, limit)

    except (RuntimeError, TypeError, OSError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not analyze wallet transactions: {error}",
        )

    total = len(transactions)

    failed_transactions = [
        tx for tx in transactions if tx.get("err") is not None
    ]
    failed_count = len(failed_transactions)

    failure_rate = (
        round((failed_count / total) * 100, 2)
        if total
        else 0.0
    )

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    timestamps = [
        tx.get("blockTime")
        for tx in transactions
        if isinstance(tx.get("blockTime"), (int, float))
    ]

    recent_24h_count = sum(
        1 for timestamp in timestamps
        if timestamp >= cutoff.timestamp()
    )

    indicators = []
    score = 0

    # Rule 1: unusually high failed-transaction proportion.
    if failure_rate >= 40:
        score += 35
        indicators.append({
            "code": "HIGH_FAILURE_RATE",
            "severity": "high",
            "title": "High failed-transaction rate",
            "details": (
                f"{failed_count} of {total} sampled transactions failed "
                f"({failure_rate}%)."
            ),
        })
    elif failure_rate >= 20:
        score += 20
        indicators.append({
            "code": "ELEVATED_FAILURE_RATE",
            "severity": "medium",
            "title": "Elevated failed-transaction rate",
            "details": (
                f"{failed_count} of {total} sampled transactions failed "
                f"({failure_rate}%)."
            ),
        })

    # Rule 2: repeated failures.
    if failed_count >= 10:
        score += 15
        indicators.append({
            "code": "REPEATED_FAILURES",
            "severity": "medium",
            "title": "Repeated failed transactions",
            "details": (
                f"{failed_count} failed transactions were found "
                "in the sampled history."
            ),
        })
    elif failed_count >= 5:
        score += 10
        indicators.append({
            "code": "MULTIPLE_FAILURES",
            "severity": "low",
            "title": "Multiple failed transactions",
            "details": (
                f"{failed_count} failed transactions were found "
                "in the sampled history."
            ),
        })

    # Rule 3: high transaction activity in the available 24-hour sample.
    if recent_24h_count >= 50:
        score += 25
        indicators.append({
            "code": "VERY_HIGH_ACTIVITY",
            "severity": "medium",
            "title": "Very high recent activity",
            "details": (
                f"{recent_24h_count} sampled transactions have timestamps "
                "within the last 24 hours."
            ),
        })
    elif recent_24h_count >= 20:
        score += 15
        indicators.append({
            "code": "HIGH_ACTIVITY",
            "severity": "low",
            "title": "High recent activity",
            "details": (
                f"{recent_24h_count} sampled transactions have timestamps "
                "within the last 24 hours."
            ),
        })

    score = min(score, 100)

    if score >= 50:
        assessment = "Elevated indicators"
    elif score >= 25:
        assessment = "Some indicators"
    else:
        assessment = "Few indicators observed"

    if total < 10:
        data_quality = "Limited sample: fewer than 10 transactions"
    elif len(timestamps) < total:
        data_quality = (
            "Partial timestamp coverage; recent activity may be understated"
        )
    else:
        data_quality = "Based on the available recent transaction sample"

    return {
        "wallet": address,
        "assessment": assessment,
        "risk_score": score,
        "score_meaning": (
            "Heuristic indicator score from 0 to 100, not a probability "
            "of fraud or proof of malicious activity."
        ),
        "sample": {
            "transactions_requested": limit,
            "transactions_analyzed": total,
            "failed_transactions": failed_count,
            "successful_transactions": total - failed_count,
            "failure_rate_percent": failure_rate,
            "transactions_with_timestamps": len(timestamps),
            "transactions_in_last_24_hours": recent_24h_count,
            "data_quality": data_quality,
        },
        "indicators": indicators,
        "limitations": [
            "Only recent transaction signatures and metadata are analyzed.",
            "High activity and failed transactions can have legitimate causes.",
            "This endpoint does not inspect token transfers, counterparties, "
            "or complete transaction instructions.",
            "No indicators does not guarantee that a wallet is safe.",
        ],
        "analyzed_at": now.isoformat(),
    }