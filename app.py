import json
import random
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


# ----------------------------
# Helpers
# ----------------------------
@st.cache_data
def load_cards():
    with open("data/cards.json", "r", encoding="utf-8") as f:
        cards = json.load(f)

    # Validate minimal schema + normalize keys
    for c in cards:
        assert "id" in c and "name" in c and "attributes" in c

        # Ensure all attribute keys exist (missing -> None)
        for k in RULES.keys():
            if k not in c["attributes"]:
                c["attributes"][k] = None

        # ✅ NEW: ensure the image key exists (missing -> None)
        if "image" not in c:
            c["image"] = None

    return cards

def alive_player_indexes(state):
    return [i for i, p in enumerate(state["players"]) if len(p["deck"]) > 0]

def compare_cards(card_by_player, attribute):
    """
    card_by_player: dict[player_index] -> card_dict
    Returns winner_player_index (int) or None if tie.
    Null always loses.
    """
    rule = RULES[attribute]  # "higher" or "lower"

    values = []
    for pi, card in card_by_player.items():
        v = card["attributes"].get(attribute, None)
        values.append((pi, v))

    # If all None => tie
    if all(v is None for _, v in values):
        return None

    # Null always loses => treat as worst possible
    # For "higher": None -> -inf
    # For "lower": None -> +inf
    scored = []
    for pi, v in values:
        if v is None:
            score = float("-inf") if rule == "higher" else float("inf")
        else:
            score = v
        scored.append((pi, score))

    # Determine best score
    if rule == "higher":
        best = max(score for _, score in scored)
        winners = [pi for pi, score in scored if score == best]
    else:
        best = min(score for _, score in scored)
        winners = [pi for pi, score in scored if score == best]

    if len(winners) == 1:
        return winners[0]
    return None  # tie

def start_new_game(num_players):
    cards = load_cards()
    random.shuffle(cards)

    players = [{"name": f"Player {i+1}", "deck": []} for i in range(num_players)]
    # Deal round-robin
    for idx, card in enumerate(cards):
        players[idx % num_players]["deck"].append(card)

    return {
        "players": players,
        "active": 0,             # active player index
        "phase": "choose",       # "choose" -> "reveal"
        "chosen_attr": None,
        "played": {},            # dict[player_index] -> card_dict
        "winner": None,          # player_index or None (tie)
        "round": 1,
        "pot": [],               # tie pot (optional; used if you want “war” later)
    }

# ----------------------------
# UI
# ----------------------------
st.title("🏎️ Top Trumps – Hypercars")

# Sidebar debug / scoreboard (helps you verify it’s actually working)
with st.sidebar:
    st.subheader("Scoreboard")

    s = st.session_state.get("state")
    if s is None:
        st.write("No game running.")
    else:
        total_cards = sum(len(p["deck"]) for p in s["players"]) + len(s.get("pot", []))
        st.write(f"**Total cards in game:** {total_cards}")

        for i, p in enumerate(s["players"]):
            tag = " (ACTIVE)" if i == s["active"] else ""
            st.write(f"- **{p['name']}**: **{len(p['deck'])}** cards{tag}")

        if len(s.get("pot", [])) > 0:
            st.write(f"**Pot (tie cards):** {len(s['pot'])}")

        st.write(f"Round: {s['round']}")
        st.write(f"Phase: {s['phase']}")



# Start / reset controls
if "state" not in st.session_state:
    st.session_state.state = None

if st.session_state.state is None:
    st.subheader("Game setup")
    num_players = st.selectbox("Number of players", [2, 3, 4], index=0)

    if st.button("Start Game"):
        st.session_state.state = start_new_game(num_players)
        st.rerun()
    st.stop()

# Running game state
state = st.session_state.state

# End condition: only one player has cards
alive = alive_player_indexes(state)
if len(alive) == 1:
    winner = state["players"][alive[0]]["name"]
    st.balloons()
    st.success(f"Game over — **{winner}** wins!")
    if st.button("Start new game"):
        st.session_state.state = None
        st.rerun()
    st.stop()

# Ensure active player is alive; if not, move to next alive
if state["active"] not in alive:
    state["active"] = alive[0]

active_player = state["players"][state["active"]]

st.subheader(f"Round {state['round']} — {active_player['name']}'s turn")

# Phase 1: choose attribute
if state["phase"] == "choose":
    top_card = active_player["deck"][0]
    st.write(f"**Your top card:** {top_card['name']}")
    if top_card.get("image"):
        st.image(f"assets/images/{top_card['image']}", width=300)


    # Show attributes of active player's top card
    st.markdown("**Choose an attribute:**")
    attr_keys = list(RULES.keys())
    # nicer labels
    chosen = st.radio(
        "Attribute",
        options=attr_keys,
        format_func=lambda k: DISPLAY.get(k, k),
        index=0
    )

    # Show the active card values
    #st.markdown("**Card stats:**")
    #for k in attr_keys:
    #    v = top_card["attributes"].get(k)
    #    st.write(f"- {DISPLAY[k]}: {v if v is not None else 'N/A'}")

    if st.button("Play round"):
        # Each alive player plays top card
        played = {}
        for pi in alive:
            played[pi] = state["players"][pi]["deck"].pop(0)

        chosen = chosen  # radio value
        winner = compare_cards(played, chosen)

        # --- APPLY ROUND RESULT IMMEDIATELY (so sidebar shows correct counts) ---
        if winner is None:
            # Tie: move all played cards to pot; rotate active player
            state["pot"].extend(played.values())

            idxs = alive
            cur_pos = idxs.index(state["active"])
            state["active"] = idxs[(cur_pos + 1) % len(idxs)]

            outcome_text = "Tie — cards go to pot."
        else:
            winnings = list(played.values()) + state["pot"]
            state["pot"] = []
            state["players"][winner]["deck"].extend(winnings)
            state["active"] = winner
            outcome_text = f"{state['players'][winner]['name']} wins the round!"

        # Store reveal info for display only
        state["played"] = played
        state["chosen_attr"] = chosen
        state["winner"] = winner
        state["outcome_text"] = outcome_text

        state["phase"] = "reveal"
        st.rerun()


# Phase 2: reveal (DISPLAY ONLY - no awarding here)
elif state["phase"] == "reveal":
    chosen_attr = state["chosen_attr"]
    st.markdown(f"### Reveal — Attribute: **{DISPLAY.get(chosen_attr, chosen_attr)}**")

    # Show all played cards SIDE BY SIDE
    played_items = list(state["played"].items())  # [(player_index, card_dict), ...]
    cols = st.columns(len(played_items))

    for col, (pi, card) in zip(cols, played_items):
        pname = state["players"][pi]["name"]
        val = card["attributes"].get(chosen_attr)

        with col:
            st.markdown(f"#### {pname}")
            st.write(f"**{card['name']}**")
            st.write(f"**{DISPLAY.get(chosen_attr, chosen_attr)}:** {val if val is not None else 'N/A'}")

            if card.get("image"):
                st.image(f"assets/images/{card['image']}", width=300)



    # Show outcome text produced in Play round
    st.info(state.get("outcome_text", "Round complete."))

    if st.button("Next round"):
        state["played"] = {}
        state["chosen_attr"] = None
        state["winner"] = None
        state["outcome_text"] = ""
        state["phase"] = "choose"
        state["round"] += 1
        st.rerun()
