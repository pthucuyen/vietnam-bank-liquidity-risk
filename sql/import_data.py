import pandas as pd
import sqlite3
import re
import os

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
EXCEL_PATH = r"C:\Users\FPT\OneDrive\Documents\1. vietnam-bank-liquidity-risk\data\raw\FiinProX_DE_Doanh_nghiep_20260511.xlsx"
DB_PATH    = "data/liquidity_risk.db"

# Map tên cột FiinPro → tên field trong DB
COLUMN_MAP = {
    "A. TỔNG TÀI SẢN"                                       : "total_assets",
    "1. Tiền mặt, vàng bạc, đá quý"                         : "cash_and_gold",
    "12. Tiền gửi tại NHNN (GT)"                            : "deposits_at_sbi",
    "3. Tiền gửi tại các TCTD khác và cho vay các TCTD khác": "deposits_at_other_banks",
    "8. Chứng khoán đầu tư"                                 : "investment_securities",
    "6. Cho vay khách hàng"                       : "loans_to_customers",
    "2.1. Chứng khoán kinh doanh"                 : "trading_securities",
    "I. TỔNG NỢ PHẢI TRẢ"                         : "total_liabilities",
    "3. Tiền gửi của khách hàng"                  : "deposits_from_customers",
    "2. Tiền gửi và vay các Tổ chức tín dụng khác": "deposits_from_banks",
    "6. Phát hành giấy tờ có giá"                 : "issued_bonds",
    "5. Vốn tài trợ, uỷ thác đầu tư của Chính phủ": "govt_entrusted_funds",
    "II. VỐN CHỦ SỞ HỮU"                          : "total_equity",
    "1. Thu nhập lãi thuần"                       : "net_interest_income",
    "8. Tổng thu nhập hoạt động"                            : "total_operating_income",
}

# Map mã FiinPro → bank_id trong DB (theo thứ tự seed)
BANK_ID_MAP = {
    "TCB": 1,
    "MBB": 2,
    "VPB": 3,
    "ACB": 4,
    "VCB": 5,
    "OCB": 6,
}


# ─────────────────────────────────────────
# STEP 1: ĐỌC FILE EXCEL
# ─────────────────────────────────────────
def parse_column_header(col_str: str) -> tuple:
    """
    Parse tên cột FiinPro thành (metric_name, quarter, year).
    
    Input:  "A. TỔNG TÀI SẢN\nHợp nhất\nQuý: Q2\nNăm: 2024\nĐơn vị: VND"
    Output: ("A. TỔNG TÀI SẢN", 2, 2024)
    """
    lines = [l.strip() for l in str(col_str).split("\n") if l.strip()]
    
    metric_name = lines[0] if lines else ""
    quarter     = None
    year        = None
    
    for line in lines:
        q_match = re.search(r"Quý:\s*Q(\d)", line)
        y_match = re.search(r"Năm:\s*(\d{4})", line)
        if q_match:
            quarter = int(q_match.group(1))
        if y_match:
            year = int(y_match.group(1))
    
    return metric_name, quarter, year


def load_excel(path: str) -> pd.DataFrame:
    print(f"📂 Đọc file: {path}")
    df = pd.read_excel(
        path,
        sheet_name="Sheet1",
        header=7,        # hàng 8 trong Excel = index 7 (đếm từ 0)
        usecols="A:GB",  # đúng range Uyên cho
    )
    print(f"   Rows: {len(df)}, Cols: {len(df.columns)}")
    return df

# ─────────────────────────────────────────
# STEP 2: TRANSFORM — wide → long format
# ─────────────────────────────────────────
def transform(df: pd.DataFrame) -> list[dict]:
    """
    Chuyển từ wide format (FiinPro) sang list of dicts
    sẵn sàng để INSERT vào bảng financial_data.
    """
    records = {}  # key: (bank_id, year, quarter)

    for col in df.columns:
        metric_name, quarter, year = parse_column_header(col)

        # Bỏ qua cột không phải data (STT, Mã, Tên, Sàn)
        if quarter is None or year is None:
            continue

        # Tìm db_field tương ứng
        db_field = None
        for fiinpro_name, field in COLUMN_MAP.items():
            if fiinpro_name in metric_name:
                db_field = field
                break

        if db_field is None:
            continue  # Cột không cần thiết, bỏ qua

        # Lặp qua từng ngân hàng (mỗi hàng)
        for _, row in df.iterrows():
            bank_code = str(row.get("Mã", "")).strip().upper()

            if bank_code not in BANK_ID_MAP:
                continue  # Bỏ qua ngân hàng không trong danh sách

            bank_id = BANK_ID_MAP[bank_code]
            key     = (bank_id, year, quarter)

            if key not in records:
                records[key] = {
                    "bank_id":        bank_id,
                    "period_year":    year,
                    "period_quarter": quarter,
                    "data_source":    "FIINPROX",
                    "is_audited":     0,
                }

            # Lấy giá trị, convert sang tỷ VND (FiinPro xuất VND)
            raw_val = row[col]
            if pd.notna(raw_val) and raw_val != "" and raw_val != 0:
                try:
                    records[key][db_field] = float(raw_val) / 1_000_000_000
                except (ValueError, TypeError):
                    records[key][db_field] = None
            else:
                records[key][db_field] = None

    result = list(records.values())
    print(f"✅ Transform xong: {len(result)} records")
    return result


# ─────────────────────────────────────────
# STEP 3: LOAD VÀO SQLITE
# ─────────────────────────────────────────
def load_to_db(records: list[dict], db_path: str):
    conn = sqlite3.connect(db_path)

    inserted = 0
    skipped  = 0

    for rec in records:
        # Chỉ insert nếu có ít nhất total_assets
        if rec.get("total_assets") is None:
            skipped += 1
            continue

        cols   = ", ".join(rec.keys())
        pholds = ", ".join(["?"] * len(rec))
        vals   = list(rec.values())

        try:
            conn.execute(
                f"INSERT OR REPLACE INTO financial_data ({cols}) VALUES ({pholds})",
                vals
            )
            inserted += 1
        except Exception as e:
            print(f"   ⚠️  Lỗi insert {rec.get('bank_id')} {rec.get('period_year')}Q{rec.get('period_quarter')}: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    print(f"✅ Load xong: {inserted} inserted, {skipped} skipped")


# ─────────────────────────────────────────
# STEP 4: VERIFY
# ─────────────────────────────────────────
def verify(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print("\n📊 Data summary:")
    rows = conn.execute("""
        SELECT 
            b.bank_code,
            COUNT(*) as quarters,
            MIN(f.period_year || 'Q' || f.period_quarter) as earliest,
            MAX(f.period_year || 'Q' || f.period_quarter) as latest,
            ROUND(AVG(f.total_assets), 0) as avg_total_assets_ty_vnd
        FROM financial_data f
        JOIN banks b ON f.bank_id = b.bank_id
        GROUP BY b.bank_code
        ORDER BY b.bank_code
    """).fetchall()

    print(f"   {'Bank':<6} {'Quarters':<10} {'Earliest':<10} {'Latest':<10} {'Avg Assets (tỷ)'}")
    print(f"   {'-'*55}")
    for r in rows:
        print(f"   {r['bank_code']:<6} {r['quarters']:<10} {r['earliest']:<10} {r['latest']:<10} {r['avg_total_assets_ty_vnd']:>15,.0f}")

    conn.close()


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    df      = load_excel(EXCEL_PATH)
    records = transform(df)
    load_to_db(records, DB_PATH)
    verify(DB_PATH)