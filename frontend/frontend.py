import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# raw path names from the backend -> friendly labels for the caption
PATH_LABELS = {
    "naive_rag": "knowledge base",
    "graph_rag": "concept graph",
    "both": "knowledge base + concept graph",
    "web_fallback": "web search",
    "no_answer": "no source found",
}

st.title("CBT & Mental Health Chatbot")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())


def render_caption(paths_used):
    if paths_used:
        labels = [PATH_LABELS.get(p, p) for p in paths_used]
        st.caption(f"Answered using: {', '.join(labels)}")


# replay the conversation so far
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["text"])
        render_caption(message.get("paths_used"))

question = st.chat_input("Ask something about mental health or CBT...")

if question:
    st.session_state.messages.append({"role": "user", "text": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
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

        # the safety gate returns a crisis message with no retrieval paths;
        # make it stand out rather than look like a normal answer
        if answer and not paths_used and "crisis line" in answer.lower():
            st.warning(answer)
        else:
            st.markdown(answer)
        render_caption(paths_used)

    st.session_state.messages.append(
        {"role": "assistant", "text": answer, "paths_used": paths_used}
    )
