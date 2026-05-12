# 🏦 Vietnam Bank Liquidity Risk Dashboard

> A quantitative liquidity risk monitoring project analyzing 6 Vietnamese commercial banks
> using Basel III framework and NHNN regulations (TT22/2019).

**Live Dashboard →** [View Interactive Dashboard](https://pthucuyen.github.io/vietnam-bank-liquidity-risk/reports/dashboard.html)

---

## 📌 Project Overview

This project simulates the core workflow of a **Liquidity Risk Analyst** at a Vietnamese commercial bank:

1. Collecting and structuring balance sheet data from public financial statements
2. Computing key liquidity metrics per Basel III and NHNN regulatory standards
3. Detecting early warning signals across a multi-bank portfolio
4. Visualizing trends and risk levels in an interactive dashboard

**Banks covered:** ACB · MBB · OCB · TCB · VCB · VPB
**Period:** Q1/2024 – Q1/2026 (9 quarters)
**Data source:** FiinPro-X (balance sheet, quarterly)

---

## 📐 Metrics & Methodology

### 1. Loan-to-Deposit Ratio (LDR)

Per **TT22/2019 NHNN, Điều 20**:

    LDR = (Loans to customers − Govt entrusted funds)
          ─────────────────────────────────────────────
          Customer deposits + Interbank deposits + Issued bonds

**Regulatory limit:** ≤ 85%

### 2. Liquidity Coverage Ratio (LCR Proxy)

Per **Basel III (BCBS 2013), Paragraph 22**:

    LCR = HQLA / Net Cash Outflow ≥ 100%

    HQLA proxy:
      Cash & gold               × 100%  (Level 1)
      SBV deposits              × 100%  (Level 1)
      Investment securities     × 85%   (Level 2A proxy)

    Net Cash Outflow = Outflow − min(Inflow, 75% × Outflow)

    Outflow:  Customer deposits    × 10%
              Interbank deposits   × 25%
              Issued bonds         × 5%

    Inflow:   Interbank lending    × 100% (capped at 75% of outflow)

**Minimum:** ≥ 100%

### 3. Net Stable Funding Ratio (NSFR Proxy)

Per **Basel III**:

    NSFR = Available Stable Funding (ASF) / Required Stable Funding (RSF) ≥ 100%

    ASF:  Equity × 100% + Customer deposits × 90%
          + Interbank deposits × 50% + Issued bonds × 100%

    RSF:  Loans to customers × 65% + Investment securities × 15%

**Minimum:** ≥ 100%

### 4. Liquid Asset Ratio

    Liquid Asset Ratio = (Cash + SBV deposits + Investment securities) / Total assets

**Reference threshold:** ≥ 10%

### 5. Early Warning Score (EWS)

Composite score aggregating all metrics into a single risk signal:

| Score | Level    | Condition                          |
|-------|----------|------------------------------------|
| 0     | 🟢 Normal  | All metrics within limits          |
| 1–2   | 🟡 Watch   | One metric approaching limit       |
| 3–4   | 🟠 Warning | Multiple metrics breaching         |
| 5+    | 🔴 Danger  | Severe multi-metric breach         |

---

## ⚠️ Limitations & Known Gaps

Public financial statement data (FiinPro-X) does not provide sufficient granularity
to fully replicate regulatory calculations. The following adjustments were not possible:

| Item | Regulatory Requirement | Data Availability |
|------|----------------------|-------------------|
| Margin deposits (tiền ký quỹ) | Exclude from deposits (TT22 §4) | Thuyết minh BCTC only |
| State Treasury deposits | Exclude from deposits (TT22 §4a-i) | Not separated in FiinPro |
| Foreign borrowings | Exclude from loans (TT22 §3b) | Not in public BCTC |
| SBV refinancing | Exclude from loans (TT22 §3c) | Not in public BCTC |
| Level 1 vs Level 2B securities | Different haircuts per Basel III | Aggregated in FiinPro |

**Impact:** All gaps cause LDR and LCR proxies to be **conservative**
(higher LDR, lower LCR than actual) — directionally safe for risk monitoring purposes.

**Run-off rate note:** Standard Basel III assumptions used (retail 10%, wholesale 25%).
SVB 2023 demonstrated actual outflows can significantly exceed these assumptions
in digital bank run scenarios.

---

## 🛠️ Tech Stack

| Tool | Purpose |
|------|---------|
| Python | Data pipeline, metric calculation |
| SQLite | Structured storage (3 tables, 1 view) |
| Pandas | Data transformation |
| Plotly | Interactive dashboard |
| SQL | Schema design, querying |
| FiinPro-X | Data source (balance sheet, quarterly) |

---

## 📁 Repository Structure

    vietnam-bank-liquidity-risk/
    │
    ├── sql/
    │   ├── schema.sql            ← Database schema (3 tables, 3 indexes, 1 view)
    │   ├── init_database.py      ← Initialize DB and seed bank data
    │   ├── import_data.py        ← Parse FiinPro-X Excel → SQLite
    │   └── calculate_metrics.py  ← Compute LDR, LCR, NSFR, EWS
    │
    ├── notebooks/
    │   └── dashboard.py          ← Build interactive HTML dashboard
    │
    ├── reports/
    │   └── dashboard.html        ← Interactive output (Plotly)
    │
    └── excel/                    ← VBA Excel report (coming soon)

---

## 🚀 How to Run

    # 1. Clone repo
    git clone https://github.com/pthucuyen/vietnam-bank-liquidity-risk.git
    cd vietnam-bank-liquidity-risk

    # 2. Create virtual environment
    python -m venv venv
    venv\Scripts\activate        # Windows
    source venv/bin/activate     # Mac/Linux

    # 3. Install dependencies
    pip install pandas openpyxl plotly

    # 4. Initialize database
    python sql/init_database.py

    # 5. Import data (requires FiinPro-X export)
    python sql/import_data.py

    # 6. Calculate metrics
    python sql/calculate_metrics.py

    # 7. Build dashboard
    python notebooks/dashboard.py

---

## 📚 Regulatory References

- Basel III: *Basel III: The Liquidity Coverage Ratio and liquidity risk monitoring tools*
  — BCBS, January 2013
- TT22/2019/TT-NHNN: *Quy định các giới hạn, tỷ lệ bảo đảm an toàn trong hoạt động
  của ngân hàng, chi nhánh ngân hàng nước ngoài* — NHNN, 2019
- TT83/2024 (IRRBB): *Quy định về quản lý rủi ro lãi suất trong hoạt động ngân hàng*