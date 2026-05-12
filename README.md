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
**Regulatory limit:** ≤ 85%

### 2. Liquidity Coverage Ratio (LCR Proxy)
Per **Basel III (BCBS 2013), Paragraph 22**:
