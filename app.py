"""
TDX 公車 API 壓力測試平台
結合 Streamlit + k6，支援：
  - 單次測試（自訂參數，快速驗證）
  - 符合規格測試（依專案 SLA/SLO 規範自動設定參數）
"""

import streamlit as st
import requests
import subprocess
import json
import os
import tempfile
import time
import threading
import queue
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import yaml

# ─────────────────────────────────────────────────────────
# 0. 載入 .env 與 config.yaml
# ─────────────────────────────────────────────────────────
load_dotenv()

@st.cache_data(ttl=60)
def load_config() -> dict:
    """載入 config.yaml（最多 60 秒快取，修改後 Streamlit 自動 reload）"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

cfg = load_config()

# ─────────────────────────────────────────────────────────
# 1. 頁面設定
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MOTC TDX 壓測平台",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────
# 2. 自訂 CSS 樣式（深色高質感主題）
# ─────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* 頁面背景 */
.stApp {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
    color: #e6edf3;
}

/* 標題樣式 */
.main-title {
    font-size: 2.4rem;
    font-weight: 700;
    background: linear-gradient(90deg, #58a6ff, #79c0ff, #a5f3fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-align: center;
    padding: 1rem 0 0.3rem 0;
    letter-spacing: -0.5px;
}

.main-subtitle {
    text-align: center;
    color: #8b949e;
    font-size: 0.95rem;
    margin-bottom: 1.5rem;
}

/* 卡片樣式 */
.metric-card {
    background: linear-gradient(135deg, #161b22, #21262d);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.2rem;
    margin: 0.3rem;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}

.metric-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #58a6ff, #79c0ff);
    border-radius: 12px 12px 0 0;
}

.metric-card:hover {
    border-color: #58a6ff;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(88, 166, 255, 0.15);
}

.metric-label {
    font-size: 0.78rem;
    color: #8b949e;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 0.4rem;
}

.metric-value {
    font-size: 1.9rem;
    font-weight: 700;
    color: #e6edf3;
    line-height: 1.1;
}

.metric-unit {
    font-size: 0.8rem;
    color: #8b949e;
    margin-left: 3px;
}

/* PASS / FAIL 標籤 */
.badge-pass {
    display: inline-block;
    background: linear-gradient(90deg, #238636, #2ea043);
    color: #fff;
    padding: 0.35rem 1.1rem;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.85rem;
    letter-spacing: 1px;
    box-shadow: 0 0 12px rgba(46, 160, 67, 0.4);
}

.badge-fail {
    display: inline-block;
    background: linear-gradient(90deg, #b91c1c, #dc2626);
    color: #fff;
    padding: 0.35rem 1.1rem;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.85rem;
    letter-spacing: 1px;
    box-shadow: 0 0 12px rgba(220, 38, 38, 0.4);
}

/* 區段標題 */
.section-title {
    font-size: 1.15rem;
    font-weight: 600;
    color: #79c0ff;
    border-left: 3px solid #58a6ff;
    padding-left: 0.75rem;
    margin: 1.2rem 0 0.8rem 0;
}

/* 按鈕美化 */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.25s ease !important;
    letter-spacing: 0.3px !important;
}

.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(88, 166, 255, 0.3) !important;
}

/* SLA 資訊框 */
.sla-info-box {
    background: linear-gradient(135deg, #0d2137, #0c2d48);
    border: 1px solid #1f6feb;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
    font-size: 0.88rem;
    color: #cae8ff;
}

/* Sidebar 美化 */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #161b22, #0d1117) !important;
    border-right: 1px solid #30363d !important;
}

/* 進度條顏色覆寫 */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #58a6ff, #79c0ff) !important;
}

/* tab 美化 */
.stTabs [data-baseweb="tab-list"] {
    background-color: #161b22;
    border-radius: 8px;
    padding: 4px;
    gap: 4px;
    border: 1px solid #30363d;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 6px;
    color: #8b949e;
    font-weight: 500;
}

.stTabs [aria-selected="true"] {
    background-color: #21262d !important;
    color: #58a6ff !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
# 3. 頁面標題
# ─────────────────────────────────────────────────────────
st.markdown('<div class="main-title">🚌 MOTC TDX 壓力測試平台</div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">公共運輸 API SLA/SLO 自動化驗證系統 ｜ Powered by k6 + Streamlit</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
# 4. 側邊欄
# ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔑 TDX 認證設定")
    st.caption("輸入 Client ID & Secret，系統自動取得 OAuth 2.0 Token")

    default_id = os.environ.get("ClientId", "")
    default_secret = os.environ.get("ClientSecret", "")

    client_id = st.text_input("Client ID", value=default_id, type="password", key="cid")
    client_secret = st.text_input("Client Secret", value=default_secret, type="password", key="csec")

    st.divider()
    st.markdown("### 🎯 測試目標 API")

    BASE_URL = cfg["tdx"]["base_url"]
    default_city = cfg["tdx"].get("default_city", "Taipei")
    tra_origin   = cfg["tdx"].get("default_tra_origin", "0900")
    tra_dest     = cfg["tdx"].get("default_tra_dest",   "1000")

    # 從 config.yaml 建立端點選項
    def _resolve_path(raw_path: str) -> str:
        """展開路徑中的 {City}、{OriginStationID}、{DestinationStationID} 佔位符"""
        return (
            raw_path
            .replace("{City}", default_city)
            .replace("{OriginStationID}", tra_origin)
            .replace("{DestinationStationID}", tra_dest)
            .replace("{RouteName}", "0")  # 預設路線名
            .replace("{StationID}", tra_origin)
        )

    endpoint_options = {
        ep["label"]: ep["path"] for ep in cfg["endpoints"]
    }

    selected_label = st.selectbox("選擇 API 端點", list(endpoint_options.keys()), key="ep_select")

    if endpoint_options[selected_label] == "CUSTOM":
        custom_path = st.text_input(
            "輸入相對路徑",
            value="/v3/Bus/Station/City/Taipei",
            placeholder="/v3/Bus/Route/City/Taichung",
            key="custom_path",
        )
        target_path = custom_path.strip()
    else:
        target_path = _resolve_path(endpoint_options[selected_label])

    full_url = f"{BASE_URL}{target_path}"

    st.caption(f"🌐 `{full_url}`")

    st.divider()
    st.markdown("### ℹ️ SLA 規範速查")
    st.markdown("""
    <div class="sla-info-box">
    <b>規格 1：靜/動態資料 ≤ 20Kbit</b><br>
    → 5,000 VU ｜ 每 5 秒一次 ｜ 連續 1 小時<br>
    → 平均回應時間 &lt; 3 秒<br><br>
    <b>規格 2：其它 API 服務</b><br>
    → 500 VU ｜ 平均回應時間 &lt; 3 秒
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
# 5. 核心函式
# ─────────────────────────────────────────────────────────

