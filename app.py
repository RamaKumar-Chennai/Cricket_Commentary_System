import gradio as gr
import json
import time
import tempfile
from datetime import datetime
from langchain_groq import ChatGroq
import pyttsx3
import os
from sql_insert_select import create_connection
from sql_insert_select import insert_delivery
from sql_insert_select import truncate_table
from sql_insert_select import select_sql_record
from dotenv import load_dotenv

from query_classifer import classify_query

# --- Load environment variables ---
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")

# --- Load match JSON ---
with open(r"D:\\VS_CODE\\INTEL-AIML\\Automated_Sports_Commentary_System\\ipl_json\\335982.json", encoding="utf-8") as f:
    match_data = json.load(f)

info = match_data["info"]
teams = info["teams"]

innings=match_data["innings"]
first_batting_team=innings[0]["team"]
second_batting_team=innings[1]["team"]

# Extract year and match number and stage
match_date = info["dates"][0]
year = datetime.strptime(match_date, "%Y-%m-%d").year
match_number = info["event"]["match_number"]
event_name = info["event"]["name"]

# Extract stage (Semi Final / Final / League)
stage = info["event"].get("stage", "League")        # returns "Semi Final" or "Final" if present

# --- Initialize Groq LLM ---

text_commentary_llm = ChatGroq(model="openai/gpt-oss-120b", api_key=groq_api_key)

# --- Commentary generator ---
def make_prompt(ball):
    prompt = f"""
You are a cricket commentator in IPL Season 1, year 2008.
Generate commentary for this ball:
- Over: {ball["actual_delivery"]}
- Bowler: {ball['bowler']}
- Batter: {ball['batter']}
- Non-striker: {ball['non_striker']}
- Runs scored by the batter:{ball['runs_batter']}
- Runs due to extras:{ball['runs_extras']}
- Total Runs scored by the batter:{ball['runs_total']}
- Extras type: {ball['extras_type']}
- Wicket: {ball['wicket']}
- Wicket kind: {ball['wicket_kind']}

-Player out: {ball['player_out']}
-Fielder: {ball['fielder']}

- Current score: {ball['score_after_ball']}


  Rules:
- If runs = 4 or 6 → make it exciting, energetic, crowd‑pleasing.
- If wicket = True → describe the dismissal dramatically, mention wicket kind, and impact.
- Otherwise → keep it engaging but balanced.
- Commentary should sound natural, like spoken broadcast.
- Length: ~40–50 words.
"""
    return prompt

def generate_commentary(ball):
    prompt = make_prompt(ball)
    response = text_commentary_llm.invoke(prompt)
    return response.content.strip()

# --- Voice synthesis with pyttsx3 ---



def text_to_speech(text):
    engine = pyttsx3.init()
    engine.setProperty("rate", 220)
    engine.setProperty("volume", 1.0)
    # Fixed file path inside temp directory
    tmpfile = os.path.join(tempfile.gettempdir(), "gradio_tts.wav")
    # Overwrite the same file each time
    engine.save_to_file(text, tmpfile)
    engine.runAndWait()
    # Return the file path so Gradio can play it
    return tmpfile


    
conn=create_connection()
if conn:
 truncate_table(conn)

# --- Replay function ---

