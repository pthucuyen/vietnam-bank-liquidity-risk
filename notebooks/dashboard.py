import sqlite3
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

DB_PATH     = "data/liquidity_risk.db"
OUTPUT_PATH = "reports/dashboard.html"

# ─────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────
def load_data(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("""
        SELECT
            b.bank_code,
            m.period_year,
            m.period_quarter,
            m.period_year || 'Q' || m.period_quarter AS period,
            ROUND(m.ldr * 100, 1)                    AS ldr_pct,
            ROUND(m.lcr_proxy * 100, 1)              AS lcr_pct,
            ROUND(m.nsfr_proxy * 100, 1)             AS nsfr_pct,
            ROUND(m.liquid_asset_ratio * 100, 1)     AS liquid_pct,
            ROUND(m.short_term_funding_ratio * 100, 1) AS st_funding_pct,
            m.ews_score,
            m.ldr_breach,
            m.lcr_breach,
            m.nsfr_breach
        FROM liquidity_metrics m
        JOIN banks b ON m.bank_id = b.bank_id
        ORDER BY b.bank_code, m.period_year, m.period_quarter
    """, conn)
    conn.close()
    return df


# ─────────────────────────────────────────
# COLOR MAP
# ─────────────────────────────────────────
BANK_COLORS = {
    "ACB": "#1f77b4",
    "MBB": "#ff7f0e",
    "OCB": "#2ca02c",
    "TCB": "#d62728",
    "VCB": "#9467bd",
    "VPB": "#8c564b",
}

EWS_COLORS = {
    0: "#2ecc71",   # xanh lá — bình thường
    1: "#f39c12",   # vàng — cảnh báo nhẹ
    2: "#e67e22",   # cam — cảnh báo
    3: "#e74c3c",   # đỏ — nguy hiểm
    4: "#c0392b",   # đỏ đậm — rất nguy hiểm
}


# ─────────────────────────────────────────
# CHART 1: LDR TREND
# ─────────────────────────────────────────
def chart_ldr_trend(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    for bank, color in BANK_COLORS.items():
        bank_df = df[df["bank_code"] == bank]
        fig.add_trace(go.Scatter(
            x=bank_df["period"],
            y=bank_df["ldr_pct"],
            name=bank,
            line=dict(color=color, width=2),
            mode="lines+markers",
            marker=dict(size=6),
            hovertemplate=f"<b>{bank}</b><br>Period: %{{x}}<br>LDR: %{{y:.1f}}%<extra></extra>"
        ))

    # Đường ngưỡng TT22
    fig.add_hline(
        y=85,
        line_dash="dash",
        line_color="red",
        line_width=1.5,
        annotation_text="TT22/2019 limit: 85%",
        annotation_position="top right",
        annotation_font_color="red"
    )

    fig.update_layout(
        title=dict(
            text="Loan-to-Deposit Ratio (LDR) — Q1/2024 to Q1/2026",
            font=dict(size=16)
        ),
        xaxis_title="Quarter",
        yaxis_title="LDR (%)",
        yaxis=dict(range=[50, 110]),
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=420
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
    return fig


# ─────────────────────────────────────────
# CHART 2: LCR vs NSFR BAR (latest quarter)
# ─────────────────────────────────────────
def chart_lcr_nsfr(df: pd.DataFrame) -> go.Figure:
    latest = df.sort_values(
        ["period_year", "period_quarter"]
    ).groupby("bank_code").last().reset_index()

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="LCR Proxy",
        x=latest["bank_code"],
        y=latest["lcr_pct"],
        marker_color=[BANK_COLORS[b] for b in latest["bank_code"]],
        opacity=0.85,
        hovertemplate="<b>%{x}</b><br>LCR: %{y:.1f}%<extra></extra>"
    ))

    fig.add_trace(go.Bar(
        name="NSFR Proxy",
        x=latest["bank_code"],
        y=latest["nsfr_pct"],
        marker_color=[BANK_COLORS[b] for b in latest["bank_code"]],
        opacity=0.45,
        hovertemplate="<b>%{x}</b><br>NSFR: %{y:.1f}%<extra></extra>"
    ))

    # Đường ngưỡng Basel 100%
    fig.add_hline(
        y=100,
        line_dash="dash",
        line_color="red",
        line_width=1.5,
        annotation_text="Basel III minimum: 100%",
        annotation_position="top right",
        annotation_font_color="red"
    )

    fig.update_layout(
        title=dict(
            text="LCR & NSFR Proxy — Latest Quarter (Q1/2026)",
            font=dict(size=16)
        ),
        xaxis_title="Bank",
        yaxis_title="Ratio (%)",
        barmode="group",
        legend=dict(orientation="h", y=-0.2),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=420
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
    return fig


# ─────────────────────────────────────────
# CHART 3: EWS HEATMAP
# ─────────────────────────────────────────
def chart_ews_heatmap(df: pd.DataFrame) -> go.Figure:
    pivot = df.pivot(
        index="bank_code",
        columns="period",
        values="ews_score"
    )

    # Sort columns chronologically
    cols = sorted(pivot.columns,
                  key=lambda x: (int(x[:4]), int(x[5])))
    pivot = pivot[cols]

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=[
            [0.0,  "#2ecc71"],
            [0.25, "#f39c12"],
            [0.5,  "#e67e22"],
            [0.75, "#e74c3c"],
            [1.0,  "#c0392b"],
        ],
        zmin=0, zmax=4,
        text=pivot.values,
        texttemplate="%{text}",
        hovertemplate="<b>%{y}</b><br>%{x}<br>EWS Score: %{z}<extra></extra>",
        showscale=True,
        colorbar=dict(
            title="EWS Score",
            tickvals=[0, 1, 2, 3, 4],
            ticktext=["0 Normal", "1 Watch", "2 Caution", "3 Warning", "4 Danger"]
        )
    ))

    fig.update_layout(
        title=dict(
            text="Early Warning Score Heatmap — All Banks & Quarters",
            font=dict(size=16)
        ),
        xaxis_title="Quarter",
        yaxis_title="Bank",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=380
    )
    return fig


