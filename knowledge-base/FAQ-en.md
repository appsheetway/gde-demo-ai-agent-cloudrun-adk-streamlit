# AI Barista Demo FAQ — Google ADK, Streamlit and Cloud Run

> **Purpose:** A pre-demo FAQ for developers who want to understand the stack, architecture, data dictionary, runtime flow, deployment and production trade-offs.
>
> **Scope:** This document describes the current implementation: a prototype agent using Google ADK, Gemini, a custom `get_menu()` tool, `menu.json`, a Streamlit UI and Cloud Run deployment.

## 1. Overview

### Q1. What does this system do?

It is a conversational AI barista. A user enters a request about drinks or pastries in the Streamlit UI. The agent uses Gemini to understand the request, may call `get_menu()` to read the actual menu, and recommends items based on names, descriptions, prices, tags and allergens.

### Q2. What is the main value of the demo?

The demo shows a compact but realistic agent pattern:

- An LLM with clear instructions and a goal.
- Function/tool calling.
- Structured data retrieval instead of relying only on model knowledge.
- Grounded recommendations and allergen responses.
- Packaging, Google Cloud IAM authentication and Cloud Run deployment.

### Q3. Is this a vector-search RAG system?

It is **tool-based retrieval**, which can be considered a simple form of RAG. The agent calls `get_menu()` to retrieve data from `menu.json` before responding. The current implementation does not use embeddings, a vector database or semantic search. For a larger catalog, the tool could be replaced by Firestore, Vertex AI Vector Search or another retrieval backend.

## 2. Tech stack

### Q4. What is Streamlit?

Streamlit is a Python framework for quickly building data and AI web applications without writing a separate frontend in React or Vue. Developers write Python, and Streamlit turns Python statements into an interactive web UI.

### Q5. What is Streamlit's role in this codelab?

`app.py` uses Streamlit as the presentation and request-orchestration layer:

- Render the page title and sidebar menu.
- Render chat history with `st.chat_message`.
- Receive input through `st.chat_input`.
- Invoke the ADK `InMemoryRunner`.
- Render the agent response.

Streamlit is **not the LLM**, does not perform reasoning by itself, and does not replace Google ADK.

### Q6. What are the advantages of Streamlit?

- **Fast development:** a usable UI can be built from a Python script quickly.
- **Good for data and AI demos:** chat, tables, charts and file upload components are readily available.
- **Low frontend boilerplate:** no separate React/Vue application is required for a small prototype.
- **Strong Python integration:** it is easy to call SDKs, model clients and data tools.
- **Simple local run and deployment:** use `streamlit run app.py`, then package the app for Cloud Run.
- **Good for proof of concept and internal tools:** useful for early user validation.

### Q7. What are the disadvantages of Streamlit?

- **Not a general-purpose frontend framework:** advanced UX, routing and component customization are harder than with React/Next.js.
- **Rerun model:** interactions can rerun the script; developers must understand `st.session_state`, caching and lifecycle behavior.
- **Session state is not durable by default:** in-memory data can disappear on refresh, restart or instance changes.
- **Multi-user scaling requires care:** state, concurrency and persistence need an explicit design.
- **Not ideal for transaction-heavy products:** authentication, authorization, workflows and validation often need a dedicated backend.
- **Advanced frontend optimization is less convenient:** animations, offline mode, mobile UX and fine-grained client state are easier in a specialized frontend.

### Q8. What is Google ADK?

Google Agent Development Kit (ADK) is the framework used to build the agent. This project uses ADK's `LlmAgent`, `App`, `InMemoryRunner` and tool registration mechanisms. ADK provides the orchestration structure so the developer does not have to manually implement every model/tool loop.

### Q9. What is Gemini's role?

Gemini is the reasoning and natural-language generation model. It interprets the request, follows the instruction, decides when the menu tool is needed and generates the final response. The source currently uses the explicit model ID:

```python
model="gemini-3.5-flash"
```

### Q10. What is Cloud Run?

Cloud Run is a managed serverless container platform. It runs the application container, provides an HTTPS URL, scales with traffic and supplies the `PORT` environment variable. The Streamlit process must listen on `0.0.0.0:$PORT`.

