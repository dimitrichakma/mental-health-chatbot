import os
import uuid

import requests
import streamlit as st


def _backend_url():
    # Streamlit Community Cloud: set BACKEND_URL in the app's Secrets.
    # Local: env var, or defaults to a locally-running backend.
    try:
        return st.secrets["BACKEND_URL"]
    except Exception:
        return os.getenv("BACKEND_URL", "http://localhost:8000")


BACKEND_URL = _backend_url()

USER_AVATAR = "🧑"
BOT_AVATAR = "🌿"

PATH_LABELS = {
    "naive_rag": "knowledge base",
    "graph_rag": "concept graph",
    "both": "knowledge base + graph",
    "web_fallback": "web search",
    "no_answer": "no source found",
}

EXAMPLES = [
    "What is cognitive restructuring?",
    "What cognitive distortions does CBT target?",
    "How is panic disorder treated?",
    "What is exposure and response prevention?",
    "How does behavioral activation help with depression?",
]

st.set_page_config(page_title="CBT & Mental Health Chatbot", page_icon="🌿", layout="centered")

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.2rem; max-width: 820px; }

      .app-header {
        border-radius: 16px;
        padding: 1.4rem 1.6rem;
        margin-bottom: 0.4rem;
        background: linear-gradient(135deg, #1f6f5c 0%, #3a8fb7 100%);
        color: #fff;
      }
      .app-header h1 { margin: 0; font-size: 1.55rem; font-weight: 700; }
      .app-header p  { margin: 0.35rem 0 0; opacity: 0.9; font-size: 0.95rem; }

      .disclaimer {
        font-size: 0.8rem; color: #6b7280;
        border-left: 3px solid #d1d5db; padding: 0.25rem 0 0.25rem 0.7rem;
        margin: 0.6rem 0 1.1rem;
      }

      .path-row { margin-top: 0.5rem; font-size: 0.78rem; color: #6b7280; }
      .path-chip {
        display: inline-block; margin-left: 0.35rem; padding: 0.12rem 0.6rem;
        border-radius: 999px; background: rgba(58,143,183,0.14);
        color: #2b6f8c; font-weight: 600; font-size: 0.72rem;
      }

      [data-testid="stChatMessage"] {
        border-radius: 14px; padding: 0.5rem 0.9rem; margin-bottom: 0.35rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-header">
      <h1>🌿 CBT &amp; Mental Health Chatbot</h1>
      <p>Ask about cognitive behavioral therapy, common mental-health conditions, and coping skills.
         Answers are drawn from a curated knowledge base and concept graph.</p>
    </div>
    <div class="disclaimer">
      This is an educational project, not medical advice or a substitute for professional care.
      If you are in crisis, contact a local crisis line or emergency services.
    </div>
    """,
    unsafe_allow_html=True,
)

# --- session state ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "pending" not in st.session_state:
    st.session_state.pending = None


@st.cache_data(ttl=15, show_spinner=False)
def backend_online():
    try:
        return requests.get(f"{BACKEND_URL}/health", timeout=3).ok
    except Exception:
        return False


# --- sidebar ---
with st.sidebar:
    st.subheader("CBT & Mental Health Chatbot")
    st.caption("Hybrid graph + vector retrieval, corrective-retrieval router, "
               "LangGraph agent with memory, web-search fallback.")

    online = backend_online()
    st.markdown(f"**Status:** {'🟢 ready' if online else '🔴 unavailable'}")

    st.divider()
    st.markdown("**Try an example**")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True, key=f"ex_{ex}"):
            st.session_state.pending = ex

    st.divider()
    if st.button("🗑️  New conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.pending = None
        st.rerun()

    st.caption(f"{len(st.session_state.messages) // 2} exchanges · "
               f"thread `{st.session_state.thread_id[:8]}`")


def render_paths(paths_used):
    if not paths_used:
        return
    chips = "".join(
        f'<span class="path-chip">{PATH_LABELS.get(p, p)}</span>' for p in paths_used
    )
    st.markdown(f'<div class="path-row">Sources:{chips}</div>', unsafe_allow_html=True)


def is_crisis(answer, paths_used):
    return bool(answer) and not paths_used and "crisis line" in answer.lower()


# --- replay history ---
for message in st.session_state.messages:
    avatar = USER_AVATAR if message["role"] == "user" else BOT_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        if message["role"] == "assistant" and is_crisis(message["text"], message.get("paths_used")):
            st.error(message["text"], icon="🆘")
        else:
            st.markdown(message["text"])
        render_paths(message.get("paths_used"))

if len(st.session_state.messages) == 0 and st.session_state.pending is None:
    st.info("Pick an example from the sidebar, or type a question below to start.", icon="💬")

# --- input (typed, or an example button from the sidebar) ---
typed = st.chat_input("Ask something about mental health or CBT...")
question = typed or st.session_state.pending
st.session_state.pending = None

if question:
    st.session_state.messages.append({"role": "user", "text": question})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(question)

    with st.chat_message("assistant", avatar=BOT_AVATAR):
        with st.spinner("Thinking through the knowledge base and graph..."):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/chat",
                    json={"question": question, "thread_id": st.session_state.thread_id},
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
                answer = data.get("answer", "Sorry, I couldn't get a response.")
                paths_used = data.get("paths_used", [])
            except Exception:
                answer = "Sorry, the assistant is temporarily unavailable. Please try again."
                paths_used = []

        if is_crisis(answer, paths_used):
            st.error(answer, icon="🆘")
        else:
            st.markdown(answer)
        render_paths(paths_used)

    st.session_state.messages.append(
        {"role": "assistant", "text": answer, "paths_used": paths_used}
    )
