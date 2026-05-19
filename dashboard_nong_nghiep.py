import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta, datetime
import time
import random

st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Live Dashboard)")

# --- 1. TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Đang chờ dữ liệu chuẩn...", "#808080"
    if "Cây con" in stage: ideal_min, ideal_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: ideal_min, ideal_max = 0.8, 1.2
    else: ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Tăng nhiệt hoặc giảm ẩm.", "#FF4B4B"
    if ideal_min <= vpd <= ideal_max: return "🟢 LÝ TƯỞNG", "Cây đang phát triển tốt.", "#00C851"
    if vpd > ideal_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng! Giảm nhiệt, tăng ẩm khẩn cấp.", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- 2. BỘ NHỚ TẠM CHO GIẢ LẬP (SESSION STATE) ---
if 'sim_df' not in st.session_state:
    st.session_state.sim_df = pd.DataFrame(columns=['Thời gian', 'STT', 'temp', 'humi', 'VPD'])

# --- 3. XỬ LÝ & LÀM SẠCH DỮ LIỆU TỪ FILE ---
def process_data(file):
    try: df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan 
            if col == 'humi':
                df.loc[(df[col] < 20) | (df[col] > 100), col] = np.nan 
    
    df = df.dropna(subset=['temp', 'humi']).copy()
    if not df.empty: df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- 4. GIAO DIỆN CHÍNH ---
st.sidebar.header("🔴 Chế độ Live (Giả lập)")
sim_mode = st.sidebar.toggle("Bật giả lập dữ liệu (30s/lần)")

uploaded_file = st.sidebar.file_uploader("Hoặc Tải file JSON (Offline)", type=['json'], disabled=sim_mode)

growth_stage = st.sidebar.radio("Giai đoạn:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)

df_valid = pd.DataFrame()

# NẾU BẬT GIẢ LẬP
if sim_mode:
    st.success("Đang trong chế độ Giả lập Realtime. Dữ liệu sẽ tự động làm mới mỗi 30 giây...")
    
    # Sinh dữ liệu ngẫu nhiên
    new_temp = round(random.uniform(22.0, 48.0), 2)
    new_humi = round(random.uniform(35.0, 85.0), 2)
    new_vpd = calculate_vpd(new_temp, new_humi)
    
    new_row = pd.DataFrame([{
        'Thời gian': datetime.now(),
        'STT': 'SIM-01',
        'temp': new_temp,
        'humi': new_humi,
        'VPD': new_vpd
    }])
    
    # Đưa vào bộ nhớ tạm
    st.session_state.sim_df = pd.concat([st.session_state.sim_df, new_row], ignore_index=True)
    # Chỉ giữ lại 30 dòng gần nhất để biểu đồ không bị nén quá nhỏ
    st.session_state.sim_df = st.session_state.sim_df.tail(30)
    
    df_valid = st.session_state.sim_df.copy()

# NẾU KHÔNG BẬT GIẢ LẬP MÀ UP FILE
elif uploaded_file:
    df_valid = process_data(uploaded_file)
    if not df_valid.empty:
        stt_list = ["Tất cả"] + sorted(df_valid['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_valid = df_valid[df_valid['STT'] == sel_stt]

# --- 5. HIỂN THỊ DỮ LIỆU & BIỂU ĐỒ ---
if not df_valid.empty:
    last = df_valid.iloc[-1]
    status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
    
    st.subheader(f"📍 Thông báo trạng thái (Cập nhật lúc: {last['Thời gian'].strftime('%H:%M:%S')})")
    col1, col2, col3 = st.columns([1, 1, 2])
    col1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
    col1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
    
    html_box = f"""
    <div style="padding:20px; border-radius:10px; background-color:{color}; color:white; text-align:center;">
        <span style="font-size:24px; font-weight:bold;">VPD: {last['VPD']} kPa</span><br>
        <span style="font-size:16px;">{status}</span>
    </div>
    """
    col2.markdown(html_box, unsafe_allow_html=True)
    col3.warning(f"**Chỉ đạo vận hành:** {advice}")

    # BIỂU ĐỒ
    st.markdown("---")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
    
    # Dùng chế độ lines+markers cho giả lập để dễ nhìn các chấm 30s
    mode = 'lines+markers' if sim_mode else 'lines'
    
    fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD (kPa)", mode=mode, line=dict(color='green')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)", mode=mode, line=dict(color='red')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)", mode=mode, line=dict(color='blue')), row=2, col=1)
    fig.update_layout(height=500, hovermode="x unified", margin=dict(t=30, b=30))
    st.plotly_chart(fig, use_container_width=True)

    # BẢNG THỐNG KÊ CHI TIẾT
    st.subheader("📋 Lịch sử bản ghi (Cảnh báo: Đỏ nếu < 0.5 hoặc > 1.5 kPa)")
    
    def highlight_vpd(val):
        if pd.isna(val): return ''
        if val < 0.5 or val > 1.5:
            return 'background-color: #ffcccc; color: #990000; font-weight: bold;'
        return ''

    # Sắp xếp từ mới nhất đến cũ nhất
    display_df = df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False)
    # Format lại giờ để bảng hiển thị đẹp
    display_df['Thời gian'] = display_df['Thời gian'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    st.dataframe(
        display_df.style.map(highlight_vpd, subset=['VPD']),
        use_container_width=True,
        hide_index=True
    )
else:
    if not sim_mode:
        st.info("👈 Vui lòng bật chế độ Giả Lập hoặc tải file JSON lên để bắt đầu.")

# --- 6. VÒNG LẶP RERUN CHO CHẾ ĐỘ LIVE ---
if sim_mode:
    time.sleep(30)
    st.rerun()
