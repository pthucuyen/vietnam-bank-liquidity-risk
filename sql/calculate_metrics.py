import sqlite3
import json

DB_PATH = "data/liquidity_risk.db"

# ─────────────────────────────────────────
# CÔNG THỨC TÍNH METRICS
# Reference: Basel III + TT22/2019 NHNN
# ─────────────────────────────────────────

def calculate_ldr(loans_customers, deposits_customers,
                  deposits_banks, issued_bonds,
                  govt_entrusted_funds):
    """
    LDR theo TT22/2019 NHNN — Điều 20
    
    Tử số L:
        Cho vay KH
        Trừ vốn tài trợ, ủy thác CP và TCTD khác (khoản 3a)
    
    Mẫu số D:
        Tiền gửi KH + Tiền gửi TCTD + Phát hành GTCG (khoản 4)
    
    Limitation còn lại: chưa trừ được vay nước ngoài
    và tái cấp vốn NHNN do không có data public.
    """
    numerator = (
        (loans_customers or 0) -
        (govt_entrusted_funds or 0)  # ← trừ theo khoản 3a TT22
    )
    denominator = (
        (deposits_customers or 0) +
        (deposits_banks or 0) +
        (issued_bonds or 0)
    )
    if denominator > 0 and numerator > 0:
        return numerator / denominator
    return None

def calculate_lcr_proxy(cash, sbi_deposits, investment_sec,
                        deposits_customers, deposits_banks,
                        issued_bonds, loans_to_banks):
    """
    LCR Proxy theo Basel III — BCBS 2013, Paragraph 22
    
    LCR = Stock of HQLA / Total Net Cash Outflows >= 100%
    
    HQLA (proxy):
      Level 1: Cash + SBV deposits           haircut 0%
      Level 2A proxy: Investment securities  haircut 15%
      (Level 2B không tách được từ FiinPro)
    
    Outflows (proxy):
      Retail deposits (run-off 10%)
      Wholesale deposits/TCTD (run-off 25%)
      Issued bonds (run-off 5%)
    
    Inflows (proxy):
      Loans to banks maturing (inflow 100%)
      Capped at 75% of outflows per Basel III
    
    Limitations:
      - Investment sec không tách được Level 2A vs 2B
      - Inflow từ cho vay KH không estimate được
      - Không có maturity profile chi tiết
    """
    if cash is None and sbi_deposits is None:
        return None, None, None

    # ── HQLA ──────────────────────────────
    hqla = (
        (cash or 0) * 1.00 +           # Level 1
        (sbi_deposits or 0) * 1.00 +   # Level 1
        (investment_sec or 0) * 0.85   # Level 2A proxy
    )

    # ── Outflows ──────────────────────────
    outflow = (
        (deposits_customers or 0) * 0.10 +
        (deposits_banks or 0) * 0.25 +
        (issued_bonds or 0) * 0.05
    )

    # ── Inflows (capped at 75% outflow) ───
    # Proxy: loans to other banks có thể thu hồi
    raw_inflow = (loans_to_banks or 0) * 1.00
    capped_inflow = min(raw_inflow, 0.75 * outflow)  # Basel III cap

    # ── Net Cash Outflow ──────────────────
    net_outflow = outflow - capped_inflow

    if net_outflow > 0:
        lcr = hqla / net_outflow
    else:
        lcr = None

    return round(hqla, 2), round(net_outflow, 2), lcr


def calculate_nsfr_proxy(total_equity, deposits_customers,
                         deposits_banks, issued_bonds,
                         loans_customers, investment_sec):
    """
    NSFR Proxy (Basel III approximation)
    
    Available Stable Funding (ASF):
      - Vốn chủ sở hữu                     : 100%
      - Tiền gửi KH (stable, ASF 90%)      : 90%
      - Tiền gửi TCTD (ASF 50%)            : 50%
      - Trái phiếu phát hành (ASF 100%)    : 100%
    
    Required Stable Funding (RSF):
      - Cho vay KH (RSF 65%)               : 65%
      - Chứng khoán đầu tư (RSF 15%)       : 15%
    
    NSFR = ASF / RSF >= 100%
    """
    asf = (
        (total_equity or 0) * 1.00 +
        (deposits_customers or 0) * 0.90 +
        (deposits_banks or 0) * 0.50 +
        (issued_bonds or 0) * 1.00
    )

    rsf = (
        (loans_customers or 0) * 0.65 +
        (investment_sec or 0) * 0.15
    )

    if rsf and rsf > 0:
        nsfr = asf / rsf
    else:
        nsfr = None

    return round(asf, 2), round(rsf, 2), nsfr


