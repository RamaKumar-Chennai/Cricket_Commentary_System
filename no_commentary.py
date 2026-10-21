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
            seen_deliveries = {}

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
                        extras_type = k
                        if k in ["wides", "noballs"]:
                            is_extra_ball = True

                json_delivery = delivery["actual_delivery"]

                if json_delivery not in seen_deliveries:
                    seen_deliveries[json_delivery] = 1
                else:
                    seen_deliveries[json_delivery] += 1

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

                # ✅ Handle wickets safely
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

                        # ✅ Stop innings if all out
                        if wickets == 10:
                            block_html = f"""
                            <div style='background:#f1948a;padding:12px;border-radius:10px;font-weight:bold;text-align:center;'>
                              ❌ ALL OUT! <b>{team}</b> finished at {total_runs}/{wickets} in {over_part+1}.{legal_ball_count} overs
                            </div>
                            """
                            yield block_html, "", None
                            time.sleep(10)
                            break  # end deliveries loop

                total_runs += runs_total
                overs_fraction = over_part + (legal_ball_count / balls_per_over)
                current_rr = round(total_runs / overs_fraction, 2) if overs_fraction > 0 else 0

                boundary_4 = 1 if runs_batter == 4 and not delivery.get("extras") else 0
                boundary_6 = 1 if runs_batter == 6 and not delivery.get("extras") else 0

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

                block_html = f"""
<div style='background:#e3f2fd;padding:12px;border-radius:10px;'>
  <!-- First line -->
  <div style='display:flex;justify-content:space-between;'>
    <div>
      <b>{team}</b> &nbsp;&nbsp;
      <b>Ball:</b> {ball_display}
    </div>
    <div>
      <b>RUNS:</b> &nbsp;&nbsp;
      🏏 Batter: {runs_batter} &nbsp;&nbsp;
      🎁 Extras: {runs_extras} &nbsp;&nbsp;
      ➕ Total: {runs_total}
    </div>
  </div>

  <!-- Second line with spacing -->
  <div style='display:flex;justify-content:space-between;margin-top:8px;'>
    <div>
      <b>Score:</b> {total_runs}/{wickets} &nbsp;&nbsp;&nbsp; in <b>Overs:</b> {ball_display}
    </div>
    <div>
      ⚡ <b>Current RR:</b> {current_rr} &nbsp;&nbsp;
      <b>INNINGS:</b> {innings_index+1}
    </div>
  </div>
"""

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

                block_html += f"""
                  <div style='margin-top:6px;'>
                    ⚾ {bowler} to 🏏 {batter} (non-striker: {non_striker})
                  </div>
                </div>
                """

                if dismissal_msg:
                    block_html += f"<div style='background:#f1948a;padding:8px;border-radius:8px;font-weight:bold;'>❌ WICKET! {dismissal_msg}</div>"
                elif boundary_4:
                    block_html += "<div style='background:#82e0aa;padding:8px;border-radius:8px;font-weight:bold;'>🏏 FOUR!</div>"
                elif boundary_6:
                    block_html += "<div style='background:#f9e79f;padding:8px;border-radius:8px;font-weight:bold;'>🔥 SIX!</div>"
                elif is_extra_ball:
                    block_html += f"<div style='background:#aed6f1;padding:8px;border-radius:8px;font-weight:bold;'>⚠️ {extras_detail}</div>"


                # Skip scorecard if innings ended
                if wickets == 10:
                    continue  

                # Only yield scorecard if wickets < 10
                yield block_html, "", None



                conn = create_connection()
                insert_delivery(conn, team, year, stage, match_number, innings_index, over_part+1, legal_ball_count, ball_data)

                time.sleep(0.1)

        # ✅ End of first innings summary
        if innings_index == 0:
            overs_played = sum(len(over["deliveries"]) for over in innings["overs"])
            team2 = match_data["innings"][1]["team"]

            player_stats = {}
            for over in innings["overs"]:
                for i, delivery in enumerate(over["deliveries"], start=1):
                    batter = delivery["batter"]
                    runs_batter = delivery["runs"]["batter"]

                    if batter not in player_stats:
                        player_stats[batter] = {"runs": 0, "dismissal": None}

                    player_stats[batter]["runs"] += runs_batter

                    if "wickets" in delivery:
                        for w in delivery["wickets"]:
                            player_stats[batter]["dismissal"] = {
                                "kind": w["kind"],
                                "bowler": delivery["bowler"],
                                "fielder": w["fielders"][0]["name"] if "fielders" in w and w["fielders"] else None,
                                "over": f"{int(over['over'])+1}.{i}"
                            }

            stats_html = "<ul style='text-align:left;'>"
            for player, stats in player_stats.items():
                if stats["dismissal"]:
                    fielder_info = f" by {stats['dismissal']['fielder']}" if stats["dismissal"]["fielder"] else ""
                    stats_html += f"<li>{player}: {stats['runs']} runs, out {stats['dismissal']['kind']}{fielder_info}, bowled by {stats['dismissal']['bowler']} in over {stats['dismissal']['over']}</li>"
                else:
                    stats_html += f"<li>{player}: {stats['runs']} runs, not out</li>"
            stats_html += "</ul>"

            flash_html = f"""
            <div style='background:#d5f5e3;padding:14px;border-radius:12px;font-weight:bold;text-align:center;'>
              🏏 <b>{team}</b> scored <b>{total_runs}/{wickets}</b> in <b>{overs_played} overs</b><br>
              🎯 Target set: <b>{target}</b><br>
              <div style='margin-top:10px;text-align:left;'>{stats_html}</div>
              
              ⏳ Wait for the 2nd innings by <b>{team2}</b>...
            </div>
            """

            yield flash_html, "", None
            time.sleep(10)


        # ✅ End of second innings summary (final result)
        if innings_index == 1:
            outcome = match_data["info"]["outcome"]
            winner = outcome["winner"]
            margin = outcome["by"]

            if "runs" in margin:
                result_text = f"{winner} won the match by {margin['runs']} runs"
            elif "wickets" in margin:
                result_text = f"{winner} won the match by {margin['wickets']} wickets"
            else:
                result_text = f"{winner} won the match"

            player_of_match = ", ".join(match_data["info"].get("player_of_match", []))

            final_html = f"""
            <div style='background:#d6eaf8;padding:16px;border-radius:12px;font-weight:bold;text-align:center;'>
              🏆 <b>Match Result</b><br>
              {result_text}<br>
              🌟 Player of the Match: <b>{player_of_match}</b>
            </div>
            """
            yield final_html, "", None    

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
.header-block {background-color:#fce4ec;padding:12px;border-radius:10px;display:flex;align-items:center;}
.flashing-header {font-size:22px;font-weight:bold;animation: bannerFlash 3s infinite;margin-left:15px;}
@keyframes bannerFlash {0%{color:#d32f2f;}25%{color:#1976d2;}50%{color:#388e3c;}75%{color:#fbc02d;}100%{color:#7b1fa2;}}
.sidebar-block {background-color:#fce4ec;padding:12px;border-radius:10px;position:sticky;top:0;}
.match-details {font-size:14px;margin-top:10px;}
.detailed-box {background-color:#f3e5f5;padding:15px;border-radius:10px;max-height:600px;overflow-y:auto;}
.controls-box {background-color:#ffe4e1;padding:10px;border-radius:10px;}
#stadium-img .image-buttons {display:none!important;}
footer {display:none!important;}
"""

# --- Gradio UI ---
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
            # Scorecard only
            commentary_html = gr.HTML(label="Ball-by-Ball Replay")

            live_btn = gr.Button("🏏 LIVE SCORE")

            with gr.Row():
                with gr.Column(scale=2, elem_classes="detailed-box"):
                    detailed = gr.Textbox(label="Detailed Commentary", lines=15)
                    commentary_audio = gr.Audio(label="Voice Commentary", type="filepath")

                with gr.Column(scale=1, elem_classes="controls-box"):
                    gr.Markdown("### ⚙️ Controls")
                    stats_input = gr.Textbox(label="Question", placeholder="e.g. Who is top scorer?")
                    stats_output = gr.Textbox(label="Response")
                    
                    stats_input.submit (
                        
                        fn=classify_query,
                        inputs=stats_input,
                        outputs=stats_output
                    )

                    

    # Wire replay to three outputs
    live_btn.click(fn=replay, inputs=None, outputs=[commentary_html, detailed, commentary_audio])

demo.launch(inbrowser=True)
