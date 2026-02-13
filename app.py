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
                max-width: 1280px;
                padding-top: 1.0rem;
                padding-bottom: 5.0rem;
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

            /* ------- Card row (horizontal, scrollable) ------- */
            .tt-row{
                display: flex;
                gap: 16px;
                overflow-x: auto;
                overflow-y: hidden;
                padding: 12px 4px 16px 4px;
                align-items: stretch;
                scroll-snap-type: x mandatory;
            }
            .tt-row::-webkit-scrollbar { height: 10px; }
            .tt-row::-webkit-scrollbar-thumb { background: #cfd6e4; border-radius: 10px; }

            /* ------- BIGGER cards ------- */
            .tt-card{
                width: 420px;                 /* ✅ bigger desktop */
                min-width: 420px;
                background: #ffffff;
                border: 2px solid #d6d9df;
                border-radius: 20px;
                padding: 14px;
                box-shadow: 0 2px 12px rgba(16, 24, 40, 0.10);
                scroll-snap-align: start;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .tt-card.active{
                border: 5px solid #ff2d2d;    /* ✅ strong red frame */
            }

            .tt-player{
                font-weight: 800;
                font-size: 1.10rem;
                opacity: 0.85;
                margin: 0;
            }
            .tt-name{
                font-weight: 950;
                font-size: 1.28rem;
                line-height: 1.18;
                margin: 0;
            }

            .tt-img{
                width: 100%;
                height: 215px;                /* ✅ bigger image */
                object-fit: cover;
                border-radius: 16px;
                border: 1px solid #eef1f6;
            }

            .tt-chosen{
                background: #fff2f2;
                border: 1px solid #ffb3b3;
                border-radius: 12px;
                padding: 9px 12px;
                font-weight: 950;
                font-size: 1.05rem;
            }

            /* ------- Attribute panel ------- */
            .tt-attrs{
                background: #f7f8fb;
                border: 1px solid #e6e9f2;
                border-radius: 16px;
                padding: 12px;
                display: grid;
                grid-template-columns: 1fr auto;
                row-gap: 9px;
                column-gap: 12px;
                font-size: 1.06rem;           /* ✅ bigger / readable */
                line-height: 1.2;
            }
            .tt-attrs .k{
                font-weight: 850;
                opacity: 0.94;
            }
            .tt-attrs .v{
                font-weight: 950;
                text-align: right;
                white-space: nowrap;
            }
            .tt-attrs .sep{
                grid-column: 1 / span 2;
                height: 1px;
                background: #e4e8f1;
                margin: 2px 0;
            }

            @media (max-width: 768px){
                .main .block-container{
                    padding-left: 1rem;
                    padding-right: 1rem;
                }
                .tt-card{
                    width: 340px;             /* ✅ bigger mobile */
                    min-width: 340px;
                }
                .tt-img{
                    height: 190px;
                }
                .tt-name{
                    font-size: 1.18rem;
                }
                .tt-attrs{
                    font-size: 1.02rem;
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


def _attrs_html(card: dict, chosen_attr: str | None, show_all: bool) -> str:
    attrs = card.get("attributes", {})
    rows = []

    keys = list(RULES.keys()) if show_all else ([chosen_attr] if chosen_attr else [])
    for idx, k in enumerate(keys):
        disp = DISPLAY.get(k, k)
        v = attrs.get(k, None)
        vtxt = "N/A" if v is None else str(v)
        rows.append(f"<div class='k'>{disp}</div><div class='v'>{vtxt}</div>")
        if idx != len(keys) - 1:
            rows.append("<div class='sep'></div>")

    if not rows:
        return ""

    chosen_badge = ""
    if chosen_attr and show_all:
        chosen_badge = f"<div class='tt-chosen'>Chosen: {DISPLAY.get(chosen_attr, chosen_attr)}</div>"

    return f"{chosen_badge}<div class='tt-attrs'>{''.join(rows)}</div>"


def _card_html(player_name: str, card: dict, highlight: bool, chosen_attr: str | None, show_attrs: bool) -> str:
    cls = "tt-card active" if highlight else "tt-card"
    img_uri = _img_as_data_uri(card.get("image"))
    img_html = f"<img class='tt-img' src='{img_uri}' />" if img_uri else ""
    attrs_html = _attrs_html(card, chosen_attr=chosen_attr, show_all=True) if show_attrs else ""

    # ✅ IMPORTANT: dedent + strip => NO leading spaces => not treated as code block
    html = f"""
    <div class="{cls}">
      <div>
        <p class="tt-player">{player_name}</p>
        <p class="tt-name">{card.get('name','(unknown)')}</p>
      </div>
      {img_html}
      {attrs_html}
    </div>
    """
    return textwrap.dedent(html).strip()


def render_cards_row(state, card_by_player: dict[int, dict], chosen_attr: str | None, show_attrs: bool):
    items = []
    for pi, card in card_by_player.items():
        pname = state["players"][int(pi)]["name"]
        highlight = int(pi) == int(state["active"])
        items.append(_card_html(pname, card, highlight, chosen_attr, show_attrs))

    row_html = "<div class='tt-row'>" + "".join(items) + "</div>"
    st.markdown(row_html, unsafe_allow_html=True)


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

    room_id = str(room_id).upper()

    # Auto-refresh for all players
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
                    st.rerun()
                else:
                    st.warning("That seat was just taken. Please pick another.")
        else:
            st.warning("All seats are currently taken. You are in spectator mode.")
        st.stop()

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
        round_cards = {pi: state["players"][pi]["deck"][0] for pi in alive if state["players"][pi]["deck"]}
        st.markdown("### Cards in this round")
        render_cards_row(state, round_cards, chosen_attr=None, show_attrs=False)

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
        st.markdown(f"### Reveal — Attribute: **{DISPLAY.get(chosen_attr, chosen_attr)}**")

        played_items = {int(pi): card for pi, card in state["played"].items()}
        render_cards_row(state, played_items, chosen_attr=chosen_attr, show_attrs=True)

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