def replay():
    balls_per_over = info["balls_per_over"]
    first_innings_total = sum(
        d["runs"]["total"]
        for over in match_data["innings"][0]["overs"]
        for d in over["deliveries"]
    )
    target = first_innings_total + 1

    for innings_index, innings in enumerate(match_data["innings"]):
        team = innings["team"]
        total_runs = 0
        wickets = 0

        for over in innings["overs"]:
            legal_ball_count = 0
            seen_deliveries = {}  # track duplicates for rebowled balls

            for delivery in over["deliveries"]:
                over_part = int(over["over"])
                runs_batter = delivery["runs"]["batter"]
                runs_extras = delivery["runs"]["extras"]
                runs_total = delivery["runs"]["total"]

                # ✅ Handle extras
                extras_detail = ""
                extras_type = None
                is_extra_ball = False
                if "extras" in delivery and delivery["extras"]:
                    for k, v in delivery["extras"].items():
                        extras_detail = f"<b>Extras:</b> {k.capitalize()} +{v}"
                        extras_type = k  # store extras type for DB
                        if k in ["wides", "noballs"]:
                            is_extra_ball = True

                json_delivery = delivery["actual_delivery"]

                # Track duplicates for rebowled balls
                if json_delivery not in seen_deliveries:
                    seen_deliveries[json_delivery] = 1
                else:
                    seen_deliveries[json_delivery] += 1

                # ✅ Ball display logic
                if is_extra_ball:
                    ball_display = f"{over_part+1}.{legal_ball_count+1} (extra)"
                else:
                    legal_ball_count += 1
                    ball_display = f"{over_part+1}.{legal_ball_count}"
                    if seen_deliveries[json_delivery] > 1:
                        ball_display = f"{ball_display} (rebowled)"

                batter = delivery["batter"]
                bowler = delivery["bowler"]
                non_striker = delivery.get("non_striker", "")

                # ✅ Handle wickets
                dismissal_msg = ""
                wicket_kind = None
                player_out = None
                fielder = None
                if "wickets" in delivery:
                    for w in delivery["wickets"]:
                        wickets += 1
                        wicket_kind = w["kind"]
                        player_out = w["player_out"]
                        if "fielders" in w and w["fielders"]:
                            fielder = w["fielders"][0]["name"]
                            dismissal_msg = f"{player_out} {w['kind'].upper()} by {fielder}"
                        else:
                            dismissal_msg = f"{player_out} {w['kind'].upper()}"

                total_runs += runs_total
                overs_fraction = over_part + (legal_ball_count / balls_per_over)
                current_rr = round(total_runs / overs_fraction, 2) if overs_fraction > 0 else 0

                # --- Boundary logic ---
                boundary_4 = 1 if runs_batter == 4 and not delivery.get("extras") else 0
                boundary_6 = 1 if runs_batter == 6 and not delivery.get("extras") else 0

                # ✅ Build ball data
                ball_data = {
                    "json_delivery": json_delivery,
                    "actual_delivery": ball_display,
                    "bowler": bowler,
                    "batter": batter,
                    "non_striker": non_striker,
                    "runs_batter": runs_batter,
                    "runs_extras": runs_extras,
                    "runs_total": runs_total,
                    "extras_type": extras_type,
                    "boundary_4": boundary_4,
                    "boundary_6": boundary_6,
                    "wicket": 1 if dismissal_msg else 0,
                    "wicket_kind": wicket_kind,
                    "player_out": player_out,
                    "fielder": fielder,
                    "score_after_ball": f"{total_runs}/{wickets}"
                }

                
                # ✅ Scorecard block
                block_html = f"""
                <div style='background:#e3f2fd;padding:12px;border-radius:10px;'>
                  <div>
                    <b>{team}</b> &nbsp;&nbsp;
                    <b>Ball:</b> {ball_display} &nbsp;&nbsp;
                    <b>Runs:</b> {runs_total} &nbsp;&nbsp;&nbsp;&nbsp; {extras_detail}
                  </div>
                  <div style='display:flex;justify-content:space-between;'>
                    <div>
                      <b>Score:</b> {total_runs}/{wickets} &nbsp;&nbsp;&nbsp; in <b>Overs:</b> {ball_display}
                    </div>
                    <div>
                      ⚡ <b>Current RR:</b> {current_rr} &nbsp;&nbsp;
                      <b>INNINGS:</b> {innings_index+1}
                    </div>
                  </div>
                """

                # 🎯 Target + Required RR (second innings only)
                if innings_index == 1:
                    remaining_runs = target - total_runs
                    remaining_balls = (len(match_data["innings"][0]["overs"]) * balls_per_over) - (
                        over_part * balls_per_over + legal_ball_count
                    )
                    required_rr = round((remaining_runs / remaining_balls) * balls_per_over, 2) if remaining_balls > 0 else 0
                    block_html += f"""
                      <div style='display:flex;justify-content:flex-end;'>
                        🎯 <b>Target:</b> {target} &nbsp;&nbsp;
                        📊 <b>Required RR:</b> {required_rr}
                      </div>
                    """

                # Bowler vs batter line
                block_html += f"""
                  <div style='margin-top:6px;'>
                    ⚾ {bowler} to 🏏 {batter} (non-striker: {non_striker})
                  </div>
                </div>
                """

                # 🎯 Flash cards
                if dismissal_msg:
                    block_html += f"<div style='background:#f1948a;padding:8px;border-radius:8px;font-weight:bold;'>❌ WICKET! {dismissal_msg}</div>"
                elif boundary_4:
                    block_html += "<div style='background:#82e0aa;padding:8px;border-radius:8px;font-weight:bold;'>🏏 FOUR!</div>"
                elif boundary_6:
                    block_html += "<div style='background:#f9e79f;padding:8px;border-radius:8px;font-weight:bold;'>🔥 SIX!</div>"
                elif is_extra_ball:
                    block_html += f"<div style='background:#aed6f1;padding:8px;border-radius:8px;font-weight:bold;'>⚠️ {extras_detail}</div>"

                # Generate commentary + audio
                commentary_text = generate_commentary(ball_data)
                audio_file = text_to_speech(commentary_text)
              

                # ✅ Skip scorecard if innings ended
                if wickets == 10:
                    continue  

                # Yield scorecard + commentary + audio
                yield block_html, commentary_text, audio_file

                conn = create_connection()
                insert_delivery(conn, team, year, stage, match_number, innings_index, over_part+1, legal_ball_count, ball_data)

                # Event-based delay
                if dismissal_msg:
                    delay = 16
                elif boundary_4 or boundary_6:
                    delay = 16
                else:
                    delay = 16
                time.sleep(delay)


