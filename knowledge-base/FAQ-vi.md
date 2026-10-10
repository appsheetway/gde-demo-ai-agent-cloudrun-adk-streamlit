# FAQ Demo AI Barista — Google ADK, Streamlit và Cloud Run

> **Mục đích:** Tài liệu để người tham dự đọc trước khi đặt câu hỏi trong buổi demo dành cho Dev.
>
> **Phạm vi:** Mô tả đúng implementation hiện tại: một prototype agent dùng Google ADK, Gemini, custom tool `get_menu()`, dữ liệu `menu.json`, giao diện Streamlit và deployment trên Cloud Run.

## 1. Tổng quan

### Q1. Hệ thống này làm gì?

Đây là một AI Barista dạng hội thoại. Người dùng nhập nhu cầu về đồ uống hoặc bánh trên giao diện Streamlit. Agent dùng Gemini để hiểu yêu cầu, có thể gọi tool `get_menu()` để đọc menu thật, sau đó đưa ra gợi ý dựa trên tên món, mô tả, giá, tags và allergens.

### Q2. Điểm mạnh chính của demo là gì?

Demo thể hiện đầy đủ một pattern agent nhỏ nhưng thực tế:

- LLM có instruction và mục tiêu rõ ràng.
- Agent có thể gọi function tool.
- Tool lấy dữ liệu có cấu trúc thay vì chỉ dựa vào kiến thức của model.
- Response được grounding theo menu và allergen.
- Ứng dụng được đóng gói, xác thực bằng Google Cloud IAM và chạy trên Cloud Run.

### Q3. Đây có phải hệ thống RAG không?

Đây là **tool-based retrieval**, có thể xem là dạng RAG đơn giản. Agent gọi `get_menu()` để retrieve dữ liệu từ `menu.json` trước khi trả lời. Tuy nhiên implementation hiện tại chưa dùng embedding, vector database hay semantic search. Với catalog lớn, có thể thay tool này bằng Firestore, Vertex AI Vector Search hoặc một retrieval backend khác.

## 2. Tech stack

### Q4. Streamlit là gì?

Streamlit là một Python framework dùng để xây dựng data app và AI web app nhanh mà không cần viết frontend riêng bằng React hoặc Vue. Developer chỉ cần viết Python; Streamlit biến các lệnh Python thành giao diện web tương tác.

### Q5. Streamlit có vai trò gì trong Codelab này?

`app.py` dùng Streamlit làm lớp giao diện và điều phối request:

- Hiển thị tiêu đề và menu ở sidebar.
- Hiển thị lịch sử chat bằng `st.chat_message`.
- Nhận input bằng `st.chat_input`.
- Gọi `InMemoryRunner` của ADK.
- Hiển thị response của agent.

Streamlit **không phải LLM**, không tự suy luận và không thay thế Google ADK. Nó là presentation/orchestration layer.

### Q6. Ưu điểm của Streamlit là gì?

- **Phát triển nhanh:** từ Python script có thể có UI trong thời gian ngắn.
- **Phù hợp data/AI demo:** chat, bảng, biểu đồ và file upload có sẵn component.
- **Ít boilerplate frontend:** không cần tách frontend/backend cho prototype nhỏ.
- **Tích hợp tốt với Python ecosystem:** dễ gọi SDK, model và data tools.
- **Dễ chạy local và deploy:** có thể chạy bằng `streamlit run app.py`, sau đó đóng gói lên Cloud Run.
- **Tốt cho proof of concept và internal tool:** giúp validate ý tưởng với người dùng sớm.

### Q7. Nhược điểm của Streamlit là gì?

