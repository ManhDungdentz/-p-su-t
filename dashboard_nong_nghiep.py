import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

# --- 1. HÀM TÍNH TOÁN VPD (Có cộng thêm sai số bù trừ) ---
def calculate_vpd(temp, humi, t_offset, h_offset):
    # Áp dụng sai số bù trừ vào giá trị đo được
    t_final = temp + t_offset
    h_final = humi + h_offset
    
    # Giới hạn độ ẩm không quá 100% và không dưới 0%
    h_final = max(min(h_final, 100), 0.1)
    
    if pd.isna(t_final) or pd.isna(h_final): return None
    vpsat = 0.61078 * np.exp((17.27 * t_final) / (t_final + 237.3))
    vpair = vpsat * (h_final / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Thiếu dữ liệu", "#808080"
    if "Cây con" in stage: ideal_min, ideal_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: ideal_min, ideal_max = 0.8, 1.2
    else: ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Tăng nhiệt hoặc giảm ẩm.", "#FF4B4B"
    if ideal_min <= vpd <= ideal_max: return "🟢 LÝ TƯỞNG", "Cây đang phát triển tốt.", "#00C851"
    if vpd > ideal_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng! Giảm nhiệt, tăng ẩm khẩn cấp.", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- 2. XỬ LÝ DỮ LIỆU ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp_raw'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi_raw'] = df[h_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp_raw', 'humi_raw']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp_raw':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[df[col] > 60, col] = np.nan
    
    if 'humi_raw' in df.columns:
        df = df[(df['humi_raw'] > 0) & (df['humi_raw'] <= 100)].copy()
    
    return df

# --- 3. GIAO DIỆN CHÍNH ---
uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # --- PHẦN SAI SỐ (OFFSET) MỚI THÊM ---
        st.sidebar.markdown("---")
        st.sidebar.header("🛠️ Hiệu chỉnh sai số (Offset)")
        t_err = st.sidebar.slider("Sai số Nhiệt độ (°C)", -0.4, 0.4, 0.0, step=0.1)
        h_err = st.sidebar.slider("Sai số Độ ẩm (%)", -5.0, 5.0, 0.0, step=0.5)
        st.sidebar.caption("Gợi ý: Nếu cảm biến báo cao hơn thực tế, hãy kéo về số âm.")

        # LỌC DỮ LIỆU
        st.sidebar.markdown("---")
        growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        
        stt_list = ["Tất cả"] + sorted(df['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        df_filtered = df if sel_stt == "Tất cả" else df[df['STT'] == sel_stt]

        # Áp dụng tính toán với sai số đã chọn
        df_filtered['temp'] = df_filtered['temp_raw'] + t_err
        df_filtered['humi'] = df_filtered['humi_raw'] + h_err
        df_filtered['VPD'] = df_filtered.apply(lambda r: calculate_vpd(r['temp_raw'], r['humi_raw'], t_err, h_err), axis=1)

        # HIỂN THỊ
        if not df_filtered.empty:
            last = df_filtered.dropna(subset=['VPD']).iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            st.subheader(f"📍 Trạng thái hiện tại (Bù sai số: {t_err}°C / {h_err}%)")
            c1, c2, c3 = st.columns([1, 1, 2])
            c1.metric("Nhiệt độ hiệu chỉnh", f"{round(last['temp'], 2)} °C")
            c1.metric("Độ ẩm hiệu chỉnh", f"{round(last['humi'], 1)} %")
            c2.markdown(f"<div style='padding:15px; border-radius:10px; background-color:{color}; color:white; text-align:center; font-size:18px;'><b>VPD: {last['VPD']} kPa</b><br><small>{status}</small></div>", unsafe_allow_html=True)
            c3.info(f"**Hướng dẫn:** {advice}")

            # BIỂU ĐỒ
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_filtered['Thời gian'], y=df_filtered['VPD'], name="VPD", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_filtered['Thời gian'], y=df_filtered['temp'], name="Nhiệt độ (Đã bù)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_filtered['Thời gian'], y=df_filtered['humi'], name="Độ ẩm (Đã bù)"), row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("📋 Chi tiết bản ghi (Sau khi bù sai số)")
            st.dataframe(df_filtered[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False), use_container_width=True)
