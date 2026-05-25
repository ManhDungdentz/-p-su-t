import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# =========================================================
# --- CẤU HÌNH TRANG ---
# =========================================================
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

# --- HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    if vpd > 1.5:
        ly_do, tinh_trang = "Nóng và khô quá mức.", "Cây cháy lá, héo rũ."
        cach_xu_ly = "Bật phun sương, kéo rèm che nắng ngay."
    elif vpd < 0.8:
        ly_do, tinh_trang = "Độ ẩm quá cao.", "Nguy cơ thối rễ, nấm bệnh."
        cach_xu_ly = "Bật quạt thông gió, ngừng tưới."
    else:
        ly_do, tinh_trang, cach_xu_ly = "Bình thường.", "Cây ổn định.", "Tiếp tục theo dõi."
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = (f"📍 TRẠNG THÁI: {status}\n"
                f"VPD: {vpd} kPa\n"
                f"Nhiệt độ: {temp}°C\n"
                f"Độ ẩm: {humi}%\n\n"
                f"Lý do: {ly_do}\n"
                f"Tình trạng: {tinh_trang}\n"
                f"Xử lý: {cach_xu_ly}")
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except:
        return False

# --- TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi):
        return None
    # Công thức chuẩn
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

# --- NGƯỠNG VPD THEO TỪNG LOẠI CÂY ---
CROP_VPD = {
    "🌶️ Ớt chuông": {
        "low": 0.6, "ideal_min": 0.8, "ideal_max": 1.2, "warn_max": 1.5,
        "note_low":  "Ớt chuông dễ nấm xám khi ẩm cao.",
        "note_ok":   "Ớt chuông phát triển tốt, tiếp tục duy trì.",
        "note_warn": "Hơi khô, kiểm tra hệ thống tưới phun.",
        "note_high": "Stress nhiệt, ớt dễ rụng hoa và quả non.",
    },
    "🥒 Dưa leo": {
        "low": 0.7, "ideal_min": 0.9, "ideal_max": 1.3, "warn_max": 1.6,
        "note_low":  "Dưa leo dễ bị phấn trắng khi độ ẩm quá cao.",
        "note_ok":   "Dưa leo sinh trưởng tốt, giữ nguyên điều kiện.",
        "note_warn": "VPD hơi cao, tăng phun sương nhẹ.",
        "note_high": "Dưa leo héo nhanh, cần tưới và che nắng gấp.",
    },
    "🍈 Dưa lưới": {
        "low": 0.8, "ideal_min": 1.0, "ideal_max": 1.4, "warn_max": 1.8,
        "note_low":  "Dưa lưới cần thoáng, ẩm cao gây nứt quả.",
        "note_ok":   "Dưa lưới trong ngưỡng lý tưởng.",
        "note_warn": "Kiểm tra hệ thống thông gió, VPD đang cao dần.",
        "note_high": "Stress nước nghiêm trọng, dưa lưới dễ nứt vỏ.",
    },
    "🍅 Cà chua": {
        "low": 0.7, "ideal_min": 0.8, "ideal_max": 1.2, "warn_max": 1.5,
        "note_low":  "Cà chua dễ bị mốc sương khi độ ẩm quá cao.",
        "note_ok":   "Cà chua phát triển tốt, hoa đậu quả bình thường.",
        "note_warn": "VPD cao, cà chua có thể rụng hoa.",
        "note_high": "Stress nhiệt nặng, cà chua ngừng đậu quả.",
    },
}

def get_greenhouse_advice(vpd, crop):
    if pd.isna(vpd):
        return "N/A", "Chờ dữ liệu...", "#808080"
    c = CROP_VPD.get(crop, list(CROP_VPD.values())[0])
    lo, i_min, i_max, w_max = c["low"], c["ideal_min"], c["ideal_max"], c["warn_max"]
    if vpd < lo:
        return "🔵 QUÁ THẤP",  c["note_low"],  "#1E90FF"
    if lo <= vpd < i_min:
        return "🟡 CẢNH BÁO",  c["note_warn"], "#FFA500"
    if i_min <= vpd <= i_max:
        return "🟢 LÝ TƯỞNG",  c["note_ok"],   "#00C851"
    if i_max < vpd <= w_max:
        return "🟡 CẢNH BÁO",  c["note_warn"], "#FFA500"
    return "🔴 QUÁ CAO",       c["note_high"], "#FF4B4B"

# --- XỬ LÝ DỮ LIỆU & KHỬ NHIỄU (CHỖ NÀY LÀ CÁI KHÁC BIỆT ĐÂY) ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except:
        return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(
            df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'),
            errors='coerce', utc=True
        ).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')

    # FIX CHUẨN: ĐẢO tempKK và humiKK, KHÔNG CHIA 10
    if 'tempKK' in df.columns and 'humiKK' in df.columns:
        df['temp'] = pd.to_numeric(df['humiKK'], errors='coerce') # Đảo humiKK vào nhiệt độ
        df['humi'] = pd.to_numeric(df['tempKK'], errors='coerce') # Đảo tempKK vào độ ẩm
    
    # Giữ logic chia 10 cho các cột Tiếng Việt nếu file khác có dùng
    elif 'Nhiệt Độ' in df.columns:
        df['temp'] = pd.to_numeric(df['Nhiệt Độ'], errors='coerce') / 10
        df['humi'] = pd.to_numeric(df['PH'], errors='coerce') / 10

    # Khử nhiễu
    df = df.dropna(subset=['temp', 'humi']).copy()
    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- HÀM VẼ BIỂU ĐỒ (DẢI MÀU CŨ CỦA ÔNG) ---