# --- Players toggle ---
def toggle_players(current_html):
    if current_html.strip() == "":
        team1_players = "<ul>" + "".join([f"<li>{p}</li>" for p in info["players"][teams[0]]]) + "</ul>"
        team2_players = "<ul>" + "".join([f"<li>{p}</li>" for p in info["players"][teams[1]]]) + "</ul>"
        return f"""
        <div style='background:#fff3e0;padding:10px;border-radius:8px; max-height:300px; overflow-y:auto;'>
            <h4>👥 Team Squads</h4>
            <b>{teams[0]}:</b>{team1_players}
            <b>{teams[1]}:</b>{team2_players}
        </div>
        """
    else:
        return ""

# --- Sidebar details ---
def sidebar_details():
    venue = info.get("venue", "")
    city = info.get("city", "")
    toss_winner = info["toss"]["winner"]
    toss_decision = info["toss"]["decision"]
    match_type = info.get("match_type", "")
    overs = info.get("overs", "")
    balls_per_over = info.get("balls_per_over", "")
    officials = info.get("officials", {})
    umpires = ", ".join(officials.get("umpires", []))
    tv_umpires = ", ".join(officials.get("tv_umpires", []))
    reserve_umpires = ", ".join(officials.get("reserve_umpires", []))
    referee = ", ".join(officials.get("match_referees", []))

    return f"""
    <div class='match-details'>
        📅 Date: {match_date}<br>
        🏟️ Venue: {venue}, {city}<br>
        🎲 Toss: {toss_winner} chose to {toss_decision}<br>
        📖 Match Type: {match_type}<br>
        ⏱️ Overs: {overs}<br>
        🎯 Balls per Over: {balls_per_over}<br>
        👨‍⚖️ Umpires: {umpires}<br>
        📺 TV Umpires: {tv_umpires}<br>
        🧑‍⚖️ Reserve Umpires: {reserve_umpires}<br>
        📝 Referee: {referee}
    </div>
    """

# --- CSS ---

css_styles = """
.header-block {
    background: linear-gradient(90deg, #ff9a9e, #fad0c4);
    padding:12px;
    border-radius:10px;
    display:flex;
    align-items:center;
}
.flashing-header {
    font-size:22px;
    font-weight:bold;
    animation: bannerFlash 3s infinite;
    margin-left:15px;
}
@keyframes bannerFlash {
    0%{color:#d32f2f;}
    25%{color:#1976d2;}
    50%{color:#388e3c;}
    75%{color:#fbc02d;}
    100%{color:#7b1fa2;}
}
.sidebar-block {
    background: linear-gradient(180deg, #fce4ec, #f8bbd0);
    padding:12px;
    border-radius:10px;
    position:sticky;
    top:0;
    height:100%;
    color:#4a148c;
    font-weight:bold;
}

/* ✅ Text Commentary box with light aqua theme */
.detailed-box {
    background: #b2ebf2;        /* light aqua outer background */
    border: 3px solid #4dd0e1;  /* medium teal border */
    border-radius: 8px;
    padding: 10px;
}

.detailed-box textarea {
    background: #e0f7fa;        /* pale aqua inside */
    color: #006064;             /* deep teal text */
    font-weight: bold;
    border: 2px solid #26c6da;  /* inner border */
    border-radius: 6px;
}


/* Controls container */
.controls-box {
    background: #fce4ec;        /* soft pink background */
    border: 2px solid #f48fb1;  /* pink border */
    border-radius: 8px;
    padding: 8px;
}

/* Text input area */
.controls-box textarea,
.controls-box input {
    background: #fff0f6;        /* lighter pink inside */
    border: 2px solid #f8bbd0;  /* subtle border */
    border-radius: 6px;
    color: #4a148c;             /* deep purple text */
    font-weight: bold;
    padding: 6px;
}

/* Focus effect */
.controls-box textarea:focus,
.controls-box input:focus {
    outline: none;
    border-color: #ce93d8;      /* lavender highlight */
    box-shadow: 0 0 6px #ba68c8;
}




/* ✅ Scorecard styling: border + reduced height + centered text + smaller font */
.scorecard {
    border: 2px solid #1976d2;
    border-radius:8px;
    padding:10px;
    background:#bbdefb;
    color:#0d47a1;
    text-align:center;
    font-weight:bold;
    font-size:14px;   /* reduced font size */
    min-height:80px;  /* reduced height */
}



.voice-box {
    background: #b2ebf2;        /* light aqua outer background */
    border: 1px solid #4dd0e1;  /* thinner border */
    border-radius: 4px;
    padding: 2px;               /* minimal padding */
    display: inline-block;      /* keeps it compact */
}



.voice-box audio {
    width: 160px !important;    /* narrower width */
    height: 26px !important;    /* minimum most browsers allow */
    background: #e0f7fa;        /* pale aqua inside */
    border: 1px solid #26c6da;  /* thinner inner border */
    border-radius: 4px;
}

/* 🌐 Page background */
body, .gradio-container {
    background: linear-gradient(135deg, #fce4ec, #e0f7fa);  /* soft pink → aqua gradient */
}

/* 🚫 Hide Gradio footer */
footer {
    display: none !important;
}

"""


