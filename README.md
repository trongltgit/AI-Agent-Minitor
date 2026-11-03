# AI Agent Monitor v2 – KYA + Strict Broker Limits + Customer Behavior + Anti-Bot

Hệ thống giám sát AI Agent nâng cao, kết hợp:

1. **Quản lý chặt hạn mức phía Broker (nhà cung cấp)**
2. **Phân tích xu hướng / hành vi giao dịch phía Khách hàng**
3. **Anti-Bot / Velocity detection** (kết hợp kinh nghiệm chống bot trước đây)
4. **KYA (Know Your Agent)** + LLM Critic

## Tính năng chính v2

### Phía Broker (Strict Policy - không thể bypass)
- Giới hạn notional / lệnh + / ngày
- Giới hạn leverage
- Giới hạn số lệnh / giờ và / ngày
- Danh sách cặp tiền & loại action được phép
- Risk tier (STANDARD / HIGH / RESTRICTED)
- Ngưỡng bắt buộc human approval

### Phía Khách hàng (Customer Tendency)
- Hồ sơ hành vi (avg notional, leverage, giờ ưa thích...)
- Điểm lệch hành vi (behavior deviation)
- Suspicion score tích lũy → tự động đưa vào watchlist

### Anti-Bot Layer
- Velocity (số lệnh / 5 phút, / 1 giờ)
- Kết hợp size + tần suất bất thường
- Off-hour large activity
- Extreme leverage patterns

## Cấu trúc thư mục

```
ai_agent_monitor/
├── app/dashboard.py
├── src/
│   ├── api.py
│   ├── database.py
│   ├── features.py
│   ├── monitor_service.py
│   ├── llm_critic.py
│   └── train.py
├── render.yaml
├── requirements.txt
└── README.md
```

## Chạy local

```bash
cd ai_agent_monitor
pip install -r requirements.txt
python -m src.train

# Terminal 1 - API
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - Dashboard
streamlit run app/dashboard.py --server.port 8501
```

## Deploy lên Render (khuyến nghị)

### Cách 1: Blueprint (dễ nhất)
1. Push code lên GitHub
2. Vào https://dashboard.render.com → **New** → **Blueprint**
3. Kết nối repo, chọn file `render.yaml`
4. Render tự tạo PostgreSQL + API + Dashboard

### Cách 2: Thủ công
- Tạo **Web Service**
- Build Command: `pip install -r requirements.txt && python -m src.train`
- Start Command: `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
- Thêm PostgreSQL database và set `DATABASE_URL`

## API chính

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/monitor/action` | Giám sát action của agent |
| POST | `/agents/register` | Đăng ký agent + hạn mức broker |
| POST | `/customers/profile` | Tạo/cập nhật hồ sơ hành vi khách |
| GET | `/actions/recent` | Lịch sử gần đây |
| GET | `/actions/stats` | Thống kê |
| GET | `/agents` | Danh sách agent |
| GET | `/customers` | Danh sách khách + suspicion |

## Quyết định cuối cùng

- **ALLOW** – trong hạn mức broker + hành vi khách bình thường
- **REVIEW** – lệch xu hướng khách hoặc velocity cao → cần người xem
- **BLOCK** – vượt hạn mức broker hoặc điểm rủi ro rất cao

---
**Version 2.0** – Kết hợp KYA + Strict Broker Limits + Customer Behavior Profiling + Anti-Bot