def calculate_liquid_asset_ratio(cash, sbi_deposits,
                                 investment_sec, total_assets):
    """
    Tỷ lệ tài sản thanh khoản / Tổng tài sản
    Ngưỡng tham chiếu: tối thiểu 10%
    """
    if total_assets and total_assets > 0:
        liquid = (cash or 0) + (sbi_deposits or 0) + (investment_sec or 0)
        return liquid / total_assets
    return None


def calculate_st_funding_ratio(deposits_banks, issued_bonds,
                               total_liabilities):
    """
    Short-term Funding Ratio
    Đo lường phụ thuộc vào wholesale funding
    Ngưỡng cảnh báo: > 30%
    """
    if total_liabilities and total_liabilities > 0:
        st_funding = (deposits_banks or 0) + (issued_bonds or 0)
        return st_funding / total_liabilities
    return None


def calculate_ews(ldr, lcr, nsfr, liquid_ratio, st_funding_ratio):
    """
    Early Warning Score (0 = bình thường, 1 = cảnh báo, 2 = nguy hiểm)
    Tổng hợp tất cả metrics thành 1 score duy nhất
    """
    score = 0
    flags = []

    # LDR
    if ldr is not None:
        if ldr > 0.90:
            score += 2
            flags.append("LDR_CRITICAL: >{:.1f}%".format(ldr * 100))
        elif ldr > 0.85:
            score += 1
            flags.append("LDR_WARNING: >{:.1f}%".format(ldr * 100))

    # LCR proxy
    if lcr is not None:
        if lcr < 0.80:
            score += 2
            flags.append("LCR_CRITICAL: {:.1f}%".format(lcr * 100))
        elif lcr < 1.00:
            score += 1
            flags.append("LCR_WARNING: {:.1f}%".format(lcr * 100))

    # NSFR proxy
    if nsfr is not None:
        if nsfr < 0.80:
            score += 2
            flags.append("NSFR_CRITICAL: {:.1f}%".format(nsfr * 100))
        elif nsfr < 1.00:
            score += 1
            flags.append("NSFR_WARNING: {:.1f}%".format(nsfr * 100))

    # Liquid Asset Ratio
    if liquid_ratio is not None:
        if liquid_ratio < 0.05:
            score += 2
            flags.append("LIQUID_RATIO_CRITICAL: {:.1f}%".format(liquid_ratio * 100))
        elif liquid_ratio < 0.10:
            score += 1
            flags.append("LIQUID_RATIO_WARNING: {:.1f}%".format(liquid_ratio * 100))

    # Short-term Funding
    if st_funding_ratio is not None:
        if st_funding_ratio > 0.40:
            score += 2
            flags.append("ST_FUNDING_CRITICAL: {:.1f}%".format(st_funding_ratio * 100))
        elif st_funding_ratio > 0.30:
            score += 1
            flags.append("ST_FUNDING_WARNING: {:.1f}%".format(st_funding_ratio * 100))

    return score, json.dumps(flags, ensure_ascii=False)