# ─────────────────────────────────────────
# CHART 4: LIQUID ASSET RATIO TREND
# ─────────────────────────────────────────
def chart_liquid_ratio(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    for bank, color in BANK_COLORS.items():
        bank_df = df[df["bank_code"] == bank]
        fig.add_trace(go.Scatter(
            x=bank_df["period"],
            y=bank_df["liquid_pct"],
            name=bank,
            line=dict(color=color, width=2),
            mode="lines+markers",
            marker=dict(size=6),
            hovertemplate=f"<b>{bank}</b><br>Period: %{{x}}<br>Liquid Ratio: %{{y:.1f}}%<extra></extra>"
        ))

    # Đường ngưỡng tham chiếu 10%
    fig.add_hline(
        y=10,
        line_dash="dash",
        line_color="orange",
        line_width=1.5,
        annotation_text="Reference: 10%",
        annotation_position="top right",
        annotation_font_color="orange"
    )

    fig.update_layout(
        title=dict(
            text="Liquid Asset Ratio — Q1/2024 to Q1/2026",
            font=dict(size=16)
        ),
        xaxis_title="Quarter",
        yaxis_title="Liquid Asset Ratio (%)",
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=420
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
    return fig


# ─────────────────────────────────────────
# ASSEMBLE DASHBOARD
# ─────────────────────────────────────────
def build_dashboard(df: pd.DataFrame, output_path: str):
    fig1 = chart_ldr_trend(df)
    fig2 = chart_lcr_nsfr(df)
    fig3 = chart_ews_heatmap(df)
    fig4 = chart_liquid_ratio(df)

    # Ghép 4 charts thành 1 HTML file
    html_parts = []

    html_parts.append("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Vietnam Bank Liquidity Risk Dashboard</title>
        <style>
            body {
                font-family: 'Segoe UI', Arial, sans-serif;
                background: #f8f9fa;
                margin: 0;
                padding: 20px;
            }
            .header {
                background: #0D1A63;
                color: white;
                padding: 24px 32px;
                border-radius: 8px;
                margin-bottom: 24px;
            }
            .header h1 { margin: 0; font-size: 22px; }
            .header p  { margin: 6px 0 0; opacity: 0.8; font-size: 13px; }
            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
            }
            .card {
                background: white;
                border-radius: 8px;
                padding: 16px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            }
            .card-full {
                background: white;
                border-radius: 8px;
                padding: 16px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.08);
                margin-bottom: 20px;
            }
            .disclaimer {
                font-size: 11px;
                color: #888;
                margin-top: 24px;
                padding: 12px;
                border-top: 1px solid #eee;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏦 Vietnam Bank Liquidity Risk Dashboard</h1>
            <p>Banks: ACB · MBB · OCB · TCB · VCB · VPB &nbsp;|&nbsp;
               Period: Q1/2024 – Q1/2026 &nbsp;|&nbsp;
               Framework: Basel III + TT22/2019 NHNN &nbsp;|&nbsp;
               Data: FiinPro-X</p>
        </div>
    """)

    # Chart 3 — heatmap full width
    html_parts.append('<div class="card-full">')
    html_parts.append(fig3.to_html(full_html=False, include_plotlyjs="cdn"))
    html_parts.append('</div>')

    # Chart 1 + 2 — side by side
    html_parts.append('<div class="grid">')
    html_parts.append('<div class="card">')
    html_parts.append(fig1.to_html(full_html=False, include_plotlyjs=False))
    html_parts.append('</div>')
    html_parts.append('<div class="card">')
    html_parts.append(fig2.to_html(full_html=False, include_plotlyjs=False))
    html_parts.append('</div>')
    html_parts.append('</div>')

    # Chart 4 — full width
    html_parts.append('<div class="card-full" style="margin-top:20px">')
    html_parts.append(fig4.to_html(full_html=False, include_plotlyjs=False))
    html_parts.append('</div>')

    html_parts.append("""
        <div class="disclaimer">
            <b>Methodology note:</b>
            LCR and NSFR are proxies calculated from public BCTC data via FiinPro-X.
            LDR follows TT22/2019 NHNN Điều 20 with available data adjustments.
            Limitations: tiền ký quỹ, tiền Kho bạc, vay nước ngoài, tái cấp vốn NHNN
            cannot be excluded due to data unavailability in public financial statements.
            Investment securities haircut applied at 15% (Level 2A proxy) —
            Level 1 Govt bonds vs Level 2B corporate bonds not separable from FiinPro data.
            Run-off rates follow Basel III standard assumptions; actual outflows may differ
            significantly in stress scenarios (ref: SVB 2023).
        </div>
    </body>
    </html>
    """)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    print(f"✅ Dashboard saved: {output_path}")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    df = load_data(DB_PATH)
    print(f"📊 Loaded {len(df)} records for {df['bank_code'].nunique()} banks")
    build_dashboard(df, OUTPUT_PATH)
    print(f"🌐 Open in browser: {os.path.abspath(OUTPUT_PATH)}")