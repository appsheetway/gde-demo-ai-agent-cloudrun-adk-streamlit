# Load test

Hai script để kiểm tra app chịu được ~300 người trước ngày demo.

| Script | Kiểm tra | Đi qua |
|---|---|---|
| `agent_load.py` | Gemini quota (429), latency model | Máy local → Gemini (không qua Cloud Run) |
| `ws_load.py` | End-to-end: Cloud Run concurrency, autoscaling, Streamlit, Gemini | Giả lập browser qua WebSocket của Streamlit |

> **Chi phí:** cả hai đều gọi Gemini thật. Mỗi lượt chat ≈ 2–3 lần gọi model. Chạy tăng dần, không bắt đầu ngay với 300.

## Chuẩn bị

```bash
pip install -r requirements.txt           # websockets đi kèm sẵn
gcloud auth application-default login     # chỉ cần cho agent_load.py
```

## 1. Tầng Gemini — `agent_load.py`

Chạy từ thư mục gốc repo:

```bash
python loadtest/agent_load.py --users 20
python loadtest/agent_load.py --users 100 --ramp 10
python loadtest/agent_load.py --users 200 --ramp 0 --no-retry   # burst, xem 429 thô
```

- `--ramp 0`: mọi người hỏi cùng lúc (tình huống "mọi người thử đi!").
- `--no-retry`: tắt retry để thấy số 429 thật; mặc định retry bật giống production.
- `--no-fallback`: tắt chuyển model khi 429/timeout (chỉ dùng `gemini-3.5-flash`).
- `--model gemini-3.5-flash-lite`: đổi model chính để so sánh sức chịu tải.

## 2. End-to-end — `ws_load.py`

```bash
# Thử nhỏ trước
python loadtest/ws_load.py --url https://coffee-barista-380921864905.us-central1.run.app --users 30

# Tải demo: 300 người vào trong 60s, mỗi người chat 2 câu rồi ngồi idle 2 phút
python loadtest/ws_load.py --url https://coffee-barista-380921864905.us-central1.run.app \
  --users 300 --ramp 60 --turns 2 --hold 120
```

`--free-ratio 0.3` (mặc định): 30% tin nhắn có nội dung riêng để **không trúng response cache**, giống người tự gõ câu hỏi. Đặt `--free-ratio 1` để đo trường hợp xấu nhất (không cache).

Mỗi virtual user: mở WebSocket → load trang → gửi tin qua `st.chat_input` → giữ kết nối idle `--hold` giây (chính phần idle này chiếm concurrency trên Cloud Run).

Trong lúc chạy, mở Cloud Run → `coffee-barista` → **Metrics**: *Container instance count*, *Request latencies*, *Container CPU utilization*.

## Đọc kết quả

| Hiện tượng | Ý nghĩa | Xử lý |
|---|---|---|
| `connect HTTP 429` / `HTTP 503` | Cloud Run hết instance (đụng `--max` hoặc quota CPU) | Tăng `--max`/`--concurrency`, hoặc xin tăng quota CPU region |
| `busy (429 after retries)` | Gemini 429 dù đã retry và chuyển hết các model trong `FALLBACK_MODELS` | Giảm burst, thêm model fallback, xin quota/Provisioned Throughput |
| `connection closed (1006)` | WebSocket bị cắt (timeout, instance restart) | Kiểm tra `--timeout 3600`, log instance |
| Chat latency p90 tăng mạnh theo số user | Gemini chậm khi tải cao hoặc CPU instance bão hoà | Xem CPU utilization; nếu > 80% giảm `--concurrency` |

Mốc tham khảo:

| Test | Kết quả |
|---|---|
| `agent_load.py --users 150 --turns 1 --ramp 30 --no-retry --no-fallback` (trước khi tối ưu) | 35% thành công, còn lại 429 |
| `agent_load.py --users 150 --turns 1 --ramp 30` (retry + fallback + timeout) | 100% thành công, p50 7.5s, p90 10.5s |