- **Không phải framework frontend tổng quát:** khó đạt mức UX, routing và component customization như React/Next.js.
- **Mô hình rerun:** mỗi interaction có thể làm script chạy lại; cần hiểu `st.session_state`, caching và lifecycle.
- **Session state mặc định không bền vững:** dữ liệu trong memory có thể mất khi refresh, restart hoặc instance thay đổi.
- **Multi-user phức tạp hơn khi scale:** cần thiết kế state, concurrency và backend persistence cẩn thận.
- **Không lý tưởng cho ứng dụng transaction-heavy:** authentication, phân quyền, workflow và validation thường cần lớp backend riêng.
- **Khó tối ưu frontend nâng cao:** animation, offline mode, mobile UX và fine-grained client state không thuận tiện bằng frontend chuyên dụng.

### Q8. Google ADK là gì?

Google Agent Development Kit (ADK) là framework dùng để xây dựng agent. Trong project này, ADK cung cấp `LlmAgent`, `App`, `InMemoryRunner` và cơ chế đăng ký tool. ADK điều phối prompt, model và tool call thay vì developer phải tự viết toàn bộ vòng lặp gọi model.

### Q9. Gemini có vai trò gì?

Gemini là model suy luận và sinh ngôn ngữ tự nhiên. Model đọc yêu cầu, tuân thủ instruction, quyết định khi nào cần gọi `get_menu()` và tạo câu trả lời cuối cùng. Source hiện dùng model ID cụ thể:

```python
model="gemini-3.5-flash"
```

### Q10. Cloud Run là gì?

Cloud Run là nền tảng serverless managed container. Cloud Run chạy container của ứng dụng, cung cấp HTTPS URL, scale theo traffic và truyền biến môi trường `PORT`. Process Streamlit phải listen trên `0.0.0.0:$PORT`.

## 3. Kiến trúc và luồng xử lý

### Q11. Kiến trúc end-to-end như thế nào?

```text
User
  → Streamlit app.py
  → InMemoryRunner
  → LlmAgent (barista_agent)
  → Gemini 3.5 Flash
  → get_menu() tool khi cần
  → menu.json
  → Response về Streamlit

Cloud Run chạy toàn bộ application container.
Runtime service account xác thực khi app gọi Google Cloud API.
```

### Q12. Điều gì xảy ra sau khi người dùng gửi câu hỏi?

1. `st.chat_input()` nhận prompt.
2. Prompt được thêm vào `st.session_state.messages`.
3. `app.py` gọi `runner.run_debug()`.
4. ADK chạy root agent.
5. Gemini có thể phát sinh tool call tới `get_menu()`.
6. Tool đọc và trả `menu.json` dưới dạng JSON string.
7. Gemini tạo response.
8. `app.py` ghép text từ ADK events, hiển thị và lưu vào session state.

### Q13. `get_menu()` có phải là API không?

Không. Đây là một Python function chạy trong cùng process với Streamlit. ADK expose function này như một tool để agent có thể gọi. Nó chưa tạo HTTP endpoint riêng. Sau này có thể thay implementation của tool bằng truy vấn Firestore, Vector Search hoặc một REST API.

### Q14. Model có luôn gọi tool không?

Không nhất thiết. Việc gọi tool do model quyết định dựa trên instruction và prompt. Với câu hỏi về món, giá hoặc allergen, model thường cần gọi tool. Nếu muốn bảo đảm tuyệt đối, application nên retrieve/filter dữ liệu trước khi gọi model hoặc thêm bước validation.

### Q15. Agent chống hallucination bằng cách nào?

Instruction yêu cầu agent:

- Chỉ recommend item có trong kết quả `get_menu()`.
- Không bịa món ngoài menu.
- Hỏi một câu làm rõ nếu yêu cầu mơ hồ.
- Dựa trên tags, description và allergens thật.

Đây là behavioral guardrail, không phải formal guarantee. Production nên thêm schema validation, rule engine hoặc deterministic filtering.

## 4. Data dictionary

### Q16. Schema của một menu item là gì?

