import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Analytics Pro", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Chốt)")

# --- 2. HÀM TÍNH TOÁN VPD & CHẨN ĐOÁN ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or temp <= 0: return 0.0
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_status_ui(vpd, stage):
    if "Cây con" in stage: i_min, i_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
    else: i_min, i_max = 1.2, 1.5
    
    if vpd < i_min - 0.2: return "🔵 THẤP", "Nguy cơ nấm bệnh!", "#3498db"
    if i_min <= vpd <= i_max: return "🟢 LÝ TƯỞNG", "Cây phát triển tốt.", "#2ecc71"
    return "🔴 CAO", "Stress nhiệt nặng!", "#e74c3c"

# --- 3. THANH ĐIỀU KHIỂN (SIDEBAR) ---
with st.sidebar:
    st.header("📂 Nạp Dữ Liệu")
    uploaded_file = st.file_uploader("Chọn file JSON (Dữ liệu thật)", type=['json'])
    
    st.divider()
    st.header("🌱 Cấu Hình Cây Trồng")
    stage = st.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
    
    st.divider()
    st.write("✅ Đã khử lỗi Mixed Timezone")
    st.write("✅ Đã khử lỗi Sensor lỏ (>150°C)")

# --- 4. XỬ LÝ DỮ LIỆU TỪ FILE ---
if uploaded_file is not None:
    try:
        # Đọc file 13MB
        df_raw = pd.read_json(uploaded_file)
        
        # Tự động tìm cột (Mapping)
        t_col = next((c for c in df_raw.columns if any(k in c.lower() for k in ['temp', 'nhiệt', 't_kk'])), None)
        h_col = next((c for c in df_raw.columns if any(k in c.lower() for k in ['humi', 'ẩm', 'h_kk'])), None)
        time_col = next((c for c in df_raw.columns if any(k in c.lower() for k in ['thời', 'time', 'date'])), None)
        stt_col = next((c for c in df_raw.columns if 'STT' in c or 'Trạm' in c), None)

        if t_col and h_col:
            # Ép kiểu và làm sạch
            df_raw['temp'] = pd.to_numeric(df_raw[t_col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            df_raw['humi'] = pd.to_numeric(df_raw[h_col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            # Sửa lỗi sensor nhảy số (331 -> 33.1)
            df_raw.loc[df_raw['temp'] > 150, 'temp'] = df_raw['temp'] / 10
            df = df_raw[(df_raw['temp'] > 5) & (df_raw['temp'] < 60)].copy()

            # FIX LỖI MIXED TIMEZONE TẠI ĐÂY
            if time_col:
                df['Thời gian'] = pd.to_datetime(df[time_col], errors='coerce', utc=True).dt.tz_localize(None)
                df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')

            # Tính VPD
            df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)

            # Lọc theo Trạm (Nếu file có nhiều trạm)
            if stt_col:
                stt_list = ["Tất cả"] + sorted(df[stt_col].unique().tolist())
                sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
                if sel_stt != "Tất cả":
                    df = df[df[stt_col] == sel_stt]

            # --- 5. HIỂN THỊ DASHBOARD ---
            if not df.empty:
                last = df.iloc[-1]
                label, advice, color = get_status_ui(last['VPD'], stage)

                # Hàng 1: Thẻ chỉ số
                c1, c2, c3 = st.columns([1, 1, 2])
                c1.metric("Nhiệt độ", f"{last['temp']} °C")
                c1.metric("Độ ẩm", f"{last['humi']} %")
                
                # Thẻ VPD trung tâm
                vpd_box = f"<div style='background-color:{color}; color:white; padding:20px; border-radius:15px; text-align:center;'><h2 style='margin:0; font-size:35px;'>{last['VPD']} kPa</h2><p style='margin:0; font-weight:bold;'>{label}</p></div>"
                c2.markdown(vpd_box, unsafe_allow_html=True)
                c3.warning(f"**Hướng dẫn:** {advice}")

                # Hàng 2: Biểu đồ
                st.subheader("📈 Biểu đồ lịch sử")
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
                fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['VPD'], name="VPD", line=dict(color='green', width=2)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['temp'], name="Nhiệt độ", line=dict(color='red')), row=2, col=1)
                fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['humi'], name="Độ ẩm", line=dict(color='blue')), row=2, col=1)
                fig.update_layout(height=500, hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)

                # Hàng 3: Bảng dữ liệu
                st.subheader("📋 Chi tiết bản ghi")
                df_table = df[['Thời gian', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False)
                df_table['Thời gian'] = df_table['Thời gian'].dt.strftime('%Y-%m-%d %H:%M:%S')
                st.dataframe(df_table, use_container_width=True, hide_index=True)
            else:
                st.warning("Không có dữ liệu cho trạm này.")

        else:
            st.error("Không tìm thấy cột Nhiệt độ/Độ ẩm. Kiểm tra lại file JSON!")
            
    except Exception as e:
        st.error(f"Lỗi: {e}")
else:
    st.info("👆 Nhét file JSON vào thanh bên để hiển thị dữ liệu.")

