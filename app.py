import base64
import json
import random
import sqlite3
import string
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh


# ----------------------------
# Config
# ----------------------------
st.set_page_config(page_title="Top Trumps – Hypercars", layout="wide")

RULES = {
    "top_speed": "higher",
    "acceleration": "lower",   # ✅ lower seconds wins
    "horsepower": "higher",
    "weight": "lower",         # ✅ lower weight wins
    "engine_size": "higher",
    "price": "higher",         # ✅ higher price wins
    "rpm": "higher",
    "release_year": "lower",   # older year wins
}

DISPLAY = {
    "top_speed": "Top Speed (km/h)",
    "acceleration": "0–100 (s)",
    "horsepower": "Horsepower (hp)",
    "weight": "Weight (kg)",
    "engine_size": "Engine Size (L)",
    "price": "Price (EUR)",
    "rpm": "RPM",
    "release_year": "Release Year (older wins)",
}

DB_PATH = "game_state.db"
ASSETS_DIR = Path("assets/images")
DATA_CARDS_PATH = Path("data/cards.json")


# ----------------------------
# Helpers
# ----------------------------
@st.cache_data
def load_cards():
    with open(DATA_CARDS_PATH, "r", encoding="utf-8") as f:
        cards = json.load(f)

    for c in cards:
        assert "id" in c and "name" in c and "attributes" in c
        for k in RULES.keys():
            if k not in c["attributes"]:
                c["attributes"][k] = None
        if "image" not in c:
            c["image"] = None
    return cards


