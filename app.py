import json
import random
import sqlite3
import string
import uuid
from datetime import datetime, timezone

import streamlit as st

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


# ----------------------------
# Helpers
# ----------------------------
@st.cache_data
def load_cards():
    with open("data/cards.json", "r", encoding="utf-8") as f:
        cards = json.load(f)

    for c in cards:
        assert "id" in c and "name" in c and "attributes" in c

        for k in RULES.keys():
            if k not in c["attributes"]:
                c["attributes"][k] = None

        if "image" not in c:
            c["image"] = None

    return cards


def inject_mobile_styles():
    st.markdown(
        """
        <style>
            .main .block-container {
                max-width: 780px;
                padding-top: 1.25rem;
                padding-bottom: 5.5rem;
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
                padding: 0.6rem 0.8rem;
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
            @media (max-width: 768px) {
                .main .block-container {
                    padding-left: 1rem;
                    padding-right: 1rem;
                }
                img {
                    border-radius: 14px;
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
    """Restart cards/round flow while keeping room settings and claimed seats."""
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


def main():
    inject_mobile_styles()
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
        with st.form("create_room"):
            num_players = st.selectbox("Number of players", [2, 3, 4], index=1)
            max_players = min(8, len(load_cards()))
            num_players = st.number_input(
                "Number of players",
                min_value=2,
                max_value=max_players,
                value=min(4, max_players),
                step=1,
                help="Host can choose how many players join this room.",
            )
            num_players = int(num_players)
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
    state = load_room_state(room_id)
    if state is None:
        st.error("This room no longer exists.")
        if st.button("Back to lobby"):
            params.clear()
            params["client"] = client_id
            st.rerun()
        st.stop()

    st.markdown(
        f"<div class='share-box'><strong>Room code:</strong> {room_id}<br/>Share this URL with friends to join this match.</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Last sync (UTC): {state.get('updated_at', state.get('created_at', 'unknown'))}")

    if st.button("🔄 Refresh room state"):
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
        top_card = active_player["deck"][0]
        st.write(f"**Top card in play:** {top_card['name']}")
        if top_card.get("image"):
            st.image(f"assets/images/{top_card['image']}", use_container_width=True)

        if is_my_turn:
            st.markdown("**Choose an attribute:**")
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
                    st.warning("State changed, please refresh.")
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
            st.info("Waiting for the active player to choose an attribute.")

    elif state["phase"] == "reveal":
        chosen_attr = state["chosen_attr"]
        st.markdown(f"### Reveal — Attribute: **{DISPLAY.get(chosen_attr, chosen_attr)}**")

        played_items = list(state["played"].items())
        use_mobile_layout = state.get("mobile_layout", True)

        if use_mobile_layout:
            for pi, card in played_items:
                pname = state["players"][int(pi)]["name"]
                val = card["attributes"].get(chosen_attr)
                with st.container(border=True):
                    st.markdown(f"#### {pname}")
                    st.write(f"**{card['name']}**")
                    st.write(f"**{DISPLAY.get(chosen_attr, chosen_attr)}:** {val if val is not None else 'N/A'}")
                    if card.get("image"):
                        st.image(f"assets/images/{card['image']}", use_container_width=True)
        else:
            cols = st.columns(len(played_items))
            for col, (pi, card) in zip(cols, played_items):
                pname = state["players"][int(pi)]["name"]
                val = card["attributes"].get(chosen_attr)
                with col:
                    st.markdown(f"#### {pname}")
                    st.write(f"**{card['name']}**")
                    st.write(f"**{DISPLAY.get(chosen_attr, chosen_attr)}:** {val if val is not None else 'N/A'}")
                    if card.get("image"):
                        st.image(f"assets/images/{card['image']}", use_container_width=True)

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
            st.info("Waiting for active player to continue.")


if __name__ == "__main__":
    main()