def get_tdx_token(c_id: str, c_secret: str) -> str | None:
    """向 TDX 申請 OAuth 2.0 Bearer Token"""
    auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    try:
        resp = requests.post(
            auth_url,
            headers={"content-type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "client_id": c_id, "client_secret": c_secret},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        st.error(f"❌ 取得 Token 失敗：{e}")
        return None


def generate_k6_script(
    target_url: str,
    vus: int,
    duration: str,
    sleep_sec: float,
    size_limit_kbit: int | None,
    ramp_up_duration: str = "30s",
    ramp_down_duration: str = "10s",
) -> str:
    """動態生成 k6 壓測腳本（ramping-vus + jitter 緩啟動）"""
    size_check = ""
    if size_limit_kbit:
        max_bytes = (size_limit_kbit * 1000) // 8
        size_check = f",\n    'Response <= {size_limit_kbit}Kbit': (r) => r.body && r.body.length <= {max_bytes}"

    # jitter：sleep 加入 ±20% 隨機誤差，讓請求更分散避免同時間點衝擊
    if sleep_sec > 0:
        jitter_max = round(sleep_sec * 0.2, 3)
        sleep_block = (
            f"  // sleep + \u00b120% jitter \u8b93\u8acb\u6c42\u5206\u6563\n"
            f"  sleep({sleep_sec} + (Math.random() * {jitter_max * 2} - {jitter_max}));"
        )
    else:
        sleep_block = ""

    return f"""
import http from 'k6/http';
import {{ check, sleep }} from 'k6';

// ─── Ramp-up 說明 ────────────────────────────────────────────────────
// 1. Ramp-up  ({ramp_up_duration}): VU 從 0 線性爸到 {vus}，避免瞬間衝擊
// 2. Steady   ({duration}): 維持 {vus} VU 全速壓測
// 3. Ramp-down({ramp_down_duration}): VU 緩降到 0，讓伺服器恢復
// ─────────────────────────────────────────────────────
export const options = {{
  scenarios: {{
    tdx_test: {{
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        {{ duration: '{ramp_up_duration}',   target: {vus}  }},
        {{ duration: '{duration}',            target: {vus}  }},
        {{ duration: '{ramp_down_duration}',  target: 0      }},
      ],
      gracefulRampDown: '10s',
    }},
  }},
  thresholds: {{
    http_req_duration: ['avg<3000'],
    http_req_failed: ['rate<0.01'],
  }},
}};

export default function () {{
  const params = {{
    headers: {{
      'Authorization': 'Bearer ' + __ENV.TDX_TOKEN,
      'Accept': 'application/json',
      'Accept-Encoding': 'gzip',
    }},
  }};
  const res = http.get('{target_url}', params);
  const ok = check(res, {{
    'HTTP 200': (r) => r.status === 200{size_check}
  }});

  if (!ok && __ITER < 5) {{
    console.error(`[ERR] HTTP ${{res.status}} | URL: {target_url} | Body: ${{res.body ? res.body.substring(0, 150) : ''}}`);
  }}
{sleep_block}
}}

export function handleSummary(data) {{
  return {{ 'summary.json': JSON.stringify(data) }};
}}
"""


def run_k6_test(script_content: str, token: str, log_queue: queue.Queue) -> tuple:
    """執行 k6 並串流輸出到 log_queue；回傳 (returncode, stdout, stderr, summary_dict)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "test.js")
        summary_path = os.path.join(tmpdir, "summary.json")

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        env = os.environ.copy()
        env["TDX_TOKEN"] = token
        env["K6_NO_USAGE_REPORT"] = "true"

        process = subprocess.Popen(
            ["k6", "run", script_path],
            cwd=tmpdir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        all_output = []
        for line in process.stdout:
            log_queue.put(line.rstrip())
            all_output.append(line)
        process.wait()

        stdout_text = "".join(all_output)
        summary_data = None
        if os.path.exists(summary_path):
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)

        return process.returncode, stdout_text, "", summary_data


def render_results(summary: dict, target_rt_ms: int, size_limit_kbit: int | None, mode_label: str, target_url: str = ""):
    """解析 k6 summary 並呈現測試結果，且自動生成詳細 Markdown 報告與下載按鈕"""
    metrics = summary.get("metrics", {})

    http_reqs     = metrics.get("http_reqs", {}).get("values", {}).get("count", 0)
    req_duration  = metrics.get("http_req_duration", {}).get("values", {})
    req_failed    = metrics.get("http_req_failed", {}).get("values", {})
    data_recv     = metrics.get("data_received", {}).get("values", {}).get("count", 0)
    iterations    = metrics.get("iterations", {}).get("values", {}).get("count", 0)
    vus_max       = metrics.get("vus_max", {}).get("values", {}).get("value", 0)

    avg_rt   = req_duration.get("avg", 0)
    p95_rt   = req_duration.get("p(95)", req_duration.get("pt(95)", 0))
    p90_rt   = req_duration.get("p(90)", req_duration.get("pt(90)", 0))
    min_rt   = req_duration.get("min", 0)
    med_rt   = req_duration.get("med", 0)
    max_rt   = req_duration.get("max", 0)
    fail_rate = req_failed.get("rate", 0) * 100
    data_mb  = data_recv / 1024 / 1024
    avg_bytes_per_req = (data_recv / http_reqs) if http_reqs > 0 else 0
    avg_kbit = avg_bytes_per_req * 8 / 1000

    # ── KPI Cards ──────────────────────────────────────────
    st.markdown('<p class="section-title">📊 核心效能指標</p>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    cards = [
        (c1, "總請求次數", f"{int(http_reqs):,}", "次"),
        (c2, "平均回應時間", f"{avg_rt:.1f}", "ms"),
        (c3, "P95 回應時間", f"{p95_rt:.1f}", "ms"),
        (c4, "錯誤率", f"{fail_rate:.2f}", "%"),
        (c5, "已接收資料量", f"{data_mb:.2f}", "MB"),
    ]
    for col, label, value, unit in cards:
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}<span class="metric-unit">{unit}</span></div>
            </div>
            """, unsafe_allow_html=True)

    # ── SLA 判定 ───────────────────────────────────────────
    st.markdown('<p class="section-title">🏛️ SLA/SLO 判定結果</p>', unsafe_allow_html=True)

    is_rt_pass    = avg_rt <= target_rt_ms
    is_error_pass = fail_rate < 1.0
    size_pass     = (avg_kbit <= size_limit_kbit) if size_limit_kbit else True
    overall_pass  = is_rt_pass and is_error_pass and size_pass

    col_v, col_i = st.columns([1, 2])
    with col_v:
        if overall_pass:
            st.markdown('<span class="badge-pass">✅ PASS</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="badge-fail">❌ FAIL</span>', unsafe_allow_html=True)
        st.caption(f"測試模式：{mode_label}")

    with col_i:
        rows = [
            ("平均回應時間 (Avg RT)", f"{avg_rt:.2f} ms", f"< {target_rt_ms} ms", "✅" if is_rt_pass else "❌"),
            ("請求錯誤率", f"{fail_rate:.2f}%", "< 1%", "✅" if is_error_pass else "❌"),
        ]
        if size_limit_kbit:
            rows.append((f"平均 Payload 大小", f"{avg_kbit:.2f} Kbit", f"<= {size_limit_kbit} Kbit", "✅" if size_pass else "❌"))

        df = pd.DataFrame(rows, columns=["指標", "實測值", "門檻", "結果"])
        st.dataframe(df, hide_index=True, use_container_width=True)

    # ── 詳細回應時間表 ─────────────────────────────────────
    with st.expander("🔍 完整回應時間分布"):
        rt_df = pd.DataFrame({
            "指標": ["Min", "Avg (平均)", "Med (p50)", "p90", "p95", "Max"],
            "時間 (ms)": [
                f"{min_rt:.2f}",
                f"{avg_rt:.2f}",
                f"{med_rt:.2f}",
                f"{p90_rt:.2f}",
                f"{p95_rt:.2f}",
                f"{max_rt:.2f}",
            ],
        })
        st.table(rt_df)

    # ── 快速統計 ───────────────────────────────────────────
    with st.expander("📋 完整測試統計"):
        st.markdown(f"""
        | 項目 | 數值 |
        |------|------|
        | 最大 VU 數 | {int(vus_max):,} |
        | 總 Iteration 數 | {int(iterations):,} |
        | 總請求次數 | {int(http_reqs):,} |
        | 已接收資料量 | {data_mb:.3f} MB |
        | 平均每次 Payload | {avg_bytes_per_req/1024:.2f} KB ({avg_kbit:.2f} Kbit) |
        """)

    # ── 產生 Markdown 測試報告 ─────────────────────────────────────
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_filename = f"TDX_LoadTest_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    # 失敗原因列表
    failure_reasons = []
    if not is_rt_pass:
        failure_reasons.append(f"- ❌ **平均回應時間過高**：實測 `{avg_rt:.2f} ms`（要求 `< {target_rt_ms} ms`）")
    if not is_error_pass:
        failure_reasons.append(f"- ❌ **請求錯誤率過高**：實測 `{fail_rate:.2f}%`（要求 `< 1%`）")
    if size_limit_kbit and not size_pass:
        failure_reasons.append(f"- ❌ **Payload 大小超標**：實測 `{avg_kbit:.2f} Kbit`（要求 `<= {size_limit_kbit} Kbit`）")

    if not overall_pass:
        failure_analysis_md = f"""## 🚨 測試失敗根因分析 (Failure Analysis)

### 關鍵死因：
{chr(10).join(failure_reasons)}

### 💡 除錯與診斷指引：
1. **HTTP Error (狀態碼非 200)**：
   - **401 Unauthorized / 403 Forbidden**：Client ID 或 Secret 無效，或 Token 授權範圍不包含該 API。
   - **404 Not Found**：請求路徑錯誤（如版本號 `/v2/` 與 `/v3/` 錯置，或缺少子路徑）。
   - **400 Bad Request**：缺少必要的 Query/Path 參數，或預設值無效。
   - **429 Too Many Requests**：已觸發伺服器流量限流機制。
2. **回應時間過長**：
   - 數據量過大，或資料庫查詢效能不足，建議檢查端點是否有 `$top` 限流或啟用 Gzip 壓縮。
"""
    else:
        failure_analysis_md = """## 🎉 合規性驗證分析 (Success Analysis)

- **回應時間**：符合 SLA 規範（低於門檻）。
- **請求成功率**：高達 99% 以上，連線穩定。
- **Payload 限制**：符合預期頻寬規範。
"""

    url_info = f"`{target_url}`" if target_url else "未指定"

    report_md = f"""# 🚌 TDX API 壓力測試報告 (Load Test Report)

- **報告生成時間**：{now_str}
- **測試模式**：{mode_label}
- **測試目標端點**：{url_info}
- **整體結果判定**：**{"✅ PASS" if overall_pass else "❌ FAIL"}**

---

## 📊 核心效能指標 summary

| 指標名稱 | 實測數值 | SLA / SLO 門檻規範 | 單項判定 |
|---------|---------|------------------|---------|
| **平均回應時間 (Avg RT)** | **{avg_rt:.2f} ms** | `< {target_rt_ms} ms` | {"✅ PASS" if is_rt_pass else "❌ FAIL"} |
| **P95 回應時間** | **{p95_rt:.2f} ms** | - | - |
| **請求錯誤率 (Fail Rate)** | **{fail_rate:.2f}%** | `< 1.0%` | {"✅ PASS" if is_error_pass else "❌ FAIL"} |
| **平均 Payload 大小** | **{avg_kbit:.2f} Kbit** | {f"<= {size_limit_kbit} Kbit" if size_limit_kbit else "無限制"} | {("✅ PASS" if size_pass else "❌ FAIL") if size_limit_kbit else "N/A"} |
| **總請求數 (Total Reqs)** | {int(http_reqs):,} 次 | - | - |
| **最大併發數 (Max VUs)** | {int(vus_max):,} VU | - | - |
| **總接收資料量** | {data_mb:.3f} MB | - | - |

---

## 🔍 詳細回應時間百分位數 (Percentiles)

- **Min (最小值)**：{min_rt:.2f} ms
- **Med / P50 (中位數)**：{med_rt:.2f} ms
- **P90**：{p90_rt:.2f} ms
- **P95**：{p95_rt:.2f} ms
- **Max (最大值)**：{max_rt:.2f} ms

---

{failure_analysis_md}

---
*Report generated automatically by MOTC TDX Load Testing Platform*
"""

    st.markdown("---")
    st.markdown("### 📥 下載測試報告")
    c_dl, c_pv = st.columns([1, 3])
    with c_dl:
        st.download_button(
            label="📝 下載 Markdown 報告 (.md)",
            data=report_md,
            file_name=report_filename,
            mime="text/markdown",
            type="primary",
            use_container_width=True,
        )

    with st.expander("📄 預覽完整 Markdown 報告"):
        st.code(report_md, language="markdown")


# ─────────────────────────────────────────────────────────
# 6. 主要頁面邏輯
# ─────────────────────────────────────────────────────────

st.markdown("---")

tab_single, tab_sla = st.tabs(["🧪 單次測試", "📋 符合規格測試（SLA/SLO）"])

# ══════════════════════════════════════════════════════════
# Tab 1：單次測試
# ══════════════════════════════════════════════════════════
with tab_single:
    st.markdown('<p class="section-title">🧪 單次測試 — 自訂參數</p>', unsafe_allow_html=True)
    st.caption("快速驗證 API 可用性，自由調整所有壓測參數。")

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        s_vus = st.number_input("併發人數 (VUs)", min_value=1, max_value=10000, value=10, key="s_vus")
    with sc2:
        s_duration = st.text_input("測試時長", value="30s", help="支援 30s / 5m / 1h 格式", key="s_dur")
    with sc3:
        s_sleep = st.number_input("請求間隔 (秒)", min_value=0.0, max_value=60.0, value=1.0, step=0.5, key="s_sleep")

    s_size_limit = st.checkbox("啟用 Payload 大小限制（20 Kbit）", value=False, key="s_size")

    st.markdown("")  # 空行

    if st.button("🚀 開始單次測試", type="primary", use_container_width=True, key="btn_single"):
        if not client_id or not client_secret:
            st.warning("⚠️ 請先在左側邊欄填入 Client ID 與 Client Secret！")
        else:
            log_q: queue.Queue = queue.Queue()
            result_holder: dict = {}

            # Step 1: 取得 Token
            with st.spinner("🔐 取得 TDX OAuth Token..."):
                token = get_tdx_token(client_id, client_secret)

            if token:
                st.success("✅ Token 取得成功！")

                # Step 2: 執行壓測
                _sd = cfg.get('single_test_defaults', {})
                script = generate_k6_script(
                    full_url, s_vus, s_duration, s_sleep,
                    20 if s_size_limit else None,
                    ramp_up_duration=_sd.get('ramp_up_duration', '10s'),
                    ramp_down_duration='10s',
                )

                log_placeholder = st.empty()
                status_bar = st.progress(0, text="⏳ k6 測試執行中...")

                log_lines: list[str] = []

                def _run():
                    rc, out, err, smry = run_k6_test(script, token, log_q)
                    result_holder.update({"rc": rc, "out": out, "err": err, "summary": smry})

                thread = threading.Thread(target=_run, daemon=True)
                thread.start()

                start_ts = time.time()
                # 嘗試解析 duration 為秒
                try:
                    if s_duration.endswith("h"):
                        total_secs = int(s_duration[:-1]) * 3600
                    elif s_duration.endswith("m"):
                        total_secs = int(s_duration[:-1]) * 60
                    elif s_duration.endswith("s"):
                        total_secs = int(s_duration[:-1])
                    else:
                        total_secs = 30
                except Exception:
                    total_secs = 30

                while thread.is_alive():
                    while not log_q.empty():
                        log_lines.append(log_q.get_nowait())
                    elapsed = time.time() - start_ts
                    pct = min(elapsed / total_secs, 0.99) if total_secs > 0 else 0.5
                    status_bar.progress(pct, text=f"⏳ 執行中… {elapsed:.0f}s / ~{total_secs}s")
                    log_placeholder.code("\n".join(log_lines[-30:]), language="bash")
                    time.sleep(0.5)

                # 清空剩餘 log
                while not log_q.empty():
                    log_lines.append(log_q.get_nowait())
                log_placeholder.code("\n".join(log_lines[-30:]), language="bash")
                status_bar.progress(1.0, text="✅ 測試完成！")

                # Step 3: 結果呈現
                if result_holder.get("summary"):
                    st.markdown("---")
                    st.markdown("## 📊 測試結果")
                    render_results(
                        result_holder["summary"],
                        target_rt_ms=3000,
                        size_limit_kbit=20 if s_size_limit else None,
                        mode_label="單次自訂測試",
                        target_url=full_url,
                    )
                else:
                    st.error("⚠️ k6 未能輸出摘要 JSON，請確認 k6 已正確安裝。")
                    with st.expander("查看完整輸出"):
                        st.code(result_holder.get("out", ""), language="bash")


# ══════════════════════════════════════════════════════════
# Tab 2：符合規格測試（SLA/SLO）
# ══════════════════════════════════════════════════════════
with tab_sla:
    st.markdown('<p class="section-title">📋 符合規格測試 — SLA/SLO 自動驗證</p>', unsafe_allow_html=True)
    st.caption("依照專案規格書自動設定壓測參數，測試完成後自動輸出 PASS/FAIL 判定。")

    # ── 從 config.yaml 讀取 SLA 情境 ──────────────────────
    _sla1 = cfg["sla"]["sla1"]
    _sla2 = cfg["sla"]["sla2"]

    sla_option = st.radio(
        "選擇驗證情境",
        [_sla1["label"], _sla2["label"]],
        key="sla_choice",
    )

    if sla_option == _sla1["label"]:
        sla_vus      = _sla1["vus"]
        sla_duration = _sla1["duration"]
        sla_sleep    = _sla1["sleep_sec"]
        sla_size     = _sla1["payload_limit_kbit"]
        sla_rt_ms    = _sla1["avg_rt_threshold_ms"]
        sla_label    = _sla1["label"]
    else:
        sla_vus      = _sla2["vus"]
        sla_duration = _sla2["duration"]
        sla_sleep    = _sla2["sleep_sec"]
        sla_size     = _sla2["payload_limit_kbit"]  # None
        sla_rt_ms    = _sla2["avg_rt_threshold_ms"]
        sla_label    = _sla2["label"]

    st.markdown(f"""
    <div class="sla-info-box">
    <b>📌 此次測試參數：</b><br>
    &bull; 併發人數 (VUs)：<b>{sla_vus:,}</b><br>
    &bull; 測試時長：<b>{sla_duration}</b><br>
    &bull; 請求間隔：<b>{sla_sleep} 秒</b><br>
    &bull; Payload 限制：<b>{"<= 20 Kbit" if sla_size else "無"}</b><br>
    &bull; 平均回應時間門檻：<b>&lt; {sla_rt_ms} ms</b>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")  # 空行

    if st.button("📋 開始符合規格測試", type="primary", use_container_width=True, key="btn_sla"):
        if not client_id or not client_secret:
            st.warning("⚠️ 請先在左側邊欄填入 Client ID 與 Client Secret！")
        else:
            log_q2: queue.Queue = queue.Queue()
            result_holder2: dict = {}

            # Step 1: 取得 Token
            with st.spinner("🔐 取得 TDX OAuth Token..."):
                token2 = get_tdx_token(client_id, client_secret)

            if token2:
                st.success("✅ Token 取得成功！")

                script2 = generate_k6_script(
                    full_url, sla_vus, sla_duration, sla_sleep, sla_size,
                    ramp_up_duration=(_sla1 if sla_option == _sla1['label'] else _sla2).get('ramp_up_duration', '1m'),
                    ramp_down_duration=(_sla1 if sla_option == _sla1['label'] else _sla2).get('ramp_down_duration', '30s'),
                )

                log_placeholder2 = st.empty()
                status_bar2 = st.progress(0, text="⏳ SLA 壓測執行中...")

                log_lines2: list[str] = []

                def _run2():
                    rc, out, err, smry = run_k6_test(script2, token2, log_q2)
                    result_holder2.update({"rc": rc, "out": out, "err": err, "summary": smry})

                thread2 = threading.Thread(target=_run2, daemon=True)
                thread2.start()

                start_ts2 = time.time()
                try:
                    if sla_duration.endswith("h"):
                        total_secs2 = int(sla_duration[:-1]) * 3600
                    elif sla_duration.endswith("m"):
                        total_secs2 = int(sla_duration[:-1]) * 60
                    elif sla_duration.endswith("s"):
                        total_secs2 = int(sla_duration[:-1])
                    else:
                        total_secs2 = 300
                except Exception:
                    total_secs2 = 300

                while thread2.is_alive():
                    while not log_q2.empty():
                        log_lines2.append(log_q2.get_nowait())
                    elapsed2 = time.time() - start_ts2
                    pct2 = min(elapsed2 / total_secs2, 0.99) if total_secs2 > 0 else 0.5
                    status_bar2.progress(pct2, text=f"⏳ 執行中… {elapsed2:.0f}s / ~{total_secs2}s")
                    log_placeholder2.code("\n".join(log_lines2[-30:]), language="bash")
                    time.sleep(0.5)

                while not log_q2.empty():
                    log_lines2.append(log_q2.get_nowait())
                log_placeholder2.code("\n".join(log_lines2[-30:]), language="bash")
                status_bar2.progress(1.0, text="✅ SLA 測試完成！")

                if result_holder2.get("summary"):
                    st.markdown("---")
                    st.markdown("## 📊 SLA 測試結果")
                    render_results(
                        result_holder2["summary"],
                        target_rt_ms=sla_rt_ms,
                        size_limit_kbit=sla_size,
                        mode_label=sla_label,
                        target_url=full_url,
                    )
                else:
                    st.error("⚠️ k6 未能輸出摘要 JSON，請確認 k6 已正確安裝。")
                    with st.expander("查看完整輸出"):
                        st.code(result_holder2.get("out", ""), language="bash")

# ─────────────────────────────────────────────────────────
# 7. 頁尾
# ─────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📖 SLA/SLO 規範備忘錄"):
    st.markdown("""
    ### 專案服務水準目標（SLO）

    | 規格 | 情境 | 併發 | 間隔 | 時長 | 平均 RT 門檻 |
    |------|------|------|------|------|------------|
    | SLA 1 | 靜/動態資料 <= 20Kbit | 5,000 VU | 5 秒 | 1 小時 | < 3 秒 |
    | SLA 2 | 其它 API 服務 | 500 VU | — | — | < 3 秒 |

    > **備註**：依規格書要求，實際驗收測試應在**內網**執行，排除頻寬限制。
    > 外網測試結果僅供參考，正式稽核請於機房環境執行。

    ### k6 安裝指引（Linux）
    ```bash
    sudo gpg --no-default-keyring \\
      --keyring /usr/share/keyrings/k6-archive-keyring.gpg \\
      --keyserver hkp://keyserver.ubuntu.com:80 \\
      --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
    echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
    sudo apt-get update && sudo apt-get install k6
    ```
    """)

st.caption(f"MOTC TDX 壓測平台 | 生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
