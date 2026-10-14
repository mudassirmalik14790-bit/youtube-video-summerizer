# 🎬 YouTube Video Summarizer

Paste a YouTube link and get a summary with timestamps, chapters and key takeaways.
Then ask follow-up questions about the video. Built with **Streamlit** and a **Gemini Flash** model.

## Features
- Works with watch, youtu.be, Shorts, embed and live links
- Three summary styles: Detailed, Concise, Study notes
- Timestamped key points and chapters
- Two input modes: paste a YouTube link, or paste the transcript text yourself
- Chat box to ask questions about the video
- Download the summary as Markdown

## Run locally
```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
Get a free Gemini API key at https://aistudio.google.com/apikey and paste it in the sidebar.
To avoid pasting it each time, create `.streamlit/secrets.toml` (never commit this file):
```toml
GEMINI_API_KEY = "your-key-here"
```

## Deploy on Streamlit Community Cloud
1. Push this repo to GitHub.
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, choose the repo, branch `main`, main file `app.py`.
4. Open **Advanced settings → Secrets** and add `GEMINI_API_KEY = "your-key-here"`.
5. Click **Deploy**.

## Known limitation: YouTube blocking cloud IPs
YouTube often blocks transcript requests from cloud servers such as Streamlit Cloud.
If you see a "blocking requests" error on the deployed app, switch to **Paste transcript**:
on YouTube click "...more" under the video, then "Show transcript", copy the text and paste it
into the app. Running the app locally also works with links, since home connections are rarely blocked.
You can also add a proxy in your secrets:
```toml
YT_PROXY_URL = "http://user:password@proxy-host:port"
```

## Notes
- Only videos that have captions (manual or auto-generated) can be summarized.
- The model defaults to `gemini-flash-latest`. You can change it in the sidebar.
- Very long videos are truncated to fit the model's limits.
