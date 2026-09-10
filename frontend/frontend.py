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

# used only to localize the crisis-support message; never inferred / geolocated
COUNTRIES = {
    "": "Not specified",
    "BD": "Bangladesh",
    "US": "United States",
    "GB": "United Kingdom",
    "IN": "India",
    "CA": "Canada",
    "AU": "Australia",
    "EU": "Europe (other)",
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
    st.selectbox(
        "Country (for crisis-support resources)",
        options=list(COUNTRIES),
        format_func=lambda c: COUNTRIES[c],
        key="country",
        help="Only used to show local helplines if a message signals a crisis.",
    )

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


def is_crisis(message):
    """message is a stored history dict or a fresh {'kind':..., 'text':...}.
    Prefer the backend's explicit kind; fall back to a text heuristic for
    history saved before the flag existed."""
    if message.get("kind"):
        return message["kind"] == "crisis"
    answer, paths = message.get("text", ""), message.get("paths_used")
    return bool(answer) and not paths and "crisis" in answer.lower() and "emergency" in answer.lower()


def _send_feedback(log_id, rating=None, note=None):
    try:
        requests.post(
            f"{BACKEND_URL}/feedback",
            json={"log_id": log_id, "rating": rating, "note": note},
            timeout=15,
        )
    except Exception:
        pass


def feedback_row(log_id):
    """Thumbs + optional note under an assistant message. No-op if the backend
    didn't return a log_id (e.g. logging disabled)."""
    if not log_id:
        return
    sent_key = f"fb_sent_{log_id}"
    left, right = st.columns([1, 5])
    with left:
        choice = st.feedback("thumbs", key=f"fb_{log_id}")
    if choice is not None and st.session_state.get(sent_key) != choice:
        _send_feedback(log_id, rating=1 if choice == 1 else -1)
        st.session_state[sent_key] = choice
        st.toast("Feedback saved — thanks!")
    with right:
        with st.popover("💬 note"):
            note = st.text_area(
                "note", key=f"note_{log_id}", label_visibility="collapsed",
                placeholder="Optional: accuracy issue, tone, missing info, safety concern…",
            )
            if st.button("Send note", key=f"notebtn_{log_id}") and note.strip():
                _send_feedback(log_id, note=note)
                st.toast("Note saved — thanks!")


# --- replay history ---
for message in st.session_state.messages:
    avatar = USER_AVATAR if message["role"] == "user" else BOT_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        if message["role"] == "assistant" and is_crisis(message):
            st.error(message["text"], icon="🆘")
        else:
            st.markdown(message["text"])
        render_paths(message.get("paths_used"))
        if message["role"] == "assistant":
            feedback_row(message.get("log_id"))

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
                    json={
                        "question": question,
                        "thread_id": st.session_state.thread_id,
                        "country": st.session_state.get("country") or None,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
                answer = data.get("answer", "Sorry, I couldn't get a response.")
                paths_used = data.get("paths_used", [])
                kind = data.get("kind", "answer")
                log_id = data.get("log_id")
            except Exception:
                answer = "Sorry, the assistant is temporarily unavailable. Please try again."
                paths_used, kind, log_id = [], "answer", None

        bot_msg = {"role": "assistant", "text": answer, "paths_used": paths_used,
                   "kind": kind, "log_id": log_id}
        if is_crisis(bot_msg):
            st.error(answer, icon="🆘")
        else:
            st.markdown(answer)
        render_paths(paths_used)
        feedback_row(log_id)

    st.session_state.messages.append(bot_msg)