def draw_chart(df_valid, c_info, smooth=True):
    df_chart = df_valid.copy()
    x_col = 'Thời gian'

    if smooth and len(df_chart) > 10:
        df_chart = df_chart.set_index('Thời gian').resample('1h').agg({'VPD': 'median', 'temp': 'median', 'humi': 'median'}).dropna(how='all').reset_index()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("VPD (kPa)", "Nhiệt độ & Độ ẩm"))

    fig.add_trace(go.Scatter(x=df_chart[x_col], y=df_chart['VPD'], name="VPD (kPa)", line=dict(color='#2E7D32', width=2.5)), row=1, col=1)

    # Dải màu chuẩn của ông
    c_lo, c_imin, c_imax, c_wmax = c_info["low"], c_info["ideal_min"], c_info["ideal_max"], c_info["warn_max"]
    fig.add_hrect(y0=0,      y1=c_lo,   fillcolor="rgba(30, 144, 255, 0.3)", line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_lo,   y1=c_imin, fillcolor="rgba(255, 165, 0, 0.3)",  line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_imin, y1=c_imax, fillcolor="rgba(0, 200, 81, 0.3)",   line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_imax, y1=c_wmax, fillcolor="rgba(255, 165, 0, 0.3)",  line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_wmax, y1=4.0,    fillcolor="rgba(255, 75, 75, 0.3)",  line_width=0, row=1, col=1)

    fig.add_trace(go.Scatter(x=df_chart[x_col], y=df_chart['temp'], name="Nhiệt độ (°C)", line=dict(color='#E53935')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_chart[x_col], y=df_chart['humi'], name="Độ ẩm (%)", line=dict(color='#1E88E5')), row=2, col=1)

    fig.update_layout(height=550, template="plotly_white", hovermode='x unified')
    return fig

# --- HIỂN THỊ METRIC CARD ---
def show_metrics(last, status, advice, color, u_mail, u_pass, t_mail, selected_crop, key_suffix="default"):
    st.subheader("📍 Thông số mới nhất")
    m1, m2, m3 = st.columns([1, 1.2, 1.8])
    m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
    m1.metric("Độ ẩm",    f"{round(last['humi'], 1)} %")
    
    m2.markdown(f'<div style="background-color:{color};padding:15px;border-radius:10px;color:white;text-align:center;">'
                f'<h3 style="margin:0;">VPD: {last["VPD"]} kPa</h3><b>{status}</b></div>', unsafe_allow_html=True)
    m3.warning(f"**Chỉ đạo:** {advice}")
    
    if ("🔴" in status or "🔵" in status) and st.button("📧 Gửi Email cảnh báo", key=f"btn_{key_suffix}"):
        if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
            st.success("✅ Đã gửi!")
        else:
            st.error("❌ Lỗi cấu hình!")

# =========================================================
# --- MAIN APP ---
# =========================================================
with st.sidebar:
    st.header("📧 Cấu hình Gmail")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu app:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()
    mode = st.radio("Nguồn dữ liệu:", ["📂 Xem file JSON", "🎲 Mô phỏng Realtime"])
    selected_crop = st.selectbox("🌱 Loại cây:", list(CROP_VPD.keys()))
    if mode == "📂 Xem file JSON":
        uploaded_file = st.file_uploader("Tải file JSON", type=['json'])
    else:
        run_realtime = st.toggle("▶️ Bật Mô phỏng", value=True)

if mode == "📂 Xem file JSON" and uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        last = df.iloc[-1]
        status, advice, color = get_greenhouse_advice(last['VPD'], selected_crop)
        show_metrics(last, status, advice, color, u_mail, u_pass, t_mail, selected_crop, "file")
        st.plotly_chart(draw_chart(df, CROP_VPD[selected_crop]), use_container_width=True)
        st.dataframe(df.iloc[::-1], use_container_width=True)

elif mode == "🎲 Mô phỏng Realtime":
    if 'rt_history' not in st.session_state:
        st.session_state.rt_history = pd.DataFrame(columns=['Thời gian', 'temp', 'humi', 'VPD'])
    
    if run_realtime:
        new_row = {'Thời gian': datetime.now(), 'temp': 28.0, 'humi': 75.0, 'VPD': calculate_vpd(28.0, 75.0)}
        st.session_state.rt_history = pd.concat([st.session_state.rt_history, pd.DataFrame([new_row])]).tail(50)
        
    if not st.session_state.rt_history.empty:
        last = st.session_state.rt_history.iloc[-1]
        status, advice, color = get_greenhouse_advice(last['VPD'], selected_crop)
        show_metrics(last, status, advice, color, u_mail, u_pass, t_mail, selected_crop, "rt")
        st.plotly_chart(draw_chart(st.session_state.rt_history, CROP_VPD[selected_crop], smooth=False), use_container_width=True)
        time.sleep(2)
        st.rerun()
