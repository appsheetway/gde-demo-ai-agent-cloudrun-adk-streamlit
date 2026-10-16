# app.py
import streamlit as st
import json

# Set page config for a premium look
st.set_page_config(
    page_title="☕ Coffee Shop - Barista Bot",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS to make the header sticky (adapts to light/dark themes)
st.markdown("""
<style>
    div[data-testid="element-container"]:has(.header-container),
    div.element-container:has(.header-container) {
        position: sticky;
        top: 2.875rem;
        z-index: 999;
        background-color: transparent;
        padding-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# App Header (using inline styles for the permanent coffee theme look)
st.markdown("""
<div class="header-container" style="text-align: center; padding: 20px; background: linear-gradient(135deg, #8B5E3C, #6F4E37); color: white; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
    <h1 style="margin: 0; font-size: 2.5rem; font-weight: 700; color: white;">☕ ☕ Coffee Shop</h1>
    <p style="margin: 5px 0 0 0; font-size: 1.1rem; opacity: 0.9; color: white;">Your friendly AI Barista is ready to help you find the perfect drink or pastry!</p>
</div>
""", unsafe_allow_html=True)

# Load Menu for the sidebar
# [START load_menu]
try:
    with open("menu.json", "r") as f:
        menu_items = json.load(f)
except Exception as e:
    st.error(f"Error loading menu: {e}")
    menu_items = []
# [END load_menu]

# Sidebar Menu & Configuration
with st.sidebar:
    st.markdown("## ☕ Coffee Shop Menu")
    st.markdown("Explore our offerings and ask the barista for recommendations.")
    st.markdown("---")
    
    for item in menu_items:
        with st.container(border=True):
            st.markdown(f"**{item['name']}**  •  **${item['price']:.2f}**")
            st.caption(item['description'])
            
            # Tags & Allergens as native badges
            tags = " ".join([f"`{t}`" for t in item.get("tags", [])])
            if tags:
                st.markdown(tags)
            
            allergens = ", ".join(item.get("allergens", []))
            if allergens:
                st.markdown(f"⚠️ *Allergens: {allergens}*")


# [START response_cache]
# During the live demo most attendees type the same suggested prompts, so we
# cache answers per conversation path (the sequence of user messages). Each
# Cloud Run instance calls Gemini once per path instead of once per attendee.
# Add ?live=1 to the URL to bypass the cache (e.g. for the presenter).
USER_ID = "web_user"
CACHE_MAX_ENTRIES = 1000


@st.cache_resource
def get_response_cache():
    import threading
    from collections import OrderedDict
    return {"lock": threading.Lock(), "data": OrderedDict()}


def cache_key(messages):
    return tuple(" ".join(m["content"].lower().split()) for m in messages if m["role"] == "user")


def cache_get(key):
    cache = get_response_cache()
    with cache["lock"]:
        if key in cache["data"]:
            cache["data"].move_to_end(key)
            return cache["data"][key]
    return None


def cache_put(key, response_text):
    cache = get_response_cache()
    with cache["lock"]:
        cache["data"][key] = response_text
        cache["data"].move_to_end(key)
        while len(cache["data"]) > CACHE_MAX_ENTRIES:
            cache["data"].popitem(last=False)


async def record_cached_turn(runner, session_id, prompt, response_text):
    """Adds a cache-served turn to the ADK session so later live turns keep the context."""
    from google.adk.events import Event
    from google.genai import types

    svc = runner.session_service
    session = await svc.get_session(app_name=runner.app_name, user_id=USER_ID, session_id=session_id)
    if session is None:
        session = await svc.create_session(app_name=runner.app_name, user_id=USER_ID, session_id=session_id)
    await svc.append_event(session, Event(
        author="user", content=types.Content(role="user", parts=[types.Part(text=prompt)])))
    await svc.append_event(session, Event(
        author=runner.agent.name, content=types.Content(role="model", parts=[types.Part(text=response_text)])))
# [END response_cache]


# Chat Interface
if "session_id" not in st.session_state:
    import uuid
    st.session_state.session_id = str(uuid.uuid4())

if "runner" not in st.session_state:
    from google.adk.runners import InMemoryRunner
    from agent import app
    st.session_state.runner = InMemoryRunner(app=app)

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Welcome to ☕ Coffee Shop! What can I get started for you today?"}
    ]

# Display existing messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User Input
if prompt := st.chat_input("Ask for recommendations (e.g., 'What dairy-free pastries do you have?')"):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Generate response
    with st.chat_message("assistant"):
        try:
            import asyncio

            key = cache_key(st.session_state.messages)
            use_cache = st.query_params.get("live") != "1"
            response_text = cache_get(key) if use_cache else None

            if response_text is not None:
                asyncio.run(record_cached_turn(
                    st.session_state.runner, st.session_state.session_id, prompt, response_text))
            else:
                # Run the ADK runner asynchronously using asyncio.run
                # quiet=True stops run_debug from printing every response line to
                # stdout (one Cloud Logging entry per line under load).
                async def fetch_response():
                    return await st.session_state.runner.run_debug(
                        prompt,
                        user_id=USER_ID,
                        session_id=st.session_state.session_id,
                        quiet=True
                    )

                with st.spinner("The barista is preparing your answer... (it may take up to a minute when the shop is busy)"):
                    res_events = asyncio.run(fetch_response())

                response_text = "".join([
                    part.text
                    for event in res_events
                    if event.content and event.content.parts
                    for part in event.content.parts
                    if part.text
                ])
                if response_text.strip():
                    cache_put(key, response_text)

            st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
        except Exception as e:
            # Retries are exhausted at this point; show a friendly message for
            # quota errors instead of the raw exception.
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                st.warning("☕ The shop is very busy right now. Please try again in a few seconds!")
            else:
                st.error(f"Apologies, I ran into an error: {e}")