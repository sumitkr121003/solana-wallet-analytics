import { useState } from "react";
import "./App.css";

const DEFAULT_WALLET = "";
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function formatDate(timestamp) {
  if (timestamp == null || !Number.isFinite(Number(timestamp))) {
    return "Unavailable";
  }

  const date = new Date(Number(timestamp) * 1000);

  if (Number.isNaN(date.getTime())) {
    return "Unavailable";
  }

  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  });
}

function shortSignature(signature = "") {
  if (signature.length < 24) return signature;
  return `${signature.slice(0, 12)}...${signature.slice(-8)}`;
}

function App() {
  const [wallet, setWallet] = useState(DEFAULT_WALLET);
  const [data, setData] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [risk, setRisk] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function analyzeWallet(event) {
    event.preventDefault();
    const address = wallet.trim();

    if (!address) {
      setError("Please enter a Solana wallet address.");
      return;
    }

    setLoading(true);
    setError("");
    setCopied(false);
    setData(null);
    setTransactions([]);
    setRisk(null);

    try {
      const [balanceResponse, transactionResponse, riskResponse] =
        await Promise.all([
          fetch(`${API_URL}/api/wallet/${encodeURIComponent(address)}/balance`),
          fetch(
            `${API_URL}/api/wallet/${encodeURIComponent(address)}/transactions?limit=10`
          ),
          fetch(
            `${API_URL}/api/wallet/${encodeURIComponent(address)}/risk?limit=100`
          ),
        ]);

      if (!balanceResponse.ok) {
        throw new Error("Could not retrieve the wallet balance.");
      }
      if (!transactionResponse.ok) {
        throw new Error("Could not retrieve wallet transactions.");
      }
      if (!riskResponse.ok) {
        throw new Error(
          "Could not retrieve risk analysis. Check the backend risk endpoint."
        );
      }

      const [balanceData, transactionData, riskData] = await Promise.all([
        balanceResponse.json(),
        transactionResponse.json(),
        riskResponse.json(),
      ]);

      setData(balanceData);
      setTransactions(transactionData.transactions || []);
      setRisk(riskData);
    } catch (err) {
      setError(
        err.message ||
          "Unable to connect to the API. Make sure FastAPI is running."
      );
    } finally {
      setLoading(false);
    }
  }

  async function copyWallet() {
    try {
      await navigator.clipboard.writeText(wallet.trim());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Could not copy the wallet address.");
    }
  }

  const riskScore = Number(risk?.risk_score ?? 0);
  const riskTone =
    riskScore >= 50 ? "risk-high" : riskScore >= 25 ? "risk-medium" : "risk-low";
  const successfulTransactions = transactions.filter(
    (tx) => tx.status === "Success"
  ).length;

  const indicatorTitles = {
    VERY_HIGH_ACTIVITY: "High recent activity",
    HIGH_ACTIVITY: "Frequent wallet activity",
    HIGH_FAILURE_RATE: "Many transactions failed",
    VERY_HIGH_FAILURE_RATE: "Unusually high failure rate",
    REPEATED_FAILURES: "Repeated transaction failures",
  };

  const indicatorExplanations = {
    VERY_HIGH_ACTIVITY:
      "Many transactions were recorded within the last 24 hours. This can be normal for active traders, automated services, or business wallets.",
    HIGH_ACTIVITY:
      "This wallet has been active recently. Frequent activity alone does not mean the wallet is unsafe.",
    HIGH_FAILURE_RATE:
      "A large share of the analyzed transactions failed. Review the transaction details to understand possible causes.",
    VERY_HIGH_FAILURE_RATE:
      "A very large share of the analyzed transactions failed. Review the transaction details to understand why.",
    REPEATED_FAILURES:
      "Several transactions failed repeatedly. Check the transaction details for a possible recurring issue.",
  };

  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <a className="brand sidebar-brand" href="#overview" aria-label="SolanaScope home">
          <span className="brand-icon"><span /></span>
          <span className="brand-name">Solana<span>Scope</span></span>
        </a>

        <div className="sidebar-label">WORKSPACE</div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          <a className="nav-item active" href="#overview">
            <span className="nav-icon">◈</span> Dashboard
          </a>
          <a className="nav-item" href="#transactions">
            <span className="nav-icon">⇄</span> Transactions
          </a>
          <a className="nav-item" href="#risk">
            <span className="nav-icon">⬡</span> Risk analysis
          </a>
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-mark"><span className="brand-icon"><span /></span></div>
          <p>On-chain clarity.<br />Built for Solana.</p>
          <div className="backend-status">
            <span className="status-dot" /> FastAPI connected when available
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="mobile-brand">
            <span className="brand-icon"><span /></span>
            <span className="brand-name">Solana<span>Scope</span></span>
          </div>
          <div className="topbar-context">
            <span className="live-dot" /> SOLANA WALLET INTELLIGENCE
          </div>
          <div className="network-badge">
            <span className="status-dot" /> Solana Mainnet
          </div>
        </header>

        <section className="hero-panel" id="overview">
          <div className="hero-copy">
            <p className="eyebrow">ON-CHAIN INTELLIGENCE</p>
            <h1>Wallet <span>Overview</span></h1>
            <p className="hero-description">
              Understand wallet activity with balance insights, transaction history,
              and transparent, rule-based risk indicators.
            </p>

            <form className="search-form" onSubmit={analyzeWallet}>
              <span className="search-icon" aria-hidden="true">⌕</span>
              <input
                aria-label="Solana wallet address"
                value={wallet}
                onChange={(event) => setWallet(event.target.value)}
                placeholder="Paste a Solana wallet address"
                spellCheck="false"
              />
              <button type="submit" disabled={loading}>
                {loading ? <><span className="button-spinner" /> Analyzing</> : <>⌕ <span>Analyze wallet</span></>}
              </button>
            </form>
            <p className="helper-text">
              <span>ⓘ</span> Public wallet addresses only. Never enter a seed phrase or private key.
            </p>
          </div>

          <div className="hero-art" aria-hidden="true">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="orbit orbit-three" />
            <div className="solana-emblem">
              <span className="solana-bar bar-one" />
              <span className="solana-bar bar-two" />
              <span className="solana-bar bar-three" />
            </div>
            <div className="hero-art-caption"><span className="live-dot" /> NETWORK READY</div>
          </div>
        </section>

        {error && <div className="error-message" role="alert"><span>!</span>{error}</div>}

        <div className="section-heading overview-heading">
          <div>
            <p className="eyebrow">YOUR SNAPSHOT</p>
            <h2>Wallet analytics</h2>
          </div>
          {data && (
            <button className="secondary-button" type="button" onClick={copyWallet}>
              {copied ? "✓ Copied" : "▣ Copy address"}
            </button>
          )}
        </div>

        <section className="stats-grid" aria-label="Wallet metrics">
          <article className="stat-card balance-card">
            <div className="stat-card-top">
              <span className="metric-icon mint-icon">◈</span>
              <span className="metric-label">Wallet balance</span>
              <span className="metric-tag">SOL</span>
            </div>
            <div className="stat-value">
              {data ? Number(data.sol).toFixed(4) : "—"}
              <span className="stat-unit">SOL</span>
            </div>
            <p className="stat-note">{data ? "Native SOL held by this address" : "Analyze a wallet to load its balance"}</p>
            <div className="card-decoration decoration-mint" aria-hidden="true">⌁</div>
          </article>

          <article className="stat-card transactions-stat">
            <div className="stat-card-top">
              <span className="metric-icon blue-icon">⇄</span>
              <span className="metric-label">Transactions loaded</span>
              <span className="metric-tag">LATEST</span>
            </div>
            <div className="stat-value">{data ? transactions.length : "—"}</div>
            <p className="stat-note">Recent records returned by the API</p>
            <div className="card-decoration decoration-blue" aria-hidden="true">▥</div>
          </article>

          <article className="stat-card risk-stat">
            <div className="stat-card-top">
              <span className="metric-icon violet-icon">⬡</span>
              <span className="metric-label">Heuristic risk score</span>
              {risk && <span className={`risk-badge ${riskTone}`}>{risk.assessment}</span>}
            </div>
            <div className={`stat-value ${risk ? riskTone : ""}`}>
              {risk ? riskScore : "—"}{risk && <span className="stat-unit">/100</span>}
            </div>
            <p className="stat-note">{risk ? "Rule-based screening indicator" : "Run an analysis to calculate the score"}</p>
            <div className="card-decoration decoration-violet" aria-hidden="true">⌁</div>
          </article>
        </section>

        <div className="content-grid">
          <section className="panel transactions-panel" id="transactions">
            <div className="panel-heading">
              <div className="panel-title-group">
                <span className="panel-icon">⇄</span>
                <div>
                  <h2>Recent transactions</h2>
                  <p>Latest on-chain activity for this wallet</p>
                </div>
              </div>
              <span className="table-count">{transactions.length} records</span>
            </div>

            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>TRANSACTION</th>
                    <th>SLOT</th>
                    <th>DATE &amp; TIME</th>
                    <th>STATUS</th>
                    <th>CONFIRMATION</th>
                  </tr>
                </thead>
                <tbody>
                  {!data && (
                    <tr><td colSpan="5" className="empty-state">
                      {loading ? <><span className="button-spinner" /> Loading wallet data…</> : "Your recent transactions will appear here after analysis."}
                    </td></tr>
                  )}
                  {data && transactions.length === 0 && (
                    <tr><td colSpan="5" className="empty-state">No transactions found for this address.</td></tr>
                  )}
                  {transactions.map((tx) => (
                    <tr key={tx.signature}>

<td>
  <div className="transaction-signature-cell">
    <a
      className="signature-link"
      href={`https://explorer.solana.com/tx/${tx.signature}?cluster=mainnet-beta`}
      target="_blank"
      rel="noreferrer"
      title="View full transaction on Solana Explorer"
    >
      <span className="tx-link-icon">↗</span>
      {shortSignature(tx.signature)}
    </a>

    <button
      type="button"
      className="copy-signature-button"
      title="Copy full transaction signature"
      aria-label="Copy full transaction signature"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(tx.signature);
        } catch {
          window.prompt("Copy transaction signature:", tx.signature);
        }
      }}
    >
      Copy
    </button>
  </div>
</td>
                      <td>{tx.slot?.toLocaleString() ?? "—"}</td>
                      <td>{formatDate(tx.block_time)}</td>
                      <td><span className={`status-pill ${tx.status === "Success" ? "success" : "failed"}`}>
                        <span />{tx.status}
                      </span></td>
                      <td>{tx.confirmation_status ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel-footer">
              <span>Showing up to 10 recent records</span>
              <span>Data supplied by your API</span>
            </div>
          </section>

          <section className="panel risk-panel" id="risk">
            <div className="panel-heading">
              <div className="panel-title-group">
                <span className="panel-icon risk-panel-icon">⬡</span>
                <div>
                  <h2>Risk analysis</h2>
                  <p>Signals from recent wallet activity</p>
                </div>
              </div>
              {risk && <span className={`risk-badge ${riskTone}`}>{risk.assessment}</span>}
            </div>

            {!risk && (
              <div className="risk-empty">
                <div className="risk-empty-symbol">⬡</div>
                <h3>{loading ? "Analyzing activity" : "Awaiting wallet data"}</h3>
                <p>{loading ? "Reviewing recent transactions and configured indicators…" : "Analyze a wallet to see its score, sample metrics, and detected indicators."}</p>
              </div>
            )}

            {risk && (
              <>
                <div className="risk-score-layout">
                  <div className={`score-ring ${riskTone}`} style={{ "--score": `${Math.max(0, Math.min(100, riskScore))}%` }}>
                    <div className="score-ring-inner">
                      <strong>{riskScore}</strong>
                      <span>OUT OF 100</span>
                    </div>
                  </div>
                  <div className="score-summary">
                    <span className={`score-label ${riskTone}`}>{risk.assessment || "Risk assessment"}</span>
                    <p>{risk.score_meaning || "A rule-based indicator score, not a probability of fraud."}</p>
                  </div>
                </div>

                <div className="risk-metrics">
                  <article className="risk-metric">
                    <span>Analyzed</span>
                    <strong>{risk.sample?.transactions_analyzed ?? "—"}</strong>
                    <small>transactions</small>
                  </article>
                  <article className="risk-metric">
                    <span>Failed</span>
                    <strong>{risk.sample?.failed_transactions ?? "—"}</strong>
                    <small>transactions</small>
                  </article>
                  <article className="risk-metric">
                    <span>Failure rate</span>
                    <strong>{risk.sample?.failure_rate_percent ?? "—"}%</strong>
                    <small>of sample</small>
                  </article>
                  <article className="risk-metric">
                    <span>Last 24 hours</span>
                    <strong>{risk.sample?.transactions_in_last_24_hours ?? "—"}</strong>
                    <small>transactions</small>
                  </article>
                </div>

                <div className="risk-indicators">
                  <div className="subsection-heading">
                    <h3>Detected indicators</h3>
                    <span>{risk.indicators?.length ?? 0} signals</span>
                  </div>
                  {risk.indicators?.length > 0 ? (
                    <ul>
                      {risk.indicators.map((indicator, index) => {
                        const details = typeof indicator === "string"
                          ? { title: indicator, severity: "info", details: "" }
                          : indicator;
                        const title = indicatorTitles[details.code] || details.title || "Activity worth reviewing";
                        const explanation = indicatorExplanations[details.code] || details.details ||
                          "The analysis detected a pattern worth reviewing. This signal alone does not establish that the wallet is unsafe.";
                        const severity = String(details.severity || "info").toLowerCase();
                        const severityLabel = severity === "high" || severity === "critical"
                          ? "High attention"
                          : severity === "medium" ? "Medium attention" : "Informational";

                        return (
                          <li className="indicator-card" key={`${index}-${details.code || title}`}>
                            <div className="indicator-card-header">
                              <span className={`indicator-symbol severity-symbol-${severity}`}>!</span>
                              <div className="indicator-copy">
                                <strong>{title}</strong>
                                <p>{explanation}</p>
                              </div>
                              <span className={`indicator-severity severity-${severity}`}>{severityLabel}</span>
                            </div>
                            {details.code === "VERY_HIGH_ACTIVITY" && (
                              <p className="indicator-evidence">
                                Observed: {risk.sample?.transactions_in_last_24_hours ?? "Unknown"} transactions in the last 24 hours.
                              </p>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <div className="risk-no-indicators">
                      <span>✓</span>
                      <div><strong>No configured indicators triggered</strong><p>No configured risk indicators were triggered in the analyzed sample.</p></div>
                    </div>
                  )}
                </div>

                {risk.limitations?.length > 0 && (
                  <details className="risk-limitations">
                    <summary>Analysis limitations</summary>
                    <ul>{risk.limitations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
                  </details>
                )}
                <p className="risk-disclaimer">
                  This is rule-based screening, not a fraud verdict. A low score does not guarantee safety, and legitimate activity can trigger indicators.
                </p>
              </>
            )}
          </section>
        </div>

        <footer className="footer">
          <span>© {new Date().getFullYear()} SolanaScope</span>
          <span><span className="status-dot" /> Built for transparent on-chain research</span>
          <span>FastAPI · Solana</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
