# Kịch bản demo 5 phút — AI Barista Agent

## 1. Mục tiêu demo

Trong 5 phút, cần làm nổi bật các điểm sau:

1. Agent hiểu yêu cầu tự nhiên của người dùng.
2. Agent có thể gọi tool `get_menu()`.
3. Tool lấy dữ liệu thật từ `menu.json`.
4. Câu trả lời được grounding theo menu, tags, giá và allergens.
5. Agent không tự bịa món ngoài menu.
6. Ứng dụng đang chạy trên Cloud Run, không chạy local trên máy demo.

> **Lưu ý:** Đây là prototype theo Codelab. Dữ liệu đang ở local JSON, history chỉ lưu trong session hiện tại và chưa có persistent database.

---

## 2. Kiến trúc cần giới thiệu

```text
Streamlit
    ↓
Google ADK InMemoryRunner
    ↓
LlmAgent
    ↓
Gemini 3.5 Flash
    ↓
get_menu() tool
    ↓
menu.json
    ↓
Response về Streamlit
```

Ứng dụng được deploy trên **Cloud Run**. Cloud Run chạy container Streamlit và dùng runtime service account để gọi Gemini trên Google Agent Platform/Vertex AI.

---

## 3. Chuẩn bị trước demo

### 3.1. Mở sẵn Cloud Run URL

Mở URL Cloud Run trong trình duyệt. Không bắt đầu bằng việc deploy hoặc chạy local.

### 3.2. Kiểm tra service trước demo

```powershell
gcloud run services describe coffee-barista `
  --project youtube-drive-auto-upload `
  --region us-central1 `
  --format="yaml(status.conditions,status.traffic,status.url)"
```

Cần thấy:

- `Ready: True`.
- Revision đang nhận `100%` traffic.
- Có URL Cloud Run.

### 3.3. Giữ container warm nếu cần

Khoảng 10–15 phút trước demo:

```powershell
gcloud run services update coffee-barista `
  --project youtube-drive-auto-upload `
  --region us-central1 `
  --min 1 `
  --max 3 `
  --memory 1Gi `
  --cpu 1 `
  --timeout 300 `
  --concurrency 10