@st.cache_data(show_spinner=False)
def _img_as_data_uri(rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    p = ASSETS_DIR / rel_path
    if not p.exists() or not p.is_file():
        return None
    ext = p.suffix.lower().lstrip(".")
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        return None
    mime = "image/jpeg" if ext in {"jpg", "jpeg"} else f"image/{ext}"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def inject_styles():
    st.markdown(
        """
        <style>
            .main .block-container{
                max-width: 2100px;
                padding-top: 0.6rem;
                padding-bottom: 3.0rem;
            }

            /* Left stats panel stays visible */
            .tt-stats{
                position: sticky;
                top: 0.6rem;
            }

            .stButton > button{
                width: 100%;
                min-height: 3.0rem;
                border-radius: 0.9rem;
                font-size: 1.0rem;
                font-weight: 650;
            }

            .metric-chip{
                background: #f2f4f8;
                border-radius: 14px;
                padding: 0.70rem 0.95rem;
                margin-bottom: 0.6rem;
                text-align: center;
                border: 1px solid #d6d9df;
                font-size: 1.00rem;
            }

            .share-box{
                background: #eff7ff;
                border: 1px solid #b7d5ff;
                border-radius: 12px;
                padding: 0.95rem 1.0rem;
                margin-bottom: 0.9rem;
                font-size: 1.02rem;
            }

            /* Row: no horizontal scroll; wrap when needed */
            .tt-row{
                display: flex;
                gap: 18px;
                overflow-x: hidden;
                overflow-y: visible;
                padding: 10px 6px 16px 6px;
                align-items: stretch;
                flex-wrap: nowrap;
            }

            /* Cards */
            .tt-card{
                flex: 1 1 0;
                max-width: 1100px;
                background: #ffffff;
                border: 2px solid #d6d9df;
                border-radius: 22px;
                padding: 18px;
                box-shadow: 0 3px 14px rgba(16, 24, 40, 0.10);
                display: flex;
                flex-direction: column;
                gap: 14px;
                position: relative;
                min-width: 380px;
            }
            .tt-card.active{
                border: 6px solid #ff2d2d;
            }

            /* Hidden cards */
            .tt-card.hidden{
                opacity: 0.35;
                filter: blur(1.3px) grayscale(0.5);
            }
            .tt-card.hidden::after{
                content: "HIDDEN";
                position: absolute;
                inset: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2.4rem;
                font-weight: 950;
                letter-spacing: 0.14em;
                color: rgba(20, 20, 20, 0.55);
                background: rgba(250, 250, 250, 0.35);
                border-radius: 22px;
            }

            .tt-player{
                font-weight: 900;
                font-size: 1.25rem;
                opacity: 0.85;
                margin: 0;
            }
            .tt-name{
                font-weight: 950;
                font-size: 1.55rem;
                line-height: 1.15;
                margin: 0;
            }

            /* Big photo */
            .tt-img{
                width: 100%;
                height: 640px;
                object-fit: cover;
                border-radius: 18px;
                border: 1px solid #eef1f6;
            }

            @media (max-width: 1400px){
                .tt-img{ height: 520px; }
            }

            @media (max-width: 1200px){
                /* on smaller screens, allow wrap and remove sticky */
                .tt-row{ flex-wrap: wrap; }
                .tt-stats{ position: static; }
                .tt-card{ min-width: 320px; }
                .tt-img{ height: 440px; }
            }

            @media (max-width: 768px){
                .tt-row{ flex-wrap: wrap; }
                .tt-card{ min-width: 300px; }
                .tt-img{ height: 360px; }
                .tt-name{ font-size: 1.35rem; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def now_iso():
    return datetime.now(tz=timezone.utc).isoformat()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def save_room_state(room_id, state):
    state["updated_at"] = now_iso()
    payload = json.dumps(state)
    ts = state["updated_at"]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO rooms(room_id, state_json, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET
                state_json=excluded.state_json,
                updated_at=excluded.updated_at
            """,
            (room_id, payload, ts, ts),
        )


def load_room_state(room_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT state_json FROM rooms WHERE room_id = ?", (room_id,)
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def generate_room_id(length=6):
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(40):
        room_id = "".join(random.choice(alphabet) for _ in range(length))
        if load_room_state(room_id) is None:
            return room_id
    raise RuntimeError("Could not generate room id")


def alive_player_indexes(state):
    return [i for i, p in enumerate(state["players"]) if len(p["deck"]) > 0]


def compare_cards(card_by_player, attribute):
    rule = RULES[attribute]
    values = [(pi, card["attributes"].get(attribute, None)) for pi, card in card_by_player.items()]

    if all(v is None for _, v in values):
        return None

    scored = []
    for pi, v in values:
        if v is None:
            score = float("-inf") if rule == "higher" else float("inf")
        else:
            score = v
        scored.append((pi, score))

    if rule == "higher":
        best = max(score for _, score in scored)
        winners = [pi for pi, score in scored if score == best]
    else:
        best = min(score for _, score in scored)
        winners = [pi for pi, score in scored if score == best]

    return winners[0] if len(winners) == 1 else None


def start_new_game(num_players, mobile_layout, owner_client_id):
    cards = load_cards()
    random.shuffle(cards)

    players = [{"name": f"Player {i+1}", "deck": []} for i in range(num_players)]
    for idx, card in enumerate(cards):
        players[idx % num_players]["deck"].append(card)

    return {
        "players": players,
        "active": 0,
        "phase": "choose",
        "chosen_attr": None,
        "played": {},
        "winner": None,
        "round": 1,
        "pot": [],
        "mobile_layout": mobile_layout,
        "outcome_text": "",
        "seat_claims": {owner_client_id: 0},
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "owner_client_id": owner_client_id,
    }


def reset_match(state):
    num_players = len(state["players"])
    cards = load_cards()
    random.shuffle(cards)

    names = [p["name"] for p in state["players"]]
    players = [{"name": names[i], "deck": []} for i in range(num_players)]
    for idx, card in enumerate(cards):
        players[idx % num_players]["deck"].append(card)

    state["players"] = players
    state["active"] = 0
    state["phase"] = "choose"
    state["chosen_attr"] = None
    state["played"] = {}
    state["winner"] = None
    state["round"] = 1
    state["pot"] = []
    state["outcome_text"] = ""
    return state


def render_scoreboard_panel(state):
    total_cards = sum(len(p["deck"]) for p in state["players"]) + len(state.get("pot", []))
    st.markdown("### Scoreboard")
    st.markdown(
        f"""
        <div class="metric-chip"><strong>Total cards:</strong> {total_cards}</div>
        <div class="metric-chip"><strong>Round:</strong> {state['round']}<br/>
        <strong>Phase:</strong> {state['phase'].title()}</div>
        """,
        unsafe_allow_html=True,
    )

    for i, p in enumerate(state["players"]):
        tag = " 👈 Active" if i == state["active"] else ""
        st.markdown(f"- **{p['name']}**: **{len(p['deck'])}** cards{tag}")

    if len(state.get("pot", [])) > 0:
        st.caption(f"Tie pot: {len(state['pot'])} cards")


def claim_player_slot(state, client_id, player_idx, display_name):
    claims = state.get("seat_claims", {})
    if any(idx == player_idx for cid, idx in claims.items() if cid != client_id):
        return False
    claims[client_id] = player_idx
    state["seat_claims"] = claims
    state["players"][player_idx]["name"] = display_name.strip()[:24] or f"Player {player_idx+1}"
    return True


def release_player_slot(state, client_id):
    claims = state.get("seat_claims", {})
    if client_id in claims:
        del claims[client_id]
        state["seat_claims"] = claims
        return True
    return False


def get_my_player_index(state, client_id):
    return state.get("seat_claims", {}).get(client_id)


def _card_html(player_name: str, card: dict, highlight: bool, hidden: bool) -> str:
    cls = "tt-card"
    if highlight:
        cls += " active"
    if hidden:
        cls += " hidden"

    if hidden:
        name_html = "<p class='tt-name'>—</p>"
        img_html = ""
    else:
        name_html = f"<p class='tt-name'>{card.get('name','(unknown)')}</p>"
        img_uri = _img_as_data_uri(card.get("image"))
        img_html = f"<img class='tt-img' src='{img_uri}' />" if img_uri else ""

    html = f"""
    <div class="{cls}">
      <div>
        <p class="tt-player">{player_name}</p>
        {name_html}
      </div>
      {img_html}
    </div>
    """
    return textwrap.dedent(html).strip()


def render_cards_row(state, cards_by_player: dict[int, dict], viewer_idx: int | None, reveal: bool):
    items = []
    for pi, card in cards_by_player.items():
        pname = state["players"][int(pi)]["name"]
        highlight = int(pi) == int(state["active"])

        if reveal:
            hidden = False
        else:
            hidden = not (viewer_idx is not None and int(pi) == int(viewer_idx))

        items.append(_card_html(pname, card, highlight, hidden))

    st.markdown("<div class='tt-row'>" + "".join(items) + "</div>", unsafe_allow_html=True)


def main():
    inject_styles()
    init_db()

    st.title("🏎️ Top Trumps – Hypercars")
    st.caption("Play online with friends from a shared room link, including laptop and mobile browsers.")

    params = st.query_params
    if "client" not in params:
        params["client"] = uuid.uuid4().hex[:10]
    client_id = params["client"]

    room_id = params.get("room")
    st.sidebar.subheader("Online room")

    # Lobby
    if not room_id:
        st.subheader("Create or join an online multiplayer room")

        base_url = getattr(st.context, "url", "").strip()
        if base_url:
            st.markdown(
                f"<div class='share-box'><strong>Tip (Host):</strong> After you create a room, you will get a full share link like:<br/><code>{base_url}?room=ABC123</code></div>",
                unsafe_allow_html=True,
            )

        with st.form("create_room"):
            num_players = st.selectbox("Number of players", [2, 3, 4], index=1)
            mobile_layout = st.toggle("Use compact layout", value=True)
            owner_name = st.text_input("Your name", value="Host")
            create_submitted = st.form_submit_button("Create room")

        join_code = st.text_input("Already have a room code?", value="").strip().upper()
        join_btn = st.button("Join room")

        if create_submitted:
            new_room_id = generate_room_id()
            state = start_new_game(num_players, mobile_layout, client_id)
            state["players"][0]["name"] = owner_name.strip()[:24] or "Host"
            save_room_state(new_room_id, state)
            params["room"] = new_room_id
            st.rerun()

        if join_btn and join_code:
            if load_room_state(join_code) is None:
                st.error("Room not found. Check the code and try again.")
            else:
                params["room"] = join_code
                st.rerun()
        st.stop()

    # In room
    room_id = str(room_id).upper()
    st_autorefresh(interval=1500, key="room_poll")

    state = load_room_state(room_id)
    if state is None:
        st.error("This room no longer exists.")
        st.stop()

    base_url = getattr(st.context, "url", "").strip()
    share_url = f"{base_url}?room={room_id}" if base_url else f"?room={room_id}"

    st.markdown(
        f"""
        <div class='share-box'>
            <strong>Room code:</strong> {room_id}<br/>
            <strong>Share link (send this):</strong><br/>
            <code>{share_url}</code>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Last sync (UTC): {state.get('updated_at', state.get('created_at', 'unknown'))}")

    my_idx = get_my_player_index(state, client_id)

    # Seat selection / spectator
    if my_idx is None:
        taken = set(state.get("seat_claims", {}).values())
        available = [i for i in range(len(state["players"])) if i not in taken]
        st.info("Choose an available seat to play. Spectators cannot see any cards before reveal.")
        if available:
            chosen_slot = st.selectbox(
                "Pick your seat",
                options=available,
                format_func=lambda i: f"Player {i+1} ({state['players'][i]['name']})",
            )
            name = st.text_input("Display name", value=f"Player {chosen_slot+1}")
            if st.button("Claim seat"):
                latest = load_room_state(room_id)
                if latest and claim_player_slot(latest, client_id, chosen_slot, name):
                    save_room_state(room_id, latest)
                    st.rerun()
                else:
                    st.warning("That seat was just taken. Please pick another.")
        else:
            st.warning("All seats are taken. You are in spectator mode.")
        st.stop()

    # Ensure active is alive
    alive = alive_player_indexes(state)
    if len(alive) == 1:
        winner = state["players"][alive[0]]["name"]
        st.balloons()
        st.success(f"Game over — **{winner}** wins!")
        st.stop()

    if state["active"] not in alive:
        state["active"] = alive[0]
        save_room_state(room_id, state)

    active_player = state["players"][state["active"]]
    is_my_turn = my_idx == state["active"]

    # Layout: stats on the LEFT, cards on the RIGHT
    left, right = st.columns([1, 3.2], gap="large")

    with left:
        st.markdown("<div class='tt-stats'>", unsafe_allow_html=True)
        render_scoreboard_panel(state)

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Leave seat"):
                latest = load_room_state(room_id)
                if latest and release_player_slot(latest, client_id):
                    save_room_state(room_id, latest)
                    st.rerun()
        with c2:
            is_owner = state.get("owner_client_id") == client_id
            if st.button("Reset match", disabled=not is_owner):
                latest = load_room_state(room_id)
                if latest and latest.get("owner_client_id") == client_id:
                    reset_match(latest)
                    save_room_state(room_id, latest)
                    st.rerun()
            if not is_owner:
                st.caption("Only host can reset.")
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.subheader(f"Round {state['round']} — {active_player['name']}'s turn")

        if state["phase"] == "choose":
            round_cards = {pi: state["players"][pi]["deck"][0] for pi in alive if state["players"][pi]["deck"]}
            render_cards_row(state, round_cards, viewer_idx=my_idx, reveal=False)

            if is_my_turn:
                st.markdown("### Choose an attribute")
                chosen = st.radio(
                    "Attribute",
                    options=list(RULES.keys()),
                    format_func=lambda k: DISPLAY.get(k, k),
                    index=0,
                )

                if st.button("Play round"):
                    latest = load_room_state(room_id)
                    if latest is None:
                        st.error("Room unavailable.")
                        st.stop()

                    alive_now = alive_player_indexes(latest)
                    if latest["active"] != my_idx or latest["phase"] != "choose":
                        st.warning("State changed, please wait for auto-refresh.")
                        st.stop()

                    played = {pi: latest["players"][pi]["deck"].pop(0) for pi in alive_now}

                    winner = compare_cards(played, chosen)
                    if winner is None:
                        latest["pot"].extend(played.values())
                        idxs = alive_now
                        cur_pos = idxs.index(latest["active"])
                        latest["active"] = idxs[(cur_pos + 1) % len(idxs)]
                        outcome_text = "Tie — cards go to pot."
                    else:
                        winnings = list(played.values()) + latest["pot"]
                        latest["pot"] = []
                        latest["players"][winner]["deck"].extend(winnings)
                        latest["active"] = winner
                        outcome_text = f"{latest['players'][winner]['name']} wins the round!"

                    latest["played"] = played
                    latest["chosen_attr"] = chosen
                    latest["winner"] = winner
                    latest["outcome_text"] = outcome_text
                    latest["phase"] = "reveal"

                    save_room_state(room_id, latest)
                    st.rerun()
            else:
                st.info("Waiting for the active player to choose an attribute (auto-refresh is on).")

        elif state["phase"] == "reveal":
            chosen_attr = state["chosen_attr"]
            st.markdown(f"### Reveal — Chosen attribute: **{DISPLAY.get(chosen_attr, chosen_attr)}**")

            played_items = {int(pi): card for pi, card in state["played"].items()}
            render_cards_row(state, played_items, viewer_idx=my_idx, reveal=True)

            st.info(state.get("outcome_text", "Round complete."))

            if is_my_turn and st.button("Next round"):
                latest = load_room_state(room_id)
                if latest is None:
                    st.error("Room unavailable.")
                    st.stop()
                latest["played"] = {}
                latest["chosen_attr"] = None
                latest["winner"] = None
                latest["outcome_text"] = ""
                latest["phase"] = "choose"
                latest["round"] += 1
                save_room_state(room_id, latest)
                st.rerun()
            elif not is_my_turn:
                st.info("Waiting for active player to continue (auto-refresh is on).")


if __name__ == "__main__":
    main()
