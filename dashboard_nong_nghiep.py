import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.parse

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Dashboard Pro", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Full Version)")

# --- HÀM TÍNH VPD ---
# Công thức: VPD = VPsat - VPair
# Trong đó VPsat = 0.61078 * exp((17.27 * T) / (T + 237.3))
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Chờ dữ liệu...", "#808080"
    # Ngưỡng lý tưởng tùy theo giai đoạn cây trồng
    if "Cây con" in stage: i_min, i_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
    else: i_min, i_max = 1.2, 1.5
    
    if vpd < i_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh cao!", "#FF4B4B"
    if i_min <= vpd <= i_max: return "🟢 LÝ TƯỞNG", "Cây phát triển tốt.", "#00C851"
    if vpd > i_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng, cháy lá!", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CANH BAO GREENHOUSE: {status}"
        body = f"Thong so hien tai:\nVPD: {vpd} kPa\nNhiet do: {temp}C\nDo am: {humi}%\nKiem tra ngay!"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except: return False

# --- XỬ LÝ DỮ LIỆU FILE JSON ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()
    
    # Xử lý cột thời gian
    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Ưu tiên cột tempKK và humiKK (Dữ liệu không khí)
    t_cols = [c for c in ['tempKK', 'Nhiệt Độ'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['humiKK', 'Độ ẩm'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
    
    # Ép kiểu số và xử lý nhiễu
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
            if col == 'humi':
                df.loc[(df[col] < 5) | (df[col] > 100), col] = np.nan 
                
    df = df.dropna(subset=['temp', 'humi']).copy()
    if not df.empty: 
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- SIDEBAR: CẤU HÌNH & BỘ LỌC ---
with st.sidebar:
    st.header("⚙️ Cấu hình")
    with st.expander("📧 Email & SMS"):
        u_mail = st.text_input("Gmail gửi:")
        u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
        t_mail = st.text_input("Gmail nhận:")
        target_phone = st.text_input("SĐT nhận SMS:", value="0359029742") # SĐT từ image_0ae12d
        
    uploaded_file = st.file_uploader("📁 Tải file JSON quan trắc (13.6MB)", type=['json'])

# --- CHƯƠNG TRÌNH CHÍNH ---
if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # Bộ lọc Sidebar
        st.sidebar.divider()
        st.sidebar.header("🔍 Bộ lọc dữ liệu")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        
        filter_mode = st.sidebar.radio("Lọc thời gian:", ["Tất cả", "Tháng", "Khoảng ngày"])
        if filter_mode == "Tháng":
            sel_m = st.sidebar.multiselect("Chọn tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
            df_work = df[df['Tháng'].isin(sel_m)].copy()
        elif filter_mode == "Khoảng ngày":
            c1, c2 = st.sidebar.columns(2)
            start = pd.to_datetime(c1.date_input("Từ", df['Thời gian'].min()))
            end = pd.to_datetime(c2.date_input("Đến", df['Thời gian'].max())) + timedelta(days=1)
            df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
        else: df_work = df.copy()

        stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm (STT):", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], stage)
            
            # --- 1. HIỂN THỊ CHỈ SỐ HIỆN TẠI ---
            st.subheader("📍 Chỉ số hiện tại")
            m1, m2, m3 = st.columns([1, 1.2, 1.8])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            html_box = f'<div style="background-color:{color}; padding:15px; border-radius:10px; color:white; text-align:center;"><h3 style="margin:0;">VPD: {last["VPD"]} kPa</h3><b>{status}</b></div>'
            m2.markdown(html_box, unsafe_allow_html=True)
            m3.warning(f"**Chỉ đạo:** {advice}")

            # --- 2. NÚT BẤM CẢNH BÁO ---
            if "🔴" in status:
                cb1, cb2 = st.columns(2)
                with cb1:
                    if st.button("📧 Gửi Gmail Cảnh Báo"):
                        if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                            st.success("✅ Đã gửi Gmail!")
                with cb2:
                    # Link SMS mở ứng dụng điện thoại
                    sms_body = f"CANH BAO: {status}. VPD: {last['VPD']}kPa, T: {last['temp']}C, H: {last['humi']}%."
                    sms_link = f"sms:{target_phone}?body={urllib.parse.quote(sms_body)}"
                    st.markdown(f'''
                        <a href="{sms_link}" target="_blank" style="text-decoration:none;">
                            <div style="background-color:#00C851; color:white; padding:10px; border-radius:8px; text-align:center; font-weight:bold;">
                                📲 MỞ TIN NHẮN SMS
                            </div>
                        </a>
                        ''', unsafe_allow_html=True)

            # --- 3. BIỂU ĐỒ ---
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD (kPa)", line=dict(color='green')), 1, 1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)"), 2, 1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)"), 2, 1)
            st.plotly_chart(fig, use_container_width=True)

            # --- 4. BẢNG THỐNG KÊ (MAX, MIN, MEAN) ---
            st.subheader("📊 Thống kê chỉ số")
            st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))

            # --- 5. BẢNG CHI TIẾT BẢN GHI (NHUỘM MÀU) ---
            st.subheader("📋 Chi tiết bản ghi")
            def highlight_vpd(row):
                # Nhuộm màu đỏ nhạt, chữ đỏ đậm khi VPD nằm ngoài ngưỡng an toàn
                if row['VPD'] > 1.5 or row['VPD'] < 0.4:
                    return ['background-color: #FFC7CE; color: #9C0006; font-weight: bold'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                .sort_values('Thời gian', ascending=False)
                .style.apply(highlight_vpd, axis=1),
                use_container_width=True
            )
else:
    st.info("👈 Vui lòng tải file JSON quan trắc ở thanh bên để hiển thị dữ liệu.")