```

Không chạy `gcloud run deploy` trong lúc demo.

---

## 4. Flow demo theo thời gian

### 0:00–0:30 — Giới thiệu bài toán

**Nói:**

> Đây là một AI Barista agent. Người dùng không cần biết trước menu; chỉ cần nhập sở thích như đồ uống nóng/lạnh, mạnh/ngọt hoặc yêu cầu không có dairy. Agent dùng dữ liệu menu thực tế để đưa ra gợi ý.

**Giới thiệu kiến trúc:**

```text
Streamlit → Google ADK InMemoryRunner → LlmAgent
→ Gemini 3.5 Flash → get_menu() → menu.json → Response
```

**Nói thêm:**

> Ứng dụng đang chạy trên Cloud Run, không chạy local trên máy của em.

---

### 0:30–1:20 — Demo tool calling và grounding

**Nhập prompt:**

```text
I want a strong, cold, dairy-free drink. Recommend one item and explain why.
```

**Kết quả kỳ vọng:**

- `Cold Brew Coffee` hoặc `Nitro Cold Brew`.
- Có các tags `strong`, `cold`, `dairy-free`.
- Giá khoảng `$4.00` hoặc `$4.50`.
- Không gợi ý món ngoài menu.

**Giải thích:**

> Agent có thể gọi `get_menu()`, đọc các item trong `menu.json`, sau đó đối chiếu các thuộc tính `strong`, `cold` và `dairy-free` để chọn món.

**Điểm cần nhấn mạnh:**

```text
tool calling + grounding
```

---

### 1:20–2:15 — Demo allergen awareness

**Nhập prompt:**

```text
I have a dairy allergy. Which menu items should I avoid? Please explain the allergens.
```

**Kết quả kỳ vọng:**

- `Seasonal Pumpkin Latte` — dairy.
- `Classic Croissant` — dairy, wheat.
- `Iced Caramel Macchiato` — dairy.

**Hỏi tiếp:**

```text
Which menu items are explicitly dairy-free?
```

Agent có thể đề cập:

- Espresso Solo.
- Oat Milk Honey Latte.
- Cold Brew Coffee.
- Vegan Blueberry Muffin.
- Nitro Cold Brew.

**Giải thích:**

> Dữ liệu allergen không được hard-code trong từng prompt. Dữ liệu nằm trong `menu.json`, được tool đọc và đưa vào context khi agent cần.

**Lưu ý an toàn:**

> Đây là metadata phục vụ demo, không phải tư vấn y tế. Trong thực tế cần xác minh thành phần và nguy cơ nhiễm chéo.

---

### 2:15–3:00 — Demo xử lý yêu cầu mơ hồ

**Nhập prompt:**

```text
I want something sweet.
```

Agent nên hỏi một câu làm rõ, ví dụ:

```text
Would you prefer something hot or cold?
```

**Nhập tiếp:**

```text
Cold, please.
```

Agent có thể gợi ý:

```text
Iced Caramel Macchiato
```

hoặc một món `cold`/`sweet` có thật trong menu.

**Giải thích:**

> Đây là điểm khác giữa chatbot trả lời cố định và agent. Agent nhận ra yêu cầu chưa đủ rõ và chủ động hỏi thêm để thu hẹp lựa chọn.

Nếu model trả lời thẳng thay vì hỏi clarification, dùng prompt dễ kích hoạt hơn:

```text
I want something nice.
```

---

### 3:00–3:50 — Demo guardrail chống bịa món

**Nhập prompt:**

```text
Do you have a Matcha Strawberry Frappuccino? If not, recommend the closest item from the actual menu.
```

**Kết quả kỳ vọng:**

- Agent nói món đó không có trong menu.
- Agent gợi ý một món có thật.
- Agent không tự tạo giá hoặc mô tả cho món không tồn tại.

**Giải thích:**

> Instruction yêu cầu agent chỉ recommendation những item được trả về từ `get_menu()`. Đây là guardrail ở mức hành vi, giúp giảm hallucination.

**Điểm cần nhấn mạnh:**

```text
grounded response + hallucination control
```

---

### 3:50–4:30 — Giải thích nhanh source code

Mở GitHub hoặc VS Code, chỉ đọc code, không sửa trong lúc demo.

#### `app.py`

> `app.py` là lớp giao diện Streamlit. File này hiển thị menu sidebar, nhận prompt và gọi `InMemoryRunner`.

Các đoạn chính:

```python
st.chat_input(...)
```

```python
st.session_state.runner.run_debug(...)
```

#### `agent.py`

> `agent.py` định nghĩa `LlmAgent`, model Gemini, instruction và tool `get_menu()`.

```python
barista_agent = LlmAgent(
    name="barista_agent",
    model="gemini-3.5-flash",
    instruction="...",
    tools=[get_menu],
)
```

#### `menu.json`

> `menu.json` là structured data source. Mỗi item có `name`, `description`, `price`, `tags` và `allergens`.

#### Cloud Run

> Khi deploy, Cloud Run build source bằng Buildpacks. Container chạy Streamlit và dùng runtime service account để gọi Agent Platform/Gemini.

---

### 4:30–5:00 — Nêu giới hạn và hướng production

**Nói thẳng:**

> Phiên bản hiện tại là prototype theo Codelab. Dữ liệu đang ở local JSON, tool đang trả toàn bộ menu và lịch sử hội thoại nằm trong `st.session_state` nên chưa persistent. Nếu mở rộng production, em sẽ thay JSON bằng Firestore hoặc Vector Search, thêm persistent session store, authentication, observability và output validation.

### Roadmap

```text
menu.json
    → Firestore / Vector Search

InMemoryRunner
    → Persistent Session Service

Public Cloud Run URL
    → IAM / IAP / application authentication

Manual test
    → Automated evaluation and safety tests
