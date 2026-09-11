import json
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
    "naive_rag": ("📚", "knowledge base"),
    "graph_rag": ("🕸️", "concept graph"),
    "both": ("🔗", "knowledge base + graph"),
    "web_fallback": ("🌐", "web search"),
    "no_answer": ("❓", "no source found"),
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
      /* -------- layout -------- */
      .block-container { padding-top: 2rem; padding-bottom: 6rem; max-width: 880px; }

      /* -------- header -------- */
      .app-header {
        display: flex; align-items: center; gap: 0.9rem;
        border-radius: 18px;
        padding: 1.3rem 1.6rem;
        margin-bottom: 0.5rem;
        background: linear-gradient(135deg, #1f6f5c 0%, #3a8fb7 100%);
        box-shadow: 0 6px 20px -8px rgba(31,111,92,0.55);
        color: #fff;
      }
      .app-header .badge {
        flex: none; width: 46px; height: 46px; border-radius: 13px;
        background: rgba(255,255,255,0.18); display: flex; align-items: center;
        justify-content: center; font-size: 1.5rem;
      }
      .app-header h1 { margin: 0; font-size: 1.35rem; font-weight: 700; line-height: 1.25; }
      .app-header p  { margin: 0.25rem 0 0; opacity: 0.92; font-size: 0.88rem; }

      .disclaimer {
        display: flex; align-items: flex-start; gap: 0.5rem;
        font-size: 0.8rem; color: var(--text-color); opacity: 0.65;
        background: var(--secondary-background-color);
        border-radius: 10px; padding: 0.55rem 0.8rem;
        margin: 0.7rem 0 1.3rem;
      }
      .disclaimer .ic { opacity: 1; flex: none; }

      /* -------- sidebar -------- */
      section[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
      .status-pill {
        display: inline-flex; align-items: center; gap: 0.4rem;
        padding: 0.3rem 0.75rem; border-radius: 999px;
        font-size: 0.82rem; font-weight: 600;
      }
      .status-ready { background: rgba(34,197,94,0.15); color: #15803d; }
      .status-down  { background: rgba(239,68,68,0.15); color: #b91c1c; }

      section[data-testid="stSidebar"] button {
        border-radius: 10px !important;
        text-align: left !important;
        justify-content: flex-start !important;
      }

      /* -------- source chips -------- */
      .path-row { margin-top: 0.55rem; font-size: 0.78rem; opacity: 0.75; }
      .path-chip {
        display: inline-block; margin: 0.15rem 0.3rem 0 0; padding: 0.15rem 0.65rem;
        border-radius: 999px; background: rgba(58,143,183,0.14);
        color: #2b6f8c; font-weight: 600; font-size: 0.74rem;
      }

      /* -------- chat bubbles -------- */
      [data-testid="stChatMessage"] {
        border-radius: 16px; padding: 0.6rem 1rem; margin-bottom: 0.5rem;
        border: 1px solid rgba(128,128,128,0.14);
      }
      [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        background: var(--secondary-background-color);
      }

      /* -------- example chips (main empty state) -------- */
      .welcome-panel {
        text-align: center; padding: 1.6rem 1rem 0.4rem; opacity: 0.9;
      }
      .welcome-panel .big { font-size: 2rem; margin-bottom: 0.2rem; }
      .welcome-panel h3 { margin: 0.2rem 0 0.2rem; font-size: 1.1rem; }
      .welcome-panel p { font-size: 0.85rem; opacity: 0.7; margin: 0 0 0.8rem; }

      /* -------- thinking indicator -------- */
      .thinking { opacity: 0.7; font-style: italic; }
      .thinking::after {
        content: '\\2026'; display: inline-block; width: 1em; overflow: hidden;
        animation: dots 1.1s steps(4, end) infinite;
      }
      @keyframes dots { 0% { width: 0; } 100% { width: 1.1em; } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-header">
      <div class="badge">🌿</div>
      <div>
        <h1>CBT &amp; Mental Health Chatbot</h1>
        <p>Ask about cognitive behavioral therapy, common mental-health conditions, and coping skills —
           answered from a curated knowledge base and concept graph.</p>
      </div>
    </div>
    <div class="disclaimer">
      <span class="ic">ℹ️</span>
      <span>Educational project, not medical advice or a substitute for professional care.
      If you are in crisis, contact a local crisis line or emergency services.</span>
    </div>
    """,
    unsafe_allow_html=True,
)

def _fetch_history(thread_id):
    """Restore a conversation from the backend's LangGraph checkpoint (Postgres)
    after a page refresh / lost session wipes the browser-side state. Only text
    survives server-side (no paths_used/log_id per turn), so restored assistant
    messages show without source chips or feedback buttons."""
    try:
        r = requests.get(f"{BACKEND_URL}/history/{thread_id}", timeout=5)
        r.raise_for_status()
        restored = []
        for turn in r.json().get("chat_history", []):
            restored.append({"role": "user", "text": turn["question"]})
            restored.append({"role": "assistant", "text": turn["answer"],
                              "paths_used": [], "kind": None, "log_id": None})
        return restored
    except Exception:
        return []


def _fetch_threads(device_id):
    """The sidebar's past-conversations list for this device. Best-effort -
    an empty list just means the sidebar section doesn't render."""
    try:
        r = requests.get(f"{BACKEND_URL}/threads", params={"device_id": device_id}, timeout=5)
        r.raise_for_status()
        return r.json().get("threads", [])
    except Exception:
        return []


# --- session state ---
# thread_id and device_id live in the URL (?t=...&d=...) so a page refresh /
# dropped connection keeps the same conversation instead of silently starting
# a new one, and the same "device" keeps seeing its conversation list - the
# backend's memory (Postgres) already outlives the browser session, the UI
# just wasn't asking for it back. There's no login, so device_id is just an
# anonymous id scoped to this browser/bookmarked link, not a real account.
if "device_id" not in st.session_state:
    st.session_state.device_id = st.query_params.get("d") or str(uuid.uuid4())
    st.query_params["d"] = st.session_state.device_id
if "thread_id" not in st.session_state:
    from_url = st.query_params.get("t")
    st.session_state.thread_id = from_url or str(uuid.uuid4())
    st.query_params["t"] = st.session_state.thread_id
    st.session_state.messages = _fetch_history(st.session_state.thread_id) if from_url else []
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending" not in st.session_state:
    st.session_state.pending = None


@st.cache_data(ttl=15, show_spinner=False)
def backend_online():
    try:
        return requests.get(f"{BACKEND_URL}/health", timeout=3).ok
    except Exception:
        return False


# crisis-helpline country: detected server-side (see src/geoip.py) from the
# visitor's real public IP - confirmed present via X-Real-Ip / the first hop
# of X-Forwarded-For on this host (Railway's edge forwards it; Streamlit
# Community Cloud never did, only internal 10.x hops).
try:
    _client_ip = st.context.headers.get("X-Real-Ip") or (
        st.context.headers.get("X-Forwarded-For", "").split(",")[0].strip() or None
    )
except Exception:
    _client_ip = None


def _short_title(title, limit=34):
    title = title or "Untitled (naming…)"
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


# --- sidebar ---
with st.sidebar:
    st.subheader("🌿 CBT & Mental Health Chatbot")
    st.caption("Hybrid graph + vector retrieval, corrective-retrieval router, "
               "LangGraph agent with memory, web-search fallback.")

    online = backend_online()
    pill_class = "status-ready" if online else "status-down"
    pill_text = "Ready" if online else "Unavailable"
    dot = "🟢" if online else "🔴"
    st.markdown(f'<span class="status-pill {pill_class}">{dot} {pill_text}</span>',
                unsafe_allow_html=True)

    st.divider()
    if st.button("🗑️  New conversation", use_container_width=True, type="primary"):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.query_params["t"] = st.session_state.thread_id
        st.session_state.pending = None
        st.rerun()

    past = [t for t in _fetch_threads(st.session_state.device_id)
            if t["thread_id"] != st.session_state.thread_id]
    if past:
        st.markdown("**Conversations**")
        for t in past:
            if st.button(_short_title(t["title"]), use_container_width=True,
                         key=f"thread_{t['thread_id']}", help=t["title"] or None):
                st.session_state.thread_id = t["thread_id"]
                st.query_params["t"] = t["thread_id"]
                st.session_state.messages = _fetch_history(t["thread_id"])
                st.session_state.pending = None
                st.rerun()

    # Only shown once a conversation is underway - on a fresh/empty one the
    # main-area welcome panel already offers the same examples, and showing
    # both at once just reads as duplicated content.
    if st.session_state.messages:
        st.divider()
        st.markdown("**Try an example**")
        for ex in EXAMPLES:
            if st.button(f"💬 {ex}", use_container_width=True, key=f"ex_{ex}"):
                st.session_state.pending = ex

    st.divider()
    st.caption(f"{len(st.session_state.messages) // 2} exchanges · "
               f"thread `{st.session_state.thread_id[:8]}`")


def render_paths(paths_used):
    if not paths_used:
        return
    chips = "".join(
        f'<span class="path-chip">{PATH_LABELS.get(p, ("", p))[0]} '
        f'{PATH_LABELS.get(p, ("", p))[1]}</span>' for p in paths_used
    )
    st.markdown(f'<div class="path-row">Sources:{chips}</div>', unsafe_allow_html=True)


def is_crisis(message):
    """message is a stored history dict or a fresh {'kind':..., 'text':...}.
    Prefer the backend's explicit kind; fall back to a text heuristic for
    history restored from the server (/history doesn't carry kind) or saved
    before the flag existed. The two phrases below are in every crisis
    response regardless of country (see src/crisis_resources.py), unlike the
    word 'crisis' itself which isn't in every country's helpline list."""
    if message.get("kind"):
        return message["kind"] == "crisis"
    answer = message.get("text", "").lower()
    return "you don't have to handle this alone" in answer and "emergency number" in answer


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
    left, mid, right = st.columns([1, 1, 4])
    with left:
        choice = st.feedback("thumbs", key=f"fb_{log_id}")
    if choice is not None and st.session_state.get(sent_key) != choice:
        _send_feedback(log_id, rating=1 if choice == 1 else -1)
        st.session_state[sent_key] = choice
        st.toast("Feedback saved — thanks!")
    with mid:
        with st.popover("💬"):
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
    st.markdown(
        """
        <div class="welcome-panel">
          <div class="big">🌿</div>
          <h3>What's on your mind?</h3>
          <p>Ask about CBT techniques, mental-health conditions, or coping skills —
             or try one of these:</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLES):
        with cols[i % 2]:
            if st.button(ex, use_container_width=True, key=f"welcome_ex_{ex}"):
                st.session_state.pending = ex
                st.rerun()

# --- input (typed, or an example button from the sidebar/welcome panel) ---
typed = st.chat_input("Ask something about mental health or CBT...", max_chars=2000)
question = typed or st.session_state.pending
st.session_state.pending = None

if question:
    st.session_state.messages.append({"role": "user", "text": question})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(question)

    payload = {
        "question": question,
        "thread_id": st.session_state.thread_id,
        "device_id": st.session_state.device_id,
        # crisis-helpline localization signal - the backend resolves country
        # from this (src/geoip.py); no manual override in the UI anymore
        "client_ip": _client_ip,
    }

    with st.chat_message("assistant", avatar=BOT_AVATAR):
        meta = {"kind": "answer", "paths_used": [], "log_id": None}
        answer = ""
        box = st.empty()
        box.markdown('<span class="thinking">Thinking through the knowledge base and graph</span>',
                     unsafe_allow_html=True)

        def render(text, final=False):
            if meta["kind"] == "crisis":
                box.error(text, icon="🆘")
            else:
                box.markdown(text if final else text + " ▌")

        try:
            with requests.post(
                f"{BACKEND_URL}/chat/stream", json=payload, stream=True, timeout=120,
            ) as resp:
                resp.raise_for_status()
                for raw in resp.iter_lines():
                    if not raw or not raw.startswith(b"data: "):
                        continue
                    evt = json.loads(raw[6:])
                    t = evt.get("type")
                    if t == "meta":
                        meta["kind"] = evt.get("kind", meta["kind"])
                        if "paths_used" in evt:
                            meta["paths_used"] = evt["paths_used"]
                    elif t == "token":
                        answer += evt["text"]
                        render(answer)
                    elif t == "done":
                        meta.update({k: evt[k] for k in ("log_id", "kind", "paths_used")
                                    if k in evt})
                    elif t == "error":
                        raise RuntimeError(evt.get("text", "stream error"))
        except Exception:
            answer = answer or "Sorry, the assistant is temporarily unavailable. Please try again."

        render(answer, final=True)
        render_paths(meta["paths_used"])
        feedback_row(meta["log_id"])

    st.session_state.messages.append(
        {"role": "assistant", "text": answer, "paths_used": meta["paths_used"],
         "kind": meta["kind"], "log_id": meta["log_id"]}
    )
