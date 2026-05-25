import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max Full", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính - Bản Đầy Đủ")

# --- 2. HÀM GỬI EMAIL CẢNH BÁO ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"📍 TRẠNG THÁI: {status}\nVPD: {vpd} kPa\nNhiệt độ: {temp}°C\nĐộ ẩm: {humi}%"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except:
        return False

# --- 3. CÔNG THỨC TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or humi <= 5: return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(max(0, vpsat - vpair), 2)

# --- 4. XỬ LÝ DỮ LIỆU & KHỬ NHIỄU TUYỆT ĐỐI ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except:
        return pd.DataFrame()
    
    # Chuẩn hóa cột thời gian
    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Gộp cột nhiệt độ/độ ẩm từ các trạm khác nhau
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
    
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            # Xử lý độ F sang độ C và chặn nhiễu vật lý cực đoan
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan
            if col == 'humi':
                df.loc[(df[col] < 15) | (df[col] > 100), col] = np.nan

    # THUẬT TOÁN LÀM MƯỢT (Trị "cột đình")
    df = df.dropna(subset=['temp', 'humi']).copy()
    if len(df) > 5:
        for c in ['temp', 'humi']:
            # Lấy trung vị cửa sổ 5 điểm để triệt tiêu các gai nhọn (spikes)
            df[c] = df[c].rolling(window=5, center=True, min_periods=1).median()
            # Nội suy để bù đắp các điểm rác bị loại bỏ
            df[c] = df[c].interpolate().ffill().bfill()

    if not df.empty: 
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
        # Giới hạn giá trị VPD hiển thị để tránh lỗi scale trục Y
        df.loc[df['VPD'] > 2.5, 'VPD'] = np.nan
        df['VPD'] = df['VPD'].interpolate()
        
    return df

# --- 5. GIAO DIỆN STREAMLIT (BỘ LỌC CHI TIẾT) ---
with st.sidebar:
    st.header("⚙️ Cấu Hình Gmail")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()
    uploaded_file = st.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        st.sidebar.header("🔍 Bộ Lọc Dữ Liệu")
        
        # --- Lọc theo Ngày/Tháng ---
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        filter_mode = st.sidebar.radio("Chế độ xem:", ["Tất cả", "Theo Tháng", "Khoảng Ngày Tùy Chọn"])
        
        if filter_mode == "Theo Tháng":
            sel_m = st.sidebar.multiselect("Chọn tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
            df_work = df[df['Tháng'].isin(sel_m)].copy()
        elif filter_mode == "Khoảng Ngày Tùy Chọn":
            c1, c2 = st.sidebar.columns(2)
            d_min, d_max = df['Thời gian'].min().date(), df['Thời gian'].max().date()
            start_d = c1.date_input("Từ ngày", d_min)
            end_d = c2.date_input("Đến ngày", d_max)
            df_work = df[(df['Thời gian'].dt.date >= start_d) & (df['Thời gian'].dt.date <= end_d)].copy()
        else:
            df_work = df.copy()

        # --- Lọc theo Trạm (STT) ---
        stt_list = ["Tất cả các trạm"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả các trạm":
            df_work = df_work[df_work['STT'] == sel_stt]

        # --- HIỂN THỊ CHỈ SỐ DASHBOARD ---
        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            vpd_val = last['VPD']
            
            # XÁC ĐỊNH MÀU SẮC (NGƯỠNG ĐỎ > 1.5)
            if vpd_val > 1.5:
                color, status = "#FF4B4B", "🔴 QUÁ CAO (Cây Stress)"
            elif vpd_val < 0.5:
                color, status = "#1E90FF", "🔵 QUÁ THẤP (Ẩm cao)"
            else:
                color, status = "#00C851", "🟢 LÝ TƯỞNG"

            st.subheader(f"📊 Thông số Trạm {last['STT']} (Mới nhất)")
            m1, m2, m3 = st.columns([1, 1, 2])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            m2.markdown(f'''
                <div style="background-color:{color}; padding:20px; border-radius:15px; color:white; text-align:center;">
                    <h2 style="margin:0;">VPD: {vpd_val} kPa</h2>
                    <b style="font-size:1.1em;">{status}</b>
                </div>
            ''', unsafe_allow_html=True)
            
            if st.button("📧 Gửi Cảnh Báo Ngay"):
                if send_email_alert(u_mail, u_pass, t_mail, vpd_val, status, last['temp'], last['humi']):
                    st.success("✅ Đã gửi email!")
                else: st.error("❌ Lỗi cấu hình Gmail!")

            # --- 6. BIỂU ĐỒ DIỄN BIẾN (KHÓA TRỤC Y) ---
            st.subheader("📈 Biểu đồ diễn biến (Đã làm mượt)")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            
            # VPD Trace
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD", line=dict(color='green', width=3)), row=1, col=1)
            
            # Dải màu theo ngưỡng yêu cầu
            fig.add_hrect(y0=0, y1=0.5, fillcolor="rgba(30, 144, 255, 0.3)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=0.5, y1=1.5, fillcolor="rgba(0, 200, 81, 0.3)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=1.5, y1=2.5, fillcolor="rgba(255, 75, 75, 0.3)", line_width=0, row=1, col=1)
            
            # Temp/Humi Trace
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm"), row=2, col=1)
            
            fig.update_layout(height=600, template="plotly_white", hovermode='x unified')
            fig.update_yaxes(range=[0, 2.5], row=1, col=1) # Khóa trục Y VPD
            st.plotly_chart(fig, use_container_width=True)

            # --- 7. BẢNG DỮ LIỆU ---
            st.subheader("📋 Bảng dữ liệu chi tiết")
            def highlight_vpd(row):
                if row['VPD'] > 1.5: return ['background-color: #FFC7CE; color: #9C0006'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                .sort_values('Thời gian', ascending=False)
                .style.apply(highlight_vpd, axis=1),
                use_container_width=True
            )
        else:
            st.error("🚨 Không có dữ liệu hợp lệ trong khoảng này.")
else:
    st.info("👈 Hãy tải file JSON để bắt đầu.")