import soundfile as sf
import numpy as np
from transformers import pipeline

# Load Whisper-tiny
asr = pipeline("automatic-speech-recognition", model="openai/whisper-tiny")

def speech_to_text(audio_path):
    if audio_path is None:
        return "No audio recorded"
    # Load audio manually with soundfile (no ffmpeg)
    samples, sr = sf.read(audio_path)
    # Whisper expects float32 numpy array
    samples = np.array(samples, dtype=np.float32)
    # Pass raw waveform and sample rate
    result = asr({"array": samples, "sampling_rate": sr})
    return result["text"]



with gr.Blocks(css=css_styles, title="Autonomous Sports Commentary (Live Replay)") as demo:
    with gr.Row(elem_classes="header-block"):
        gr.Image(value="stadium_image.webp", type="filepath", show_label=False, scale=0, elem_id="stadium-img")
        gr.HTML(f"""
            <div class='flashing-header'>
                🏏 {event_name } ({year}) – Match {match_number}<br>
                🏟️ {teams[0]} vs {teams[1]}
            </div>
        """)

    with gr.Row():
        with gr.Column(scale=1, elem_classes="sidebar-block"):
            gr.HTML(sidebar_details())
            players_html = gr.HTML(value="", elem_id="players-block")
            toggle_players_btn = gr.Button("👥 Show/Hide Players")
            toggle_players_btn.click(fn=toggle_players, inputs=players_html, outputs=players_html)

        with gr.Column(scale=3):
            # ✅ Default centered SCORE CARD message
            commentary_html = gr.HTML(
                value="<div>SCORE CARD:<br>Click LIVE SCORE to update...</div>",
                label="Ball-by-Ball Replay",
                elem_classes="scorecard"
            )

            live_btn = gr.Button("🏏 LIVE SCORE")

            detailed = gr.Textbox(label="Detailed Commentary", lines=5,elem_classes="detailed-box")

            
            # ✅ Voice commentary with reduced width + height
            commentary_audio = gr.Audio(label="🔊 Voice Commentary", type="filepath", elem_classes="voice-box")
            
            gr.Markdown("### ⚙️ Controls")
            stats_input = gr.Textbox(label="Question", placeholder="Speak or type your query here",elem_classes="controls-box")
            stats_output = gr.Textbox(label="Response",elem_classes="controls-box")



            mic_input = gr.Audio(type="filepath", label="🎤 Speak")
               
            mic_input.change(speech_to_text, inputs=mic_input, outputs=stats_input)


            reset_btn = gr.Button("Reset")
    
            # Reset → clear both textboxes
            reset_btn.click(lambda: ("", ""), None, [stats_input, stats_output], queue=False)

            stats_input.submit(fn=classify_query, inputs=stats_input, outputs=stats_output)

    # Wire your own function here later
    live_btn.click(fn=replay, inputs=None, outputs=[commentary_html, detailed, commentary_audio])

demo.launch(inbrowser=True)



