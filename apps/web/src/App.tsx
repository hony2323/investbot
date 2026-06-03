import { useEffect, useState } from "react";
import { getPortfolio, type PortfolioResponse, type Violation } from "./api";

type Theme = "light" | "dark";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () => (document.documentElement.dataset.theme as Theme) || "light"
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("ledger-theme", theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

const money = (x: number, ccy: string) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: ccy || "USD",
    maximumFractionDigits: 0,
  }).format(x);

const signedMoney = (x: number, ccy: string) =>
  (x >= 0 ? "+" : "−") + money(Math.abs(x), ccy).replace("-", "");

const longDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

export default function App() {
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [theme, toggleTheme] = useTheme();

  useEffect(() => {
    getPortfolio("mock")
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <Masthead asOf={data?.summary.as_of} theme={theme} onToggle={toggleTheme} />

      {error && (
        <p className="state err">
          The wire is down — {error}
        </p>
      )}
      {!data && !error && (
        <p className="state">
          Setting the type<span className="blink">…</span>
        </p>
      )}

      {data && <Ledger data={data} />}

      <Colophon account={data?.summary.account_id ?? null} />
    </div>
  );
}

function Masthead({
  asOf,
  theme,
  onToggle,
}: {
  asOf?: string;
  theme: Theme;
  onToggle: () => void;
}) {
  const dateText = asOf ? longDate(asOf) : longDate(new Date().toISOString());
  const dark = theme === "dark";
  return (
    <header className="masthead">
      <div className="dateline">
        <span>Est. MMXXVI</span>
        <button
          className="edition-toggle"
          onClick={onToggle}
          aria-pressed={dark}
          title={dark ? "Switch to the Morning Edition" : "Switch to the Evening Edition"}
        >
          <span className="orb" aria-hidden="true">{dark ? "☾" : "☀"}</span>
          {dark ? "Evening Edition" : "Morning Edition"}
        </button>
        <span>{dateText}</span>
      </div>
      <h1 className="title">
        Invest<span className="glyph">bot</span>
        <sup>Nº 01</sup>
      </h1>
      <div className="standfirst">
        <span>The advisory ledger — recommendations set in ink, never orders.</span>
        <span className="tag">Read-only · No trades</span>
      </div>
    </header>
  );
}

function Ledger({ data }: { data: PortfolioResponse }) {
  const { summary: s, risk } = data;
  const ccy = s.base_currency;
  const maxSector = Math.max(1, ...s.sector_weights.map((w) => w.weight_pct));

  return (
    <>
      <section className="figures">
        <Figure k="Total Value" v={money(s.total_value, ccy)} />
        <Figure k="Invested" v={money(s.invested_value, ccy)} />
        <Figure k="Cash on Hand" v={money(s.cash, ccy)} sub={`${s.cash_pct.toFixed(1)}% of book`} />
        <Figure k="Holdings" v={String(s.position_count)} sub="positions" />
      </section>

      <section className="s-1">
        <div className="section-head">
          <h2>Holdings</h2>
          <span className="count">{s.top_positions.length} of {s.position_count} listed</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Security</th>
              <th className="num">Last</th>
              <th className="num">Mkt Value</th>
              <th className="num">Weight</th>
              <th className="num">Unrealized</th>
            </tr>
          </thead>
          <tbody>
            {s.top_positions.map((p) => {
              const up = p.unrealized_pnl >= 0;
              return (
                <tr key={p.ticker}>
                  <td>
                    <div className="cell-ticker">{p.ticker}</div>
                    <div className="cell-name">{p.name}</div>
                    <div className="cell-sector">{p.sector ?? "—"}</div>
                  </td>
                  <td className="num">{money(p.market_price, ccy)}</td>
                  <td className="num">{money(p.market_value, ccy)}</td>
                  <td className="num">
                    <span className="weight">
                      <span>{p.weight_pct.toFixed(1)}%</span>
                      <span className="bar">
                        <span style={{ width: `${Math.min(100, p.weight_pct)}%` }} />
                      </span>
                    </span>
                  </td>
                  <td className="num">
                    <span className={`pnl ${up ? "gain" : "loss"}`}>
                      {signedMoney(p.unrealized_pnl, ccy)}
                      <span className="pct">{up ? "+" : "−"}{Math.abs(p.unrealized_pnl_pct).toFixed(1)}%</span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <div className="deck">
        <section className="s-2">
          <div className="section-head">
            <h2>Sector Exposure</h2>
          </div>
          {s.sector_weights.map((w) => (
            <div className="sector" key={w.sector}>
              <span className="name">{w.sector}</span>
              <span className="pct">{w.weight_pct.toFixed(1)}%</span>
              <span className="track">
                <span style={{ width: `${(w.weight_pct / maxSector) * 100}%` }} />
              </span>
            </div>
          ))}
        </section>

        <section className="s-3">
          <div className="section-head">
            <h2>Risk Desk</h2>
            <span className="count">{risk.violations.length} notice{risk.violations.length === 1 ? "" : "s"}</span>
          </div>
          {risk.violations.length === 0 ? (
            <p className="all-clear">All clear — every rule holds.</p>
          ) : (
            <ul className="notices">
              {risk.violations.map((v, i) => (
                <Notice key={i} v={v} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

function Notice({ v }: { v: Violation }) {
  return (
    <li className={`notice n-${v.severity}`}>
      <div className="label">{v.severity}</div>
      <span className="rule-name"> · {v.rule}</span>
      <p className="detail">{v.detail}</p>
    </li>
  );
}

function Figure({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div className="figure">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function Colophon({ account }: { account: string | null }) {
  return (
    <footer className="colophon">
      <span>Investbot · Advisory only · Not financial advice</span>
      <span>{account ? `Account ${account}` : "—"}</span>
      <span>Powered by Claude</span>
    </footer>
  );
}