| Field | Kiểu dữ liệu | Bắt buộc | Ý nghĩa |
|---|---|---:|---|
| `name` | string | Có | Tên hiển thị của món |
| `description` | string | Có | Mô tả món |
| `price` | number | Có | Giá, hiện biểu diễn bằng USD |
| `tags` | array[string] | Không | Thuộc tính phục vụ matching/recommendation |
| `allergens` | array[string] | Không | Các allergen được khai báo |

### Q17. `tags` hiện có những giá trị nào?

Ví dụ hiện tại: `strong`, `hot`, `cold`, `sweet`, `dairy-free`, `sugar-free`, `seasonal`, `bakery`, `savory`, `vegan`. Đây là metadata mô tả; hiện chưa có database constraint hoặc taxonomy service kiểm soát giá trị.

### Q18. Diễn giải `allergens` như thế nào?

Mảng có thể là `[]`, `["dairy"]` hoặc `["wheat", "dairy"]`. Mảng rỗng nghĩa là demo không khai báo allergen, không phải cam kết y tế rằng món hoàn toàn an toàn. Người dùng có dị ứng cần xác nhận thành phần và nguy cơ nhiễm chéo với cửa hàng.

### Q19. Dữ liệu được đọc ở đâu?

- `agent.py`: `get_menu()` mở `menu.json` khi agent gọi tool.
- `app.py`: mở `menu.json` để hiển thị menu ở sidebar.

Vì vậy `menu.json` phải được commit và nằm trong working directory của container khi runtime.

## 5. State, bảo mật và vận hành

### Q20. Hệ thống có lưu history không?

Có lưu history trong phiên hiện tại qua:

```python
st.session_state.messages
st.session_state.session_id
```

Nhưng đây là in-memory state. Refresh browser, restart container hoặc chuyển instance có thể làm mất history. Chưa có persistent conversation database.

### Q21. Production nên thay thế state hiện tại bằng gì?

Có thể dùng ADK session service kết hợp với Firestore, Cloud SQL, Redis hoặc một persistence layer được phê duyệt. Cần xác định user ID, session ID, retention, encryption và quyền truy cập.

### Q22. Authentication hiện tại như thế nào?

Nếu deploy bằng `--allow-unauthenticated`, URL Cloud Run public. Cách này phù hợp demo nhưng không phù hợp dữ liệu nhạy cảm. Production có thể dùng Cloud Run IAM, Identity-Aware Proxy, application login hoặc API gateway.

### Q23. Secret và token lưu ở đâu?

Không commit API key, OAuth refresh token hoặc service-account JSON key. Local dùng ADC; Cloud Run dùng runtime service account gắn vào service. Nếu cần secret, dùng Secret Manager với least privilege.

## 6. Scale và lựa chọn thay thế Streamlit

### Q24. Streamlit có scale được không?

Có, Streamlit có thể chạy trên nhiều instance Cloud Run và phù hợp internal tool/prototype hoặc traffic vừa phải. Tuy nhiên scale compute không tự giải quyết state. Với nhiều instance, session state trong memory của từng instance không đồng nhất; người dùng có thể mất history khi request được route sang instance khác.

### Q25. Nếu scale lớn thì cần bổ sung gì?

- Persistent session store: Firestore, Redis hoặc Cloud SQL.
- Shared cache nếu cần.
- Authentication và authorization.
- Rate limiting và request timeout.
- Observability: logs, metrics, traces, error tracking.
- Model quota management và retry/backoff.
- Deterministic retrieval/filtering trước hoặc sau model.
- Async/background jobs nếu request dài.
- Container concurrency và min/max instance được benchmark thay vì đoán.

### Q26. Scale lớn nên dùng gì thay Streamlit?