```

---

## 5. Bộ keyword nên dùng

### 5.1. Preference matching

```text
strong
cold
hot
sweet
dairy-free
sugar-free
vegan
bakery
savory
seasonal
```

Ví dụ:

```text
I want a strong and cold drink.
```

```text
I want something sweet and hot.
```

```text
I need a dairy-free and sugar-free option.
```

### 5.2. Allergen

```text
dairy allergy
wheat allergy
allergens
dairy-free
vegan
safe option
avoid
```

Ví dụ:

```text
I have a dairy allergy. What should I avoid?
```

```text
Which items contain wheat?
```

### 5.3. Clarification

```text
something nice
something good
I want a recommendation
surprise me
I need something for the afternoon
```

Mục tiêu là tạo một yêu cầu đủ mơ hồ để agent hỏi lại.

### 5.4. Grounding và anti-hallucination

```text
Is Matcha Latte available?
Do you have a Strawberry Frappuccino?
Recommend something not on the menu.
What is the price of the Cappuccino?
```

Prompt nên dùng nhất:

```text
Do you have a Matcha Strawberry Frappuccino? If not, recommend something from the actual menu.
```

---

## 6. Bộ prompt chuẩn bị sẵn

```text
1. I want a strong, cold, dairy-free drink. Recommend one item and explain why.

2. I have a dairy allergy. Which menu items should I avoid? Please explain the allergens.

3. I want something sweet.

4. Cold, please.

5. Do you have a Matcha Strawberry Frappuccino? If not, recommend the closest item from the actual menu.

6. Which menu items are explicitly dairy-free and sugar-free?
```

---

## 7. Câu hỏi thường gặp khi demo

### Q: Tool có thực sự được gọi không?

**Trả lời:**

Có. `get_menu()` được đăng ký trong `tools=[get_menu]`. ADK expose function này cho agent. Khi prompt cần thông tin menu, Gemini có thể phát sinh tool call; function đọc `menu.json`, rồi kết quả được đưa lại vào context để model tạo response.

Có thể chỉ ra code:

```python
tools=[get_menu]
```

```python
def get_menu() -> str:
    with open("menu.json", "r") as f:
        menu_data = json.load(f)
        return json.dumps(menu_data)
```

### Q: Hệ thống có lưu history không?

**Trả lời:**

Có history trong phiên Streamlit hiện tại thông qua `st.session_state.messages` và `session_id`, nhưng chưa có persistent history. Nếu refresh hoặc mất session thì history có thể mất. Production cần persistent session service hoặc Firestore.

### Q: Đây có phải RAG không?

**Trả lời:**

Đây là một dạng retrieval/tool-based RAG đơn giản. Agent retrieve dữ liệu bằng function tool trước khi trả lời. Tuy nhiên chưa phải vector-search RAG; hiện tại tool đọc local JSON. Với dữ liệu lớn, có thể thay `get_menu()` bằng truy vấn Firestore Vector Search hoặc managed retrieval backend.

### Q: Tại sao không dùng API key?

**Trả lời:**

Ứng dụng dùng Google Cloud ADC/IAM authentication thay vì API key. Khi chạy local, Google SDK dùng ADC của user; khi chạy Cloud Run, SDK dùng runtime service account `ai-barista-runner`. OAuth token được SDK tự động lấy và refresh.

### Q: Cloud Run có làm model inference không?

**Trả lời:**

Không. Cloud Run chỉ chạy web application và orchestration code. Model inference được thực hiện bởi Gemini trên Google Agent Platform/Vertex AI. Cloud Run nhận request, gọi ADK, ADK gọi model, rồi trả response về Streamlit.

---

## 8. Kết luận dùng khi demo

> Hệ thống này chứng minh pattern agent cơ bản: một LLM có instruction, có khả năng gọi tool để lấy dữ liệu thực tế và có giao diện ứng dụng chạy trên Cloud Run. Điểm quan trọng không phải menu coffee, mà là pattern này có thể mở rộng bằng cách thay `menu.json` bằng database hoặc retrieval system mà không cần thay đổi toàn bộ agent architecture.