## 3. Architecture and request flow

### Q11. What is the end-to-end architecture?

```text
User
  → Streamlit app.py
  → InMemoryRunner
  → LlmAgent (barista_agent)
  → Gemini 3.5 Flash
  → get_menu() tool when needed
  → menu.json
  → Response back to Streamlit

Cloud Run runs the complete application container.
The runtime service account authenticates Google Cloud API calls.
```

### Q12. What happens after a user submits a question?

1. `st.chat_input()` receives the prompt.
2. The prompt is appended to `st.session_state.messages`.
3. `app.py` calls `runner.run_debug()`.
4. ADK executes the root agent.
5. Gemini may emit a tool call to `get_menu()`.
6. The tool reads and returns `menu.json` as a JSON string.
7. Gemini generates the response.
8. `app.py` joins text from ADK events, renders it and stores it in session state.

### Q13. Is `get_menu()` an API?

No. It is an in-process Python function. ADK exposes it as a callable tool for the agent; it does not create a separate HTTP endpoint. Its implementation could later be replaced with a Firestore, Vector Search or REST API query while preserving a similar agent contract.

### Q14. Does the model always call the tool?

Not necessarily. Tool use is selected by the model based on the instruction and the prompt. Menu, price and allergen questions should usually require the tool. For a strict production guarantee, the application should retrieve/filter data deterministically before the model call or add validation after generation.

### Q15. How does the agent reduce hallucination?

The instruction tells the agent to:

- Recommend only items returned by `get_menu()`.
- Never invent products outside the menu.
- Ask one clarifying question when the request is vague.
- Use the actual tags, descriptions and allergens.

This is a behavioral guardrail, not a formal guarantee. Production systems should add schema validation, deterministic filtering or a rule engine.

## 4. Data dictionary

### Q16. What is the schema of one menu item?

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `name` | string | Yes | Product display name |
| `description` | string | Yes | Product description |
| `price` | number | Yes | Price, currently represented in USD |
| `tags` | array[string] | No | Attributes used for matching/recommendation |
| `allergens` | array[string] | No | Declared allergens |

### Q17. Which values can appear in `tags`?

Current examples include `strong`, `hot`, `cold`, `sweet`, `dairy-free`, `sugar-free`, `seasonal`, `bakery`, `savory` and `vegan`. These are descriptive metadata values; there is currently no database constraint or taxonomy service enforcing them.

### Q18. How should `allergens` be interpreted?

The array can be `[]`, `["dairy"]` or `["wheat", "dairy"]`. An empty array means that no allergen is declared in this demo data; it is not a medical guarantee that the item is completely safe. Users with allergies should verify ingredients and cross-contamination risks with the shop.

### Q19. Where is the data loaded?

- `agent.py`: `get_menu()` opens `menu.json` when the agent calls the tool.
- `app.py`: opens `menu.json` to render the sidebar menu.

Therefore `menu.json` must be committed and available in the container working directory at runtime.

## 5. State, security and operations

### Q20. Does the system store chat history?

It stores history for the current session through:

```python
st.session_state.messages
st.session_state.session_id
```

This is in-memory state. A browser refresh, container restart or request routed to another instance can lose the conversation. No persistent conversation database is configured.

### Q21. What should replace the current state for production?

Use an ADK session service with Firestore, Redis, Cloud SQL or another approved persistence layer. Define user identity, session identity, retention, encryption and access-control rules.

### Q22. How is authentication handled?

If deployed with `--allow-unauthenticated`, the Cloud Run URL is public. That is convenient for a demo but not appropriate for sensitive data. Production can use Cloud Run IAM, Identity-Aware Proxy, application login or an API gateway.

### Q23. Where should secrets and tokens be stored?

Never commit API keys, OAuth refresh tokens or service-account JSON keys. Local execution uses ADC; Cloud Run uses the attached runtime service account. If a secret is required, use Secret Manager with least-privilege access.

## 6. Scaling and Streamlit alternatives

### Q24. Can Streamlit scale?

Yes. Streamlit can run on multiple Cloud Run instances and is suitable for an internal tool, prototype or moderate traffic. However, compute scaling does not solve state consistency. With multiple instances, each instance has its own in-memory session state; a user's history can disappear or appear inconsistent when requests are routed to another instance.

