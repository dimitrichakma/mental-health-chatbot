import json
import os
import uuid

import requests
import streamlit as st

from src.crisis_resources import CRISIS_RESOURCES, resolve_country


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


# --- session state ---
# thread_id lives in the URL (?t=...) so a page refresh / dropped connection
# keeps the same conversation instead of silently starting a new one - the
# backend's memory (Postgres) already outlives the browser session, the UI
# just wasn't asking for it back.
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


# crisis-helpline country: auto-detected from the browser's own Accept-Language
# (no picker, no IP geolocation) - but that only reflects browser/OS language,
# not physical location, so it's wrong for e.g. an English-locale browser
# outside the US. Detected here (not just in the backend) so the sidebar can
# show what was picked and offer a one-click override.
try:
    _accept_language = st.context.headers.get("Accept-Language")
except Exception:
    _accept_language = None
_detected_country = resolve_country(_accept_language)
_COUNTRY_NAMES = {"": f"Auto-detect"
                  + (f" ({CRISIS_RESOURCES[_detected_country][0]})" if _detected_country else "")}
_COUNTRY_NAMES.update({code: entry[0] for code, entry in CRISIS_RESOURCES.items()})


# --- sidebar ---
with st.sidebar:
    st.subheader("CBT & Mental Health Chatbot")
    st.caption("Hybrid graph + vector retrieval, corrective-retrieval router, "
               "LangGraph agent with memory, web-search fallback.")

    online = backend_online()
    st.markdown(f"**Status:** {'🟢 ready' if online else '🔴 unavailable'}")

    st.divider()
    st.selectbox(
        "Country (for crisis helplines)",
        options=list(_COUNTRY_NAMES),
        format_func=lambda c: _COUNTRY_NAMES[c],
        key="country_override",
        help="Auto-detected from your browser language. If a crisis message ever "
             "shows the wrong country's helplines, pick the right one here.",
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
        st.query_params["t"] = st.session_state.thread_id
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
        # only set when the sidebar override isn't "Auto-detect"
        "country": st.session_state.get("country_override") or None,
    }

    # requests.post runs on the Streamlit server, not in the visitor's browser -
    # forward the browser's own Accept-Language so the backend can localize
    # crisis helplines automatically when there's no override above.
    request_headers = {"Accept-Language": _accept_language} if _accept_language else {}

    with st.chat_message("assistant", avatar=BOT_AVATAR):
        meta = {"kind": "answer", "paths_used": [], "log_id": None}
        answer = ""
        box = st.empty()
        box.markdown("_Thinking through the knowledge base and graph…_")

        def render(text, final=False):
            if meta["kind"] == "crisis":
                box.error(text, icon="🆘")
            else:
                box.markdown(text if final else text + " ▌")

        try:
            with requests.post(
                f"{BACKEND_URL}/chat/stream", json=payload, headers=request_headers,
                stream=True, timeout=120,
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
