"""YouTube Video Summarizer: Streamlit + Gemini Flash.

Paste a YouTube link, get a summary with timestamps, then ask follow-up questions.
"""

import os
import re

import streamlit as st
from google import genai
from google.genai import types
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)
from youtube_transcript_api.proxies import GenericProxyConfig

DEFAULT_MODEL = "gemini-flash-latest"  # alias that always points to the newest Flash model
MAX_TRANSCRIPT_CHARS = 400_000  # safety cap, well within Flash's context window

STYLES = {
    "Detailed": "Write a thorough summary with sections.",
    "Concise": "Keep everything short: a TL;DR and 5 key points at most.",
    "Study notes": "Format the result as structured study notes with headings, "
    "definitions, and bullet points, plus 5 quiz questions at the end.",
}

st.set_page_config(page_title="YouTube Video Summarizer", page_icon="🎬", layout="wide")


# ---------- Helpers ----------
def get_secret(name: str) -> str:
    """Read a value from Streamlit secrets or environment variables."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass  # no secrets file locally
    return os.getenv(name, "")


def extract_video_id(url: str):
    """Return the 11-character video ID from common YouTube URL formats."""
    url = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    patterns = [
        r"(?:youtube\.com/watch\?(?:.*&)?v=)([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/(?:shorts|embed|live|v)/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_transcript(video_id: str, proxy_url: str):
    """Return (transcript_text, language_name). Raises on failure."""
    proxy = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url) if proxy_url else None
    api = YouTubeTranscriptApi(proxy_config=proxy)

    transcript_list = api.list(video_id)
    try:
        chosen = transcript_list.find_transcript(["en"])
    except NoTranscriptFound:
        chosen = next(iter(transcript_list))  # any language; Gemini can read it

    fetched = chosen.fetch()
    lines = [f"[{fmt_time(s.start)}] {s.text.replace(chr(10), ' ')}" for s in fetched]
    return "\n".join(lines), chosen.language


def friendly_transcript_error(exc: Exception) -> str:
    if isinstance(exc, TranscriptsDisabled):
        return "This video has subtitles turned off, so there is no transcript to summarize."
    if isinstance(exc, NoTranscriptFound):
        return "No transcript was found for this video."
    if isinstance(exc, VideoUnavailable):
        return "This video is unavailable (private, deleted, or region-locked)."
    if isinstance(exc, (IpBlocked, RequestBlocked)):
        return (
            "YouTube is blocking requests from this server's IP address. This is common on "
            "cloud hosts. Try again later, run the app locally, or set a proxy "
            "(see the README)."
        )
    if isinstance(exc, CouldNotRetrieveTranscript):
        cause = getattr(exc, "cause", "") or ""
        return (
            "Could not retrieve the transcript for this video. This usually means the video "
            "has no captions, is age-restricted, or YouTube is blocking this server. "
            f"Technical detail: {type(exc).__name__}. {str(cause).strip()[:300]}"
        )
    return f"Unexpected error while fetching the transcript ({type(exc).__name__}): {str(exc)[:300]}"


def ask_gemini(client, model: str, system: str, prompt: str) -> str:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.3),
    )
    text = response.text
    if not text:
        raise RuntimeError("Gemini returned an empty response (it may have been blocked). Try again.")
    return text


SYSTEM_PROMPT = (
    "You are an expert at summarizing YouTube videos from their transcripts. "
    "Transcript lines start with a [timestamp]. Only use information from the transcript. "
    "If the transcript is auto-generated, tolerate small transcription errors. "
    "Always answer in English."
)


def summary_prompt(transcript: str, style: str) -> str:
    return f"""{STYLES[style]}

Use this structure in Markdown:
## TL;DR
2-3 sentences.
## Key points
Bullets, each starting with its timestamp like **[05:32]**.
## Chapters
A list of "timestamp - chapter title" covering the whole video.
## Takeaways
The most important things a viewer should remember.

TRANSCRIPT:
{transcript}"""


def qa_prompt(transcript: str, question: str) -> str:
    return f"""Answer the question using only the transcript below. Mention relevant timestamps
like [05:32]. If the transcript does not contain the answer, say so.

QUESTION: {question}

TRANSCRIPT:
{transcript}"""


# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input(
        "Gemini API key",
        type="password",
        value=get_secret("GEMINI_API_KEY"),
        help="Get a free key at https://aistudio.google.com/apikey",
    )
    model_name = st.text_input("Model", value=DEFAULT_MODEL)
    style = st.selectbox("Summary style", list(STYLES.keys()))
    st.caption("Your key is only used for this session and is never stored.")

proxy_url = get_secret("YT_PROXY_URL")

# ---------- Main UI ----------
st.title("🎬 YouTube Video Summarizer")
st.write("Paste a YouTube link to get a summary with timestamps, then ask questions about the video.")

url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...")

if st.button("Summarize", type="primary"):
    if not api_key:
        st.error("Please enter your Gemini API key in the sidebar.")
        st.stop()
    video_id = extract_video_id(url) if url else None
    if not video_id:
        st.error("That doesn't look like a valid YouTube link.")
        st.stop()

    try:
        with st.spinner("Fetching transcript..."):
            transcript, language = fetch_transcript(video_id, proxy_url)
    except Exception as exc:  # library raises many specific errors
        st.error(friendly_transcript_error(exc))
        st.stop()

    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS]
        st.warning("This video is very long, so only the first part of the transcript was used.")

    try:
        client = genai.Client(api_key=api_key)
        with st.spinner("Summarizing with Gemini..."):
            summary = ask_gemini(client, model_name, SYSTEM_PROMPT, summary_prompt(transcript, style))
    except Exception as exc:
        st.error(f"Gemini request failed: {exc}")
        st.stop()

    st.session_state.update(
        video_id=video_id, transcript=transcript, language=language, summary=summary, chat=[]
    )

# ---------- Results ----------
if "summary" in st.session_state:
    left, right = st.columns([1, 1.4])
    with left:
        st.video(f"https://www.youtube.com/watch?v={st.session_state['video_id']}")
        st.caption(f"Transcript language: {st.session_state['language']}")
        with st.expander("Show full transcript"):
            st.text(st.session_state["transcript"])
    with right:
        st.markdown(st.session_state["summary"])
        st.download_button(
            "Download summary (.md)",
            st.session_state["summary"],
            file_name=f"summary_{st.session_state['video_id']}.md",
            mime="text/markdown",
        )

    st.divider()
    st.subheader("Ask about this video")
    for role, msg in st.session_state["chat"]:
        with st.chat_message(role):
            st.markdown(msg)

    question = st.chat_input("Ask a question about the video...")
    if question:
        st.session_state["chat"].append(("user", question))
        try:
            client = genai.Client(api_key=api_key)
            answer = ask_gemini(
                client, model_name, SYSTEM_PROMPT, qa_prompt(st.session_state["transcript"], question)
            )
        except Exception as exc:
            answer = f"Sorry, the request failed: {exc}"
        st.session_state["chat"].append(("assistant", answer))
        st.rerun()
