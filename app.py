import base64
import json
import random
import sqlite3
import string
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh  # ✅ FIXED (use streamlit-autorefresh)


# ----------------------------
# Config
# ----------------------------
st.set_page_config(page_title="Top Trumps – Hypercars", layout="centered")

RULES = {
    "top_speed": "higher",
    "acceleration": "lower",
    "horsepower": "higher",
    "weight": "lower",
    "engine_size": "higher",
    "price": "higher",
    "rpm": "higher",
    "release_year": "lower",  # older year wins
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
    """Return a data URI for assets/images/<rel_path>. None if missing."""
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
            .main .block-container {
                max-width: 980px;
                padding-top: 1.0rem;
                padding-bottom: 5.0rem;
            }

            .stButton > button {
                width: 100%;
                min-height: 3rem;
                border-radius: 0.75rem;
                font-size: 1rem;
                font-weight: 600;
            }

            .metric-chip {
                background: #f2f4f8;
                border-radius: 12px;
                padding: 0.55rem 0.7rem;
                margin-bottom: 0.5rem;
                text-align: center;
                border: 1px solid #d6d9df;
            }

            .share-box {
                background: #eff7ff;
                border: 1px solid #b7d5ff;
                border-radius: 10px;
                padding: 0.7rem;
                margin-bottom: 0.8rem;
                font-size: 0.95rem;
            }

            /* --- Compact card row --- */
            .tt-row {
                display: flex;
                gap: 12px;
                overflow-x: auto;
                padding: 8px 2px 12px 2px;
                align-items: stretch;
                scroll-snap-type: x mandatory;
            }
            .tt-row::-webkit-scrollbar { height: 10px; }
            .tt-row::-webkit-scrollbar-thumb { background: #cfd6e4; border-radius: 10px; }

            .tt-card {
                width: 200px;
                min-width: 200px;
                background: #ffffff;
                border: 1px solid #d6d9df;
                border-radius: 14px;
                padding: 10px;
                box-shadow: 0 1px 6px rgba(16, 24, 40, 0.06);
                scroll-snap-align: start;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }
            .tt-card.active {
                border: 3px solid #ff2d2d;  /* red frame */
            }

            .tt-name {
                font-weight: 800;
                font-size: 0.98rem;
                line-height: 1.2;
                margin: 0;
            }
            .tt-player {
                font-weight: 700;
                font-size: 0.9rem;
                opacity: 0.85;
                margin: 0;
            }
            .tt-img {
                width: 100%;
                height: 118px;
                object-fit: cover;
                border-radius: 12px;
                border: 1px solid #eef1f6;
            }
            .tt-attr {
                font-size: 0.9rem;
                line-height: 1.25;
                background: #f7f8fb;
                border: 1px solid #e6e9f2;
                border-radius: 12px;
                padding: 8px;
            }
            .tt-attr b { font-weight: 800; }

            @media (max-width: 768px) {
                .main .block-container {
                    padding-left: 1rem;
                    padding-right: 1rem;
                }
                .tt-card {
                    width: 175px;
                    min-width: 175px;
                }
                .tt-img {
                    height: 105px;
                }
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
    values = []
    for pi, card in card_by_player.items():
        v = card["attributes"].get(attribute, None)
        values.append((pi, v))

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

    if len(winners) == 1:
        return winners[0]
    return None


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


def render_scoreboard(state):
    total_cards = sum(len(p["deck"]) for p in state["players"]) + len(state.get("pot", []))
    st.markdown("### Scoreboard")
    st.markdown(
        f"""
        <div class="metric-chip"><strong>Total cards in game:</strong> {total_cards}</div>
        <div class="metric-chip"><strong>Round:</strong> {state['round']} · <strong>Phase:</strong> {state['phase'].title()}</div>
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


def _card_html(player_name: str, card: dict, highlight: bool, attr_key: str | None, show_attr: bool) -> str:
    cls = "tt-card active" if highlight else "tt-card"
    img_uri = _img_as_data_uri(card.get("image"))
    img_html = f"<img class='tt-img' src='{img_uri}' />" if img_uri else ""
    attr_html = ""
    if show_attr and attr_key:
        val = card["attributes"].get(attr_key)
        disp = DISPLAY.get(attr_key, attr_key)
        vtxt = "N/A" if val is None else str(val)
        attr_html = f"<div class='tt-attr'><b>{disp}:</b> {vtxt}</div>"

    return f"""
        <div class="{cls}">
            <p class="tt-player">{player_name}</p>
            <p class="tt-name">{card.get('name','(unknown)')}</p>
            {img_html}
            {attr_html}
        </div>
    """


def render_round_cards_horizontal(state, card_by_player: dict[int, dict], chosen_attr: str | None, show_attr: bool):
    items = []
    for pi, card in card_by_player.items():
        pname = state["players"][int(pi)]["name"]
        highlight = int(pi) == int(state["active"])
        items.append(_card_html(pname, card, highlight, chosen_attr, show_attr))
    st.markdown("<div class='tt-row'>" + "\n".join(items) + "</div>", unsafe_allow_html=True)


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
            mobile_layout = st.toggle("Use compact mobile reveal layout", value=True)
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

    room_id = str(room_id).upper()

    # ✅ Auto-refresh for all players
    st_autorefresh(interval=1500, key="room_poll")

    state = load_room_state(room_id)
    if state is None:
        st.error("This room no longer exists.")
        if st.button("Back to lobby"):
            params.clear()
            params["client"] = client_id
            st.rerun()
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

    with st.sidebar:
        if st.button("🔄 Force refresh now"):
            st.rerun()

    my_idx = get_my_player_index(state, client_id)

    if my_idx is None:
        taken = set(state.get("seat_claims", {}).values())
        available = [i for i in range(len(state["players"])) if i not in taken]
        st.info("Choose an available seat to play. You can spectate if all seats are taken.")
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
                    st.success("Seat claimed.")
                    st.rerun()
                else:
                    st.warning("That seat was just taken. Please pick another.")
        else:
            st.warning("All seats are currently taken. You are in spectator mode.")
    else:
        st.success(f"You are {state['players'][my_idx]['name']}.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Leave my seat"):
                latest = load_room_state(room_id)
                if latest and release_player_slot(latest, client_id):
                    save_room_state(room_id, latest)
                    st.info("You left your seat.")
                    st.rerun()
        with c2:
            is_owner = state.get("owner_client_id") == client_id
            if st.button("Reset match", disabled=not is_owner):
                latest = load_room_state(room_id)
                if latest and latest.get("owner_client_id") == client_id:
                    reset_match(latest)
                    save_room_state(room_id, latest)
                    st.success("Match reset. Same room and seats kept.")
                    st.rerun()
            if not is_owner:
                st.caption("Only the room creator can reset.")

    with st.expander("Game stats", expanded=True):
        render_scoreboard(state)

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

    st.subheader(f"Round {state['round']} — {active_player['name']}'s turn")

    if state["phase"] == "choose":
        round_cards = {}
        for pi in alive:
            if len(state["players"][pi]["deck"]) > 0:
                round_cards[pi] = state["players"][pi]["deck"][0]

        st.markdown("### Cards in this round")
        render_round_cards_horizontal(state, round_cards, chosen_attr=None, show_attr=False)

        if is_my_turn:
            st.markdown("### Choose an attribute")
            attr_keys = list(RULES.keys())
            chosen = st.radio(
                "Attribute",
                options=attr_keys,
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
                    st.warning("State changed, please wait for auto-refresh or force refresh.")
                    st.stop()

                played = {}
                for pi in alive_now:
                    played[pi] = latest["players"][pi]["deck"].pop(0)

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
        st.markdown(f"### Reveal — Attribute: **{DISPLAY.get(chosen_attr, chosen_attr)}**")

        played_items = {int(pi): card for pi, card in state["played"].items()}
        render_round_cards_horizontal(state, played_items, chosen_attr=chosen_attr, show_attr=True)

        st.info(state.get("outcome_text", "Round complete."))

        if is_my_turn:
            if st.button("Next round"):
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
        else:
            st.info("Waiting for active player to continue (auto-refresh is on).")


if __name__ == "__main__":
    main()
