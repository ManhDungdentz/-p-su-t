import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
import random

# --- CẤU HÌNH ---
st.set_page_config(page_title="Greenhouse Dashboard", layout="wide")

# --- CSS TÙY CHỈNH CHO GIAO DIỆN DỄ DÙNG ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- HÀM TÍNH TOÁN ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return 0.0
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_status_ui(vpd, stage):
    if "Cây con" in stage: i_min, i_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
    else: i_min, i_max = 1.2, 1.5
    
    if vpd < i_min - 0.2: return "🔵 THẤP", "Nguy cơ nấm!", "#3498db"
    if i_min <= vpd <= i_max: return "🟢 LÝ TƯỞNG", "Cây khỏe mạnh.", "#2ecc71"
    return "🔴 CAO", "Stress nhiệt!", "#e74c3c"

# --- SIDEBAR: CHỖ NHÉT FILE VÀ CÀI ĐẶT ---
with st.sidebar:
    st.title("⚙️ Điều khiển")
    
    # 1. KHU VỰC TẢI FILE (LUÔN HIỆN)
    st.subheader("📂 Dữ liệu đầu vào")
    uploaded_file = st.file_uploader("Nhét file JSON vào đây 👇", type=['json'])
    
    st.divider()
    
    # 2. KHU VỰC GIẢ LẬP
    sim_on = st.toggle("🚀 Chế độ Giả lập Realtime", value=False)
    
    if sim_on:
        st.info("Đang tự sinh số liệu...")
        off_t = st.slider("Bù Nhiệt độ", -5.0, 5.0, 0.0)
        off_h = st.slider("Bù Độ ẩm", -10.0, 10.0, 0.0)
    
    st.divider()
    stage = st.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)

# --- XỬ LÝ DỮ LIỆU ---
df = pd.DataFrame()

# Ưu tiên lấy dữ liệu từ file nếu có
if uploaded_file is not None:
    try:
        raw_data = pd.read_json(uploaded_file)
        # Giả sử file có cột 'temp' và 'humi' (hoặc bạn tự đổi tên theo file thật)
        df = raw_data.copy()
        if 'VPD' not in df.columns:
            df['VPD'] = df.apply(lambda r: calculate_vpd(r.get('temp', 25), r.get('humi', 70)), axis=1)
        st.sidebar.success("Đã nạp file thành công!")
    except Exception as e:
        st.sidebar.error(f"File lỗi: {e}")

# Nếu bật giả lập và không có file
elif sim_on:
    if 'sim_store' not in st.session_state:
        st.session_state.sim_store = pd.DataFrame(columns=['Thời gian', 'temp', 'humi', 'VPD'])
    
    # Tạo số liệu ngẫu nhiên mượt mà
    prev_t = st.session_state.sim_store.iloc[-1]['temp'] if not st.session_state.sim_store.empty else 26.0
    prev_h = st.session_state.sim_store.iloc[-1]['humi'] if not st.session_state.sim_store.empty else 75.0
    
    new_t = round(prev_t + random.uniform(-0.3, 0.3), 1)
    new_h = round(prev_h + random.uniform(-1, 1), 1)
    new_v = calculate_vpd(new_t, new_h)
    
    new_row = pd.DataFrame([{'Thời gian': datetime.now(), 'temp': new_t, 'humi': new_h, 'VPD': new_v}])
    st.session_state.sim_store = pd.concat([st.session_state.sim_store, new_row], ignore_index=True).tail(20)
    df = st.session_state.sim_store

# --- GIAO DIỆN CHÍNH ---
st.header("🌿 Giám sát Vi khí hậu Nhà kính")

if not df.empty:
    last = df.iloc[-1]
    label, advice, color = get_status_ui(last['VPD'], stage)
    
    # Hàng 1: Chỉ số chính
    col1, col2, col3 = st.columns(3)
    col1.metric("Nhiệt độ", f"{last.get('temp', 0)} °C")
    col2.metric("Độ ẩm", f"{last.get('humi', 0)} %")
    
    # Box VPD trung tâm
    with col3:
        st.markdown(f"""
            <div style="background-color:{color}; color:white; padding:15px; border-radius:10px; text-align:center;">
                <h2 style="margin:0;">{last['VPD']} kPa</h2>
                <p style="margin:0; font-weight:bold;">{label}</p>
            </div>
        """, unsafe_allow_html=True)

    st.info(f"💡 **Lời khuyên:** {advice}")

    # Hàng 2: Biểu đồ
    st.subheader("📈 Xu hướng")
    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(go.Scatter(x=df.index if 'Thời gian' not in df.columns else df['Thời gian'], 
                             y=df['VPD'], name="VPD", line=dict(color=color, width=4)))
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Hàng 3: Bảng dữ liệu
    st.subheader("📋 Chi tiết bản ghi")
    st.dataframe(df.iloc[::-1], use_container_width=True)

    if sim_on and uploaded_file is None:
        time.sleep(30)
        st.rerun()
else:
    st.warning("⚠️ Chưa có dữ liệu. Vui lòng **Tải file JSON** hoặc **Bật giả lập** ở thanh bên trái!")