Tùy nhu cầu:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Web product nhiều người dùng, UX tùy biến | React/Next.js frontend + FastAPI/Go/Node backend |
| Python full-stack đơn giản | FastAPI + frontend riêng hoặc server-rendered app |
| Chat realtime/streaming và session lớn | React/Next.js + WebSocket/SSE + backend persistent |
| Internal dashboard nhỏ | Tiếp tục dùng Streamlit |
| Demo AI nhanh, ít người dùng | Tiếp tục dùng Streamlit |
| Workflow agent phức tạp | Backend service riêng + ADK; Streamlit chỉ làm admin/demo UI |
| Mobile app | Native/Flutter/React Native + API backend |

Lựa chọn thay thế không nhất thiết là bỏ Streamlit hoàn toàn. Có thể giữ Streamlit cho admin console hoặc prototype, còn public product dùng frontend/backend chuyên dụng.

### Q27. Vì sao không thay Streamlit ngay trong Codelab?

Mục tiêu codelab là chứng minh agent và deployment nhanh. Streamlit giảm thời gian viết UI để tập trung vào ADK, tool calling và Cloud Run. Khi yêu cầu chuyển sang sản phẩm có nhiều user, auth, persistence và UX phức tạp, mới nên tách frontend/backend.

## 7. Deployment và quyền

### Q28. Source-based deployment hoạt động thế nào?

Lệnh `gcloud run deploy --source .` upload source cho Cloud Build. Buildpacks phát hiện Python và `requirements.txt`, build container, lưu image vào Artifact Registry, tạo Cloud Run revision và chạy Streamlit.

### Q29. Runtime service account là gì?

Service đang dùng:

```text
ai-barista-runner@youtube-drive-auto-upload.iam.gserviceaccount.com
```

Đây là identity của application khi chạy trên Cloud Run. Nó cần `roles/aiplatform.user` để gọi Gemini/Agent Platform. Developer deploy cần quyền `roles/iam.serviceAccountUser` để được phép gắn service account đó cho Cloud Run.

### Q30. Những quyền nào liên quan đến deploy?

| Identity / mục đích | Quyền tiêu biểu |
|---|---|
| Developer tạo/cập nhật Cloud Run | `roles/run.developer` hoặc quyền tương đương |
| Developer chạy build | `roles/cloudbuild.builds.editor` |
| Developer ghi image | `roles/artifactregistry.writer` |
| Tạo repository lần đầu | `roles/artifactregistry.admin` hoặc admin tạo trước |
| Developer dùng runtime service account | `roles/iam.serviceAccountUser` |
| Runtime gọi Gemini | `roles/aiplatform.user` |
| Dùng project làm quota consumer | `roles/serviceusage.serviceUsageConsumer` |

## 8. Câu hỏi demo gợi ý

- **Streamlit là gì và tại sao dùng nó ở đây?**
- **Nếu thay `menu.json` bằng Firestore thì phần nào của code thay đổi?**
- **Agent có thực sự gọi tool hay model chỉ đoán từ prompt?**
- **Làm thế nào kiểm chứng response chỉ chứa món có thật?**
- **Nếu có 1.000 user đồng thời, session state sẽ ra sao?**
- **Vì sao Cloud Run scale được nhưng history vẫn có thể mất?**
- **Khi nào nên chuyển từ Streamlit sang React/Next.js + backend?**
- **Cloud Run có chạy inference không hay chỉ orchestration?**
- **Vì sao không dùng API key?**
- **Model không khả dụng ở region thì xử lý thế nào?**

## 9. Tóm tắt để người demo nói trong một phút

Đây là Python Streamlit app dùng Google ADK `LlmAgent`. Streamlit cung cấp chat UI; `InMemoryRunner` chạy agent; Gemini 3.5 Flash suy luận; `get_menu()` là function tool đọc dữ liệu có cấu trúc từ `menu.json`. Tool giúp agent grounding câu trả lời về menu, giá và allergen. App được build bằng Cloud Build/Buildpacks và chạy trên Cloud Run bằng runtime service account riêng. Đây là prototype để minh họa agent pattern; production cần persistent storage, validation chặt hơn, authentication, observability và retrieval backend có khả năng scale.
