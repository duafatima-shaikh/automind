# Deploy AutoMind on Streamlit (via GitHub)

## 1. Test it on your computer
```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```
Opens at http://localhost:8501.

## 2. Upload to GitHub
Create an empty repository on github.com (for example `automind`), then in the project folder:
```bash
git init
git add .
git commit -m "AutoMind Streamlit version"
git branch -M main
git remote add origin https://github.com/<your-username>/automind.git
git push -u origin main
```
`.gitignore` already keeps `data/`, `.env` and `.streamlit/secrets.toml` out of GitHub, so no keys are uploaded.

## 3. Deploy on Streamlit Community Cloud
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** -> **Deploy a public app from GitHub**.
3. Repository: `<your-username>/automind`, Branch: `main`, Main file path: `streamlit_app.py`.
4. (Optional) **Advanced settings** -> pick Python 3.12, and paste your secrets (see `.streamlit/secrets.toml.example`).
5. Click **Deploy**. The first build takes a few minutes.

## Notes
* Each visitor gets a private, temporary library. Files disappear when the browser session ends or the app restarts.
* Without a key the app runs in basic mode (quotes sentences from your documents, offline). Add a free Gemini or Groq key in Settings for real answers, Urdu/Sindhi output and better quizzes.
* Search uses the small offline encoder on Streamlit Cloud (memory limit about 1 GB). Keyword search is strong; cross-language search needs a real embedding model, which is better run locally.
* Old .doc/.ppt/.xls files need LibreOffice and are not supported on Streamlit Cloud: save them as .docx/.pptx/.xlsx.
* Scanned PDFs and images need OCR: enable the two optional lines in `requirements.txt`.
* The FastAPI version (`uvicorn automind.api.main:app`) still works unchanged.