### Q25. What is needed for larger scale?

- Persistent session storage: Firestore, Redis or Cloud SQL.
- Shared caching where appropriate.
- Authentication and authorization.
- Rate limiting and request timeouts.
- Observability: logs, metrics, traces and error tracking.
- Model quota management and retry/backoff.
- Deterministic retrieval/filtering before or after model generation.
- Async/background jobs for long-running work.
- Benchmarked Cloud Run concurrency and min/max instance settings.

### Q26. What should replace Streamlit at larger scale?

The answer depends on the product requirement:

| Requirement | Suitable choice |
|---|---|
| Public web product with custom UX | React/Next.js frontend + FastAPI/Go/Node backend |
| Simple Python full-stack service | FastAPI + a dedicated frontend or server-rendered app |
| Large chat product with streaming/session requirements | React/Next.js + WebSocket/SSE + persistent backend |
| Small internal dashboard | Keep Streamlit |
| Fast AI demo for a small audience | Keep Streamlit |
| Complex agent workflow | Dedicated backend service + ADK; Streamlit as admin/demo UI |
| Mobile application | Native, Flutter or React Native + API backend |

Replacing Streamlit is not always all-or-nothing. It can remain useful for an admin console or prototype while a public product uses a specialized frontend/backend.

### Q27. Why not replace Streamlit in this codelab?

The codelab is designed to demonstrate the agent and deployment pattern quickly. Streamlit minimizes UI work so the focus stays on ADK, tool calling and Cloud Run. A specialized frontend/backend becomes justified when the product needs many users, complex authentication, durable state, strict workflows and advanced UX.

## 7. Deployment and permissions

### Q28. How does source-based deployment work?

`gcloud run deploy --source .` uploads the source to Cloud Build. Buildpacks detect Python and `requirements.txt`, build a container, store the image in Artifact Registry, create a Cloud Run revision and start Streamlit.

### Q29. What is the runtime service account?

The service uses:

```text
ai-barista-runner@youtube-drive-auto-upload.iam.gserviceaccount.com
```

This is the application identity inside Cloud Run. It needs `roles/aiplatform.user` to call Gemini/Agent Platform. The developer deploying the service separately needs `roles/iam.serviceAccountUser` to attach that identity to Cloud Run.

### Q30. Which permissions matter for deployment?

| Identity / purpose | Typical role |
|---|---|
| Developer creates/updates Cloud Run | `roles/run.developer` or equivalent |
| Developer runs builds | `roles/cloudbuild.builds.editor` |
| Developer writes images | `roles/artifactregistry.writer` |
| First repository creation | `roles/artifactregistry.admin`, or an admin creates it |
| Developer acts as runtime service account | `roles/iam.serviceAccountUser` |
| Runtime calls Gemini | `roles/aiplatform.user` |
| Project used as quota consumer | `roles/serviceusage.serviceUsageConsumer` |

## 8. Suggested demo questions

- **What is Streamlit, and why is it used here?**
- **If `menu.json` were replaced with Firestore, which part of the code would change?**
- **Does the agent really call a tool, or is the model guessing from the prompt?**
- **How can we verify that a response contains only real menu items?**
- **What happens to session state with 1,000 concurrent users?**
- **Why can Cloud Run scale while chat history is still lost?**
- **When should we move from Streamlit to React/Next.js plus a backend?**
- **Does Cloud Run run inference, or does it only orchestrate?**
- **Why use OAuth/IAM instead of an API key?**
- **What should happen when a model is unavailable in a region?**

## 9. One-minute presenter summary

This is a Python Streamlit application using a Google ADK `LlmAgent`. Streamlit provides the chat UI; `InMemoryRunner` executes the agent; Gemini 3.5 Flash performs reasoning; and `get_menu()` is a function tool that reads structured data from `menu.json`. The tool grounds answers about menu items, prices and allergens. The application is built with Cloud Build/Buildpacks and runs on Cloud Run with a dedicated runtime service account. This is a prototype that demonstrates an agent pattern; production would add persistent storage, stronger validation, authentication, observability and a scalable retrieval backend.