# ─────────────────────────────────────────
# MAIN: ĐỌC → TÍNH → INSERT
# ─────────────────────────────────────────
def run(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT
            f.bank_id, f.period_year, f.period_quarter,
            f.cash_and_gold, f.deposits_at_sbi,
            f.investment_securities, f.trading_securities,
            f.loans_to_customers, f.total_assets,
            f.total_liabilities, f.deposits_from_customers,
            f.deposits_from_banks, f.issued_bonds,
            f.total_equity, f.govt_entrusted_funds,
            f.deposits_at_other_banks
        FROM financial_data f
        ORDER BY f.bank_id, f.period_year, f.period_quarter
    """).fetchall()

    inserted = 0

    for r in rows:
        # ── Tính từng metric ──────────────────
        ldr = calculate_ldr(
            r["loans_to_customers"],
            r["deposits_from_customers"],
            r["deposits_from_banks"],
            r["issued_bonds"],
            r["govt_entrusted_funds"]
        )

        hqla, outflow, lcr = calculate_lcr_proxy(
            r["cash_and_gold"],
            r["deposits_at_sbi"],
            r["investment_securities"],
            r["deposits_from_customers"],
            r["deposits_from_banks"],
            r["issued_bonds"],
            r["deposits_at_other_banks"]
        )

        asf, rsf, nsfr = calculate_nsfr_proxy(
            r["total_equity"],
            r["deposits_from_customers"],
            r["deposits_from_banks"],
            r["issued_bonds"],
            r["loans_to_customers"],
            r["investment_securities"]
        )

        liquid_ratio = calculate_liquid_asset_ratio(
            r["cash_and_gold"],
            r["deposits_at_sbi"],
            r["investment_securities"],
            r["total_assets"]
        )

        st_funding = calculate_st_funding_ratio(
            r["deposits_from_banks"],
            r["issued_bonds"],
            r["total_liabilities"]
        )

        ews_score, ews_flags = calculate_ews(
            ldr, lcr, nsfr, liquid_ratio, st_funding
        )

        # ── Breach flags ──────────────────────
        ldr_breach = 1 if (ldr and ldr > 0.85) else 0
        lcr_breach = 1 if (lcr and lcr < 1.00) else 0
        nsfr_breach = 1 if (nsfr and nsfr < 1.00) else 0

        # ── Insert vào liquidity_metrics ──────
        conn.execute("""
            INSERT OR REPLACE INTO liquidity_metrics (
                bank_id, period_year, period_quarter,
                ldr, ldr_breach,
                hqla_proxy, net_cash_outflow_proxy, lcr_proxy, lcr_breach,
                asf_proxy, rsf_proxy, nsfr_proxy, nsfr_breach,
                liquid_asset_ratio,
                short_term_funding_ratio,
                ews_score, ews_flags,
                methodology_version
            ) VALUES (
                ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?,
                ?,
                ?, ?,
                'v1.0'
            )
        """, (
            r["bank_id"], r["period_year"], r["period_quarter"],
            ldr, ldr_breach,
            hqla, outflow, lcr, lcr_breach,
            asf, rsf, nsfr, nsfr_breach,
            liquid_ratio,
            st_funding,
            ews_score, ews_flags
        ))
        inserted += 1

    conn.commit()

    # ── Summary ───────────────────────────────
    print(f"✅ Calculated and inserted: {inserted} records\n")

    print("📊 Liquidity Metrics Summary (latest quarter per bank):")
    summary = conn.execute("""
        SELECT
            b.bank_code,
            m.period_year || 'Q' || m.period_quarter AS period,
            ROUND(m.ldr * 100, 1)                AS ldr_pct,
            ROUND(m.lcr_proxy * 100, 1)          AS lcr_pct,
            ROUND(m.nsfr_proxy * 100, 1)         AS nsfr_pct,
            ROUND(m.liquid_asset_ratio * 100, 1) AS liquid_pct,
            m.ews_score,
            m.ldr_breach,
            m.lcr_breach
        FROM liquidity_metrics m
        JOIN banks b ON m.bank_id = b.bank_id
        WHERE m.period_year || m.period_quarter = (
            SELECT MAX(m2.period_year || m2.period_quarter)
            FROM liquidity_metrics m2
            WHERE m2.bank_id = m.bank_id
        )
        ORDER BY b.bank_code
    """).fetchall()

    print(f"   {'Bank':<6} {'Period':<8} {'LDR%':<8} "
          f"{'LCR%':<8} {'NSFR%':<8} {'Liq%':<8} "
          f"{'EWS':<5} {'Breach'}")
    print(f"   {'-'*65}")

    for s in summary:
        breach_flags = []
        if s["ldr_breach"]:
            breach_flags.append("LDR")
        if s["lcr_breach"]:
            breach_flags.append("LCR")
        breach_str = ",".join(breach_flags) if breach_flags else "—"

        print(
            f"   {s['bank_code']:<6} {s['period']:<8} "
            f"{str(s['ldr_pct'])+'%':<8} "
            f"{str(s['lcr_pct'])+'%':<8} "
            f"{str(s['nsfr_pct'])+'%':<8} "
            f"{str(s['liquid_pct'])+'%':<8} "
            f"{s['ews_score']:<5} {breach_str}"
        )

    conn.close()


if __name__ == "__main__":
    run(DB_PATH)