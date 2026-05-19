import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

st.set_page_config(page_title="Greenhouse Monitoring", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

# --- 1. HÀM TÍNH TOÁN VPD CHUẨN ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    # Áp suất hơi bão hòa
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    # Áp suất hơi thực tế
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Đang chờ dữ liệu...", "#808080"
    if "Cây con" in stage: ideal_min, ideal_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: ideal_min, ideal_max = 0.8, 1.2
    else: ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Tăng nhiệt hoặc giảm ẩm.", "#FF4B4B"
    if ideal_min <= vpd <= ideal_max: return "🟢 LÝ TƯỞNG", "Cây đang phát triển tốt.", "#00C851"
    if vpd > ideal_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng! Giảm nhiệt, tăng ẩm khẩn cấp.", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- 2. XỬ LÝ DỮ LIỆU (LỌC BỎ SỐ LỎ) ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Nhận diện cột nhiệt độ và độ ẩm (hỗ trợ cả tempKK/humiKK)
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            if col == 'temp':
                # Sửa lỗi hiển thị sai đơn vị hoặc nhân 10
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                # LOẠI BỎ NHIỆT ĐỘ VÔ LÝ (> 55 ĐỘ)
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan 
                
            if col == 'humi':
                # LOẠI BỎ ĐỘ ẨM LỖI (< 20% HOẶC > 100%)
                df.loc[(df[col] < 20) | (df[col] > 100), col] = np.nan 
    
    # Xóa bỏ các dòng dữ liệu rác để biểu đồ và bảng thống kê chuẩn xác
    df = df.dropna(subset=['temp', 'humi']).copy()
    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    
    return df

# --- 3. GIAO DIỆN ---
uploaded_file = st.sidebar.file_uploader("Tải file JSON dữ liệu", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # Danh mục tháng hiện có
        st.sidebar.subheader("📅 Dữ liệu hiện có")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        st.sidebar.table(df.groupby('Tháng').size().reset_index(name='Số bản ghi'))

        # Bộ lọc thời gian
        st.sidebar.header("🔍 Bộ lọc")
        filter_mode = st.sidebar.radio("Xem theo:", ["Tất cả", "Tháng cụ thể", "Khoảng ngày"])
        
        if filter_mode == "Tháng cụ thể":
            sel_m = st.sidebar.multiselect("Chọn tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
            df_work = df[df['Tháng'].isin(sel_m)].copy()
        elif filter_mode == "Khoảng ngày":
            c1, c2 = st.sidebar.columns(2)
            start = pd.to_datetime(c1.date_input("Từ ngày", df['Thời gian'].min()))
            end = pd.to_datetime(c2.date_input("Đến ngày", df['Thời gian'].max())) + timedelta(days=1)
            df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
        else:
            df_work = df.copy()

        # Chọn giai đoạn và trạm
        growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        # HIỂN THỊ THÔNG BÁO HIỆN TẠI
        if not df_work.empty:
            last = df_work.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            st.subheader("📍 Trạng thái vận hành hiện tại")
            col1, col2, col3 = st.columns([1, 1, 2])
            col1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            col1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            # Khung thông báo VPD
            html_box = f"""
            <div style="padding:20px; border-radius:10px; background-color:{color}; color:white; text-align:center;">
                <span style="font-size:24px; font-weight:bold;">VPD: {last['VPD']} kPa</span><br>
                <span style="font-size:16px;">{status}</span>
            </div>
            """
            col2.markdown(html_box, unsafe_allow_html=True)
            col3.info(f"**Chỉ đạo:** {advice}")

            # BIỂU ĐỒ THEO DÕI
            st.markdown("---")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['VPD'], name="VPD (kPa)", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['temp'], name="Nhiệt độ (°C)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['humi'], name="Độ ẩm (%)"), row=2, col=1)
            fig.update_layout(height=500, hovermode="x unified", title_text="Biểu đồ thông số nhà kính")
            st.plotly_chart(fig, use_container_width=True)

            # BẢNG DỮ LIỆU
            st.subheader("📋 Bảng Thông Số Chi Tiết (Đã lọc lỗi)")
            # Tóm tắt số liệu chuẩn
            summary = df_work[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2)
            summary.index = ['Cao nhất', 'Thấp nhất', 'Trung bình']
            st.table(summary)
            
            st.dataframe(df_work[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False), use_container_width=True)
        else:
            st.warning("Không tìm thấy dữ liệu hợp lệ trong khoảng này.")
else:
    st.info("👈 Vui lòng tải file JSON lên để bắt đầu giám sát.")
