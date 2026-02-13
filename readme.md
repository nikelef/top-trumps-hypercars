# Top Trumps – Hypercars

A digital Top Trumps-style card game built with Streamlit.

## What's improved

###  Mobile and iOS-friendly gameplay
- Touch-friendly controls (large tap targets for main actions).
- Responsive card/media layout optimized for iPhone/iPad and small screens.
- Optional compact reveal mode that stacks cards vertically.

### ✅ Remote multiplayer rooms (shared link)
- Create an **online room** with a short room code.
- Share the same URL with friends so everyone joins the same match.
- Players can claim an available seat and play from separate laptops/phones.
- Room state is persisted in SQLite so each browser sees synchronized game progress.
- Room state now stores a last-updated timestamp to help players know when to refresh.
- Players can **leave their seat** to let another friend take over.
- Room creator can **reset the match** (same room/seats, freshly shuffled decks).

## Requirements
- Python 3.10+
- Streamlit

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
