-- ============================================================
-- VIETNAM BANK LIQUIDITY RISK DATABASE
-- Schema version 1.0
-- Reference: Basel III Liquidity Framework + TT22/2019 NHNN
-- ============================================================

-- ------------------------------------------------------------
-- TABLE 1: BANKS
-- Thông tin tĩnh về từng ngân hàng
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS banks (
    bank_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_code       TEXT NOT NULL UNIQUE,   -- VD: 'TCB', 'MBB', 'VPB'
    bank_name_vn    TEXT NOT NULL,          -- Tên đầy đủ tiếng Việt
    bank_name_en    TEXT,
    bank_type       TEXT,                   -- 'SOE' | 'JSB' | 'FOREIGN'
    tier1_capital   REAL,                   -- Vốn cấp 1 (tỷ VND), dùng để normalize
    listing_exchange TEXT,                  -- 'HOSE' | 'HNX' | 'UPCOM'
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- TABLE 2: FINANCIAL_DATA  
-- Raw data từ Bảng cân đối kế toán (BCĐKT) theo quý
-- Đơn vị: tỷ VND
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_data (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id                 INTEGER NOT NULL,
    period_year             INTEGER NOT NULL,   -- VD: 2024
    period_quarter          INTEGER NOT NULL,   -- 1 | 2 | 3 | 4
    report_date             TEXT,               -- ngày công bố BCTC

    -- ASSETS (Tài sản)
    total_assets            REAL,   -- Tổng tài sản
    cash_and_gold           REAL,   -- Tiền mặt, vàng
    deposits_at_sbi         REAL,   -- Tiền gửi tại NHNN
    deposits_at_other_banks REAL,   -- Tiền gửi tại TCTD khác (thị trường 2)
    trading_securities      REAL,   -- Chứng khoán kinh doanh
    investment_securities   REAL,   -- Chứng khoán đầu tư (HQLA proxy)
    loans_to_customers      REAL,   -- Cho vay khách hàng (thị trường 1)
    loans_to_banks          REAL,   -- Cho vay TCTD khác

    -- LIABILITIES (Nợ phải trả)  
    total_liabilities       REAL,
    deposits_from_customers REAL,   -- Tiền gửi khách hàng (core funding)
    deposits_from_banks     REAL,   -- Tiền gửi từ TCTD khác (wholesale)
    issued_bonds            REAL,   -- Trái phiếu phát hành
    short_term_borrowings   REAL,   -- Vay ngắn hạn (< 1 năm)
    long_term_borrowings    REAL,   -- Vay dài hạn (>= 1 năm)

    -- EQUITY
    total_equity            REAL,   -- Vốn chủ sở hữu

    -- INCOME STATEMENT items (từ KQKD)
    net_interest_income     REAL,   -- Thu nhập lãi thuần
    total_operating_income  REAL,

    -- DATA QUALITY
    data_source             TEXT,   -- 'BCTC_OFFICIAL' | 'CAFEF' | 'ESTIMATED'
    is_audited              INTEGER DEFAULT 0,  -- 1 = đã kiểm toán
    notes                   TEXT,

    FOREIGN KEY (bank_id) REFERENCES banks(bank_id),
    UNIQUE(bank_id, period_year, period_quarter)
);

-- ------------------------------------------------------------
-- TABLE 3: LIQUIDITY_METRICS
-- Calculated metrics — tách riêng khỏi raw data
-- Mỗi lần recalculate sẽ UPDATE bảng này
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS liquidity_metrics (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id             INTEGER NOT NULL,
    period_year         INTEGER NOT NULL,
    period_quarter      INTEGER NOT NULL,

    -- METRIC 1: Loan-to-Deposit Ratio (LDR)
    -- Theo TT22/2019: tối đa 85% cho ngân hàng nội địa
    ldr                 REAL,   -- loans / deposits_from_customers
    ldr_tt22_limit      REAL DEFAULT 0.85,
    ldr_breach          INTEGER DEFAULT 0,  -- 1 nếu vượt ngưỡng

    -- METRIC 2: LCR Proxy (Basel III)
    -- LCR thật cần HQLA chi tiết, đây là approximation
    -- HQLA proxy = cash + SBV deposits + investment_securities * 0.85
    -- Net cash outflow proxy = short_term_liabilities * 0.25
    hqla_proxy          REAL,
    net_cash_outflow_proxy REAL,
    lcr_proxy           REAL,   -- hqla_proxy / net_cash_outflow_proxy
    lcr_basel_limit     REAL DEFAULT 1.0,   -- Basel III: tối thiểu 100%
    lcr_breach          INTEGER DEFAULT 0,

    -- METRIC 3: NSFR Proxy (Basel III)
    -- Available Stable Funding proxy = equity + long_term deposits + bonds
    -- Required Stable Funding proxy = loans * 0.65 (haircut)
    asf_proxy           REAL,
    rsf_proxy           REAL,
    nsfr_proxy          REAL,   -- asf / rsf
    nsfr_basel_limit    REAL DEFAULT 1.0,
    nsfr_breach         INTEGER DEFAULT 0,

    -- METRIC 4: Liquid Asset Ratio
    -- Tỷ lệ tài sản thanh khoản / tổng tài sản
    liquid_asset_ratio  REAL,

    -- METRIC 5: Short-term Funding Ratio  
    -- Đo lường sự phụ thuộc vào wholesale/short-term funding
    short_term_funding_ratio REAL,  -- (deposits_from_banks + short_term_borrowings) / total_liabilities

    -- EARLY WARNING SIGNALS
    -- Tổng hợp: 0 = bình thường, 1 = cảnh báo, 2 = nguy hiểm
    ews_score           INTEGER DEFAULT 0,
    ews_flags           TEXT,   -- JSON string mô tả flags cụ thể

    -- METADATA
    calculated_at       TEXT DEFAULT (datetime('now')),
    methodology_version TEXT DEFAULT 'v1.0',

    FOREIGN KEY (bank_id) REFERENCES banks(bank_id),
    UNIQUE(bank_id, period_year, period_quarter)
);

-- ------------------------------------------------------------
-- INDEXES — tăng tốc query
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_financial_bank_period 
    ON financial_data(bank_id, period_year, period_quarter);

CREATE INDEX IF NOT EXISTS idx_metrics_bank_period 
    ON liquidity_metrics(bank_id, period_year, period_quarter);

CREATE INDEX IF NOT EXISTS idx_metrics_breach 
    ON liquidity_metrics(ldr_breach, lcr_breach, nsfr_breach);

-- ------------------------------------------------------------
-- VIEW: LIQUIDITY_DASHBOARD
-- Join 3 tables để query một lần duy nhất
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_liquidity_dashboard AS
SELECT
    b.bank_code,
    b.bank_name_vn,
    b.bank_type,
    f.period_year,
    f.period_quarter,
    f.period_year || 'Q' || f.period_quarter AS period_label,

    -- Raw data
    f.total_assets,
    f.loans_to_customers,
    f.deposits_from_customers,
    f.investment_securities,

    -- Metrics
    ROUND(m.ldr * 100, 2)               AS ldr_pct,
    ROUND(m.lcr_proxy * 100, 2)         AS lcr_proxy_pct,
    ROUND(m.nsfr_proxy * 100, 2)        AS nsfr_proxy_pct,
    ROUND(m.liquid_asset_ratio * 100, 2) AS liquid_asset_ratio_pct,
    ROUND(m.short_term_funding_ratio * 100, 2) AS st_funding_ratio_pct,

    -- Breach flags
    m.ldr_breach,
    m.lcr_breach,
    m.nsfr_breach,
    m.ews_score,
    m.ews_flags

FROM banks b
JOIN financial_data f ON b.bank_id = f.bank_id
LEFT JOIN liquidity_metrics m 
    ON b.bank_id = m.bank_id 
    AND f.period_year = m.period_year 
    AND f.period_quarter = m.period_quarter
ORDER BY b.bank_code, f.period_year, f.period_quarter;