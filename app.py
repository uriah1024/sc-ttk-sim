import json
import base64
import collections
import os
import time
import streamlit as st
import pandas as pd
import altair as alt
import streamlit.components.v1 as components

from data_manager import GameDatabase, DataTransformer, get_ship_shield_size, get_ship_pp_size, get_default_shield, get_default_pp
from mechanics import Weapon, DefenderLoadout
from simulation import run_tournament_engine, simulate_visual_fight

# --- GLOBAL CSS OVERRIDES ---
st.markdown("""
    <style>
    /* Force true wide layout for high-res monitors */
    .block-container {
        max-width: 95% !important;
        padding-top: 1rem !important;
    }
            
    /* Match Tab Font Size to Subheaders */
    button[data-baseweb="tab"] {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
    }
    
    /* Hollow Interactive Reset Button Styling */
    button[kind="secondary"] {
        border: 1px solid #4a4a5a !important;
        background-color: transparent !important;
        color: #aaaaaa !important;
        transition: all 0.15s ease-in-out !important;
    }
    button[kind="secondary"]:hover {
        background-color: #3a3a4a !important;
        border-color: #888899 !important;
        color: #ffffff !important;
    }
    button[kind="secondary"]:active {
        background-color: #ff4b4b !important;
        border-color: #ff4b4b !important;
        color: #ffffff !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# UI HELPERS
# ==========================================

def render_target_components(tab_prefix, target_ship_name, db):
    if 'ship_prefs' not in st.session_state:
        st.session_state.ship_prefs = {}
        
    req_shd_size = get_ship_shield_size(target_ship_name, db)
    req_pp_size = get_ship_pp_size(target_ship_name, db)
    
    valid_shields = []
    for n, d in db.shields.items():
        sz = DataTransformer.get_num(d.get('Shield_Size'), is_int=True)
        if sz in (req_shd_size, 0): valid_shields.append(n)
            
    valid_pps = []
    for n, d in db.power_plants.items():
        sz = DataTransformer.get_num(d.get('PP_Size', d.get('Size', d.get('PP_Comp_Size', 0))), is_int=True)
        if sz in (req_pp_size, 0): valid_pps.append(n)
            
    valid_shields = ["None"] + sorted(valid_shields)
    valid_pps = ["Default"] + sorted(valid_pps)

    def_shd = get_default_shield(target_ship_name, db)
    if def_shd not in valid_shields and len(valid_shields) > 1: def_shd = valid_shields[1]
    
    def_pp = get_default_pp(target_ship_name, db)
    if def_pp not in valid_pps and len(valid_pps) > 1: def_pp = valid_pps[1]
    
    prefs = st.session_state.ship_prefs.get(target_ship_name, {})
    cur_shd = prefs.get('shield', def_shd)
    cur_pp = prefs.get('pp', def_pp)
    
    shd_key = f"{tab_prefix}_shd"
    pp_key = f"{tab_prefix}_pp"
    last_ship_key = f"{tab_prefix}_last_ship"
    
    if st.session_state.get(last_ship_key) != target_ship_name:
        st.session_state[shd_key] = cur_shd if cur_shd in valid_shields else def_shd
        st.session_state[pp_key] = cur_pp if cur_pp in valid_pps else def_pp
        st.session_state[last_ship_key] = target_ship_name
        
    if st.session_state.get(shd_key) not in valid_shields: st.session_state[shd_key] = def_shd
    if st.session_state.get(pp_key) not in valid_pps: st.session_state[pp_key] = def_pp
    
    selected_shd = st.selectbox("Target Shield", valid_shields, key=shd_key)
    selected_pp = st.selectbox("Target Power Plant", valid_pps, key=pp_key)
        
    if target_ship_name not in st.session_state.ship_prefs:
        st.session_state.ship_prefs[target_ship_name] = {}
    st.session_state.ship_prefs[target_ship_name]['shield'] = selected_shd
    st.session_state.ship_prefs[target_ship_name]['pp'] = selected_pp
    
    return selected_shd, selected_pp

def reset_tab_defaults(tab_prefix, target_ship_key):
    target_ship = st.session_state[target_ship_key]
    req_shd_size = get_ship_shield_size(target_ship, db)
    req_pp_size = get_ship_pp_size(target_ship, db)
    
    valid_shields = []
    for n, d in db.shields.items():
        sz = DataTransformer.get_num(d.get('Shield_Size'), is_int=True)
        if sz in (req_shd_size, 0): valid_shields.append(n)
            
    valid_pps = []
    for n, d in db.power_plants.items():
        sz = DataTransformer.get_num(d.get('PP_Size', d.get('Size', d.get('PP_Comp_Size', 0))), is_int=True)
        if sz in (req_pp_size, 0): valid_pps.append(n)
            
    valid_shields = ["None"] + sorted(valid_shields)
    valid_pps = ["Default"] + sorted(valid_pps)
    
    def_shd = get_default_shield(target_ship, db)
    if def_shd not in valid_shields and len(valid_shields) > 1: def_shd = valid_shields[1]
    
    def_pp = get_default_pp(target_ship, db)
    if def_pp not in valid_pps and len(valid_pps) > 1: def_pp = valid_pps[1]
    
    st.session_state[f"{tab_prefix}_shd"] = def_shd
    st.session_state[f"{tab_prefix}_pp"] = def_pp
    
    if 'ship_prefs' in st.session_state and target_ship in st.session_state.ship_prefs:
        st.session_state.ship_prefs[target_ship]['shield'] = def_shd
        st.session_state.ship_prefs[target_ship]['pp'] = def_pp

def generate_discord_copy_button(dataframe, button_text):
    headers = list(dataframe.columns)
    md_lines = [f"| {' | '.join(headers)} |", "|" + "|".join(["---"]*len(headers)) + "|"]
    for _, row in dataframe.iterrows():
        md_lines.append(f"| {' | '.join([str(row[h]) for h in headers])} |")
    
    discord_md = "\n".join(md_lines)
    b64_md = base64.b64encode(discord_md.encode('utf-8')).decode('utf-8')
    
    html = f"""
    <button onclick="navigator.clipboard.writeText(atob('{b64_md}')); this.innerText='Copied!'; setTimeout(()=>this.innerText='{button_text}', 2000);" 
    style="background-color: #5865F2; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-family: sans-serif; font-weight: bold; margin-bottom: 10px;">
    {button_text}
    </button>
    """
    components.html(html, height=40)

def get_base64_image(filepath):
    """Safely reads a local image and converts it to a Base64 data URI for the browser."""
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            data = f.read()
        ext = filepath.split('.')[-1].lower()
        mime_type = "image/png" if ext == "png" else "image/jpeg"
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{mime_type};base64,{b64}"
    return None

def generate_interactive_ttk_chart(df, title):
    plot_df = df[df["TTK Float"] != float('inf')].copy()
    if plot_df.empty: return
    
    plot_df = plot_df.sort_values('TTK Float')
    
    chart = alt.Chart(plot_df).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X('TTK Float:Q', title='Time to Kill (Seconds)'),
        y=alt.Y('Loadout:N', sort=alt.EncodingSortField(field='TTK Float', order='ascending'), title=None, axis=alt.Axis(labelLimit=300)),
        color=alt.Color('TTK Float:Q', scale=alt.Scale(scheme='tealblues', reverse=True), legend=None),
        tooltip=['Loadout', 'TTK', 'Velocity Dev', 'Death Reason']
    ).properties(
        title=title,
        height=min(400, max(150, len(plot_df) * 40))
    )
    st.altair_chart(chart, use_container_width=True)

# ==========================================
# STREAMLIT GUI FRONTEND
# ==========================================

if __name__ == '__main__':
    st.title("🚀 Star Citizen TTK Simulator")

    @st.cache_data
    def load_db():
        return GameDatabase()

    db = load_db()

    if not db.ships or not db.weapons:
        st.error("Missing CSV files! Ensure ships.csv, weapons.csv, etc., are in the same folder.")
        st.stop()
    
    attacker_options = sorted(list(db.ships.keys()))
    defender_options = sorted(list(db.ships.keys()))

    tab_tourney, tab_sandbox, tab_visualizer = st.tabs(["🏆 Tournament Engine", "🔬 Penetration Sandbox", "🎬 Combat Visualizer"])
    
    trigger_help = "Benchmark: Waits for full capacity.\nHuman: Estimates shield regen delays with human error margins.\nAI: Uses perfect math/distance tracking to keep shields down."
    
    # === TAB 1: TOURNAMENT ENGINE ===
    with tab_tourney:
        col_t1_setup, col_t1_main = st.columns([1, 4], gap="large")
        
        with col_t1_setup:
            st.subheader("⚙️ Match Setup")
            t1_attacker = st.selectbox("Attacker Ship", attacker_options, index=attacker_options.index("F7A Hornet Mk II") if "F7A Hornet Mk II" in attacker_options else 0, key="t1_atk")
            t1_target = st.selectbox("Target Ship", defender_options, index=defender_options.index("Arrow") if "Arrow" in defender_options else 0, key="t1_tgt")
            
            t1_shield, t1_pp = render_target_components("t1", t1_target, db)
            
            t1_dist = st.number_input("Engagement Distance (m)", value=500.0, step=100.0, key="t1_dst")
            
            run_btn = st.button("🚀 Run Tournament Simulator", type="primary", use_container_width=True)
            st.button("↺ Reset Defaults", key="rst_t1", use_container_width=True, on_click=reset_tab_defaults, args=("t1", "t1_tgt"))
            
            st.divider()
            
            st.subheader("Rules & Filters")
            t1_trigger = st.selectbox("Trigger Logic", ["Benchmark", "Human", "AI"], help=trigger_help, key="t1_trig")
            t1_force = st.checkbox("Force Identical Sized Weapons", value=True, key="t1_frc")
            t1_dmg = st.selectbox("Damage Preference", ["Any", "Energy", "Ballistic", "Distortion"], key="t1_dmg")
            t1_vel = st.number_input("Velocity Floor (m/s)", value=0.0, step=100.0, key="t1_vel")
            t1_armor = st.number_input("Min Pen Armor Cutoff (%)", value=0.0, step=10.0, key="t1_arm")
            t1_banned = st.text_input("Banned Terms (Comma Separated)", value="scattergun, mass driver", key="t1_ban")
            t1_whitelist = st.text_input("Force Weapons (e.g., 3:Panther)", key="t1_whi")
            
            banned_list = [x.strip() for x in t1_banned.split(',')] if t1_banned else []
            whitelist_dict = {}
            if t1_whitelist:
                for pair in t1_whitelist.split(','):
                    if ':' in pair:
                        try:
                            sz_str, name_str = pair.split(':', 1)
                            whitelist_dict[int(sz_str.strip())] = [name_str.strip()]
                        except ValueError:
                            pass

        with col_t1_main:
            if run_btn:
                actual_pp = None if t1_pp == "Default" else t1_pp
                actual_shield = None if t1_shield == "None" else t1_shield
                dmg_val = None if t1_dmg == "Any" else t1_dmg.lower()
                
                with st.spinner("Calculating combinations... Engaging Warp Drive..."):
                    start_time = time.time()
                    results, intel, pp_depth, total_combos, err = run_tournament_engine(
                        database=db, attacker_name=t1_attacker, target_name=t1_target, 
                        target_shield_name=actual_shield, target_pp_name=actual_pp, 
                        engagement_distance=t1_dist, disallowed_terms=banned_list, 
                        trigger_logic=t1_trigger, min_penetration_pct=t1_armor, 
                        forced_weapons=whitelist_dict, min_ammo_speed=t1_vel, 
                        weapon_type_filter=dmg_val, homogeneous_grouping=t1_force
                    )
                    elapsed = time.time() - start_time
                    
                if err:
                    st.error(err)
                else:
                    st.success(f"Simulation complete! Evaluated {total_combos:,} loadouts in {elapsed:.2f} seconds.")
                    
                    df_data = []
                    for r in results:
                        ttk_val = f"{r['ttk']:.2f}s" if r['ttk'] != float('inf') else "FAILED"
                        counts = collections.Counter(r['loadout'])
                        pretty_loadout = ", ".join([f"{v}x {DataTransformer.clean_weapon_name(k)}" for k, v in counts.items()])
                        
                        df_data.append({
                            "TTK": ttk_val,
                            "Death Reason": r['reason'],
                            "Velocity Dev": f"{r['speed_dev']:.0f} m/s",
                            "Loadout": pretty_loadout,
                            "Speed Float": r['speed_dev'], 
                            "TTK Float": r['ttk']
                        })
                    
                    df = pd.DataFrame(df_data)
                    
                    st.subheader("🏆 Top Loadouts (Overall)")
                    top_10_df = df.drop(columns=["Speed Float"]).head(10)
                    generate_interactive_ttk_chart(top_10_df, "Overall TTK Breakdown")
                    generate_discord_copy_button(top_10_df.drop(columns=["TTK Float"]), "📋 Copy Top 10 to Discord")
                    st.dataframe(top_10_df.drop(columns=["TTK Float"]), use_container_width=True, hide_index=True)
                    
                    st.subheader("🏆 Top Loadouts (Velocity Matched < 60 m/s)")
                    matched_df = df[df["Speed Float"] < 60.0]
                    if matched_df.empty:
                        st.info("No loadouts found with a velocity deviation under 60 m/s.")
                    else:
                        top_10_matched = matched_df.drop(columns=["Speed Float"]).head(10)
                        generate_interactive_ttk_chart(top_10_matched, "Velocity Matched TTK Breakdown")
                        generate_discord_copy_button(top_10_matched.drop(columns=["TTK Float"]), "📋 Copy Matched Top 10 to Discord")
                        st.dataframe(top_10_matched.drop(columns=["TTK Float"]), use_container_width=True, hide_index=True)
                    
                    st.divider()
    
                    st.subheader("📊 Weapon Intelligence Report")
                    intel_df = pd.DataFrame(intel)
                    generate_discord_copy_button(intel_df, "📋 Copy Intel to Discord")
                    st.dataframe(intel_df, use_container_width=True, hide_index=True)
            else:
                st.info("Configure your matchup on the left and click 'Run Tournament Simulator' to begin.")

    # === TAB 2: PENETRATION SANDBOX ===
    with tab_sandbox:
        col_t2_setup, col_t2_main = st.columns([1, 4], gap="large")
        
        with col_t2_setup:
            st.subheader("⚙️ Match Setup")
            t2_target = st.selectbox("Target Ship", defender_options, index=defender_options.index("Arrow") if "Arrow" in defender_options else 0, key="t2_tgt")
            t2_shield, t2_pp = render_target_components("t2", t2_target, db)
            
            st.button("↺ Reset Defaults", key="rst_t2", use_container_width=True, on_click=reset_tab_defaults, args=("t2", "t2_tgt"))

            st.divider()
            st.subheader("Test Parameters")
            sandbox_weapon_name = st.selectbox("Detail Test Weapon", sorted(list(db.weapons.keys())))
            sandbox_shield_pct = st.slider("Current Shield %", 0.0, 100.0, 100.0, step=1.0)
            sandbox_armor_pct = st.slider("Current Armor %", 0.0, 100.0, 100.0, step=1.0)
            t2_attacker = st.selectbox("Attacker Ship (For Fleet Chart)", attacker_options, index=attacker_options.index("F7A Hornet Mk II") if "F7A Hornet Mk II" in attacker_options else 0, key="t2_atk")

        with col_t2_main:
            st.header("Interactive Penetration Sandbox")
            st.write("Adjust the target's remaining Shield and Armor % on the left to visualize exactly when weapons will overcome deflection and breach the Power Plant depth.")
            
            sb_target = DefenderLoadout(t2_target, db, None if t2_pp == "Default" else t2_pp)
            sb_target.equip_shields(None if t2_shield == "None" else t2_shield, db)
            
            sb_weapon = Weapon(db.weapons[sandbox_weapon_name], 1.0, 1.0)
            
            if sb_weapon.damage_type == 'distortion':
                st.warning("Distortion weapons bypass physical geometry completely and attack the shield generator directly.")
            else:
                shield_ratio = sandbox_shield_pct / 100.0
                d_active = sb_weapon.alpha_damage * (1.0 - sb_target.shield_resist.get(sb_weapon.damage_type, 0.0))
                
                if shield_ratio > 0 and sb_target.max_shield_hp > 0:
                    abs_min = sb_target.shield_absorp_min[sb_weapon.damage_type]
                    abs_max = sb_target.shield_absorp_max[sb_weapon.damage_type]
                    absorp_current = abs_min + (abs_max - abs_min) * shield_ratio
                    d_pass = d_active * (1.0 - absorp_current)
                else:
                    d_pass = d_active
                    
                current_armor_ratio = sandbox_armor_pct / 100.0
                current_deflection = sb_target.deflection.get(sb_weapon.damage_type, 0.0) * current_armor_ratio
                
                scale = 1.0 - current_armor_ratio
                current_pen_depth = sb_weapon.max_pen * scale
                pp_target_depth = sb_target.pp_depth
                
                bites_armor = d_pass >= current_deflection
                strikes_pp = current_pen_depth >= pp_target_depth
                
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.metric(f"{DataTransformer.clean_weapon_name(sandbox_weapon_name)} vs Deflection", 
                              f"{d_pass:.1f} dmg vs {current_deflection:.1f} defl", 
                              "Deflected" if not bites_armor else "Bites Armor",
                              delta_color="inverse" if not bites_armor else "normal")
                with col_res2:
                    st.metric("Penetration vs PP Depth", 
                              f"{current_pen_depth:.2f}m / {pp_target_depth:.2f}m",
                              "Sniped" if strikes_pp else "Too Shallow",
                          delta_color="normal" if strikes_pp else "inverse")
                    
                st.markdown("### Individual Depth Visualizer")
                
                visual_max = max(sb_weapon.max_pen, pp_target_depth) * 1.1
                if visual_max == 0: visual_max = 1.0
                
                pen_fill_pct = (current_pen_depth / visual_max) * 100.0
                pp_marker_pct = (pp_target_depth / visual_max) * 100.0
                bar_color = "#00cc44" if strikes_pp else "#0088ff"
                
                custom_html = f"""
                <div style="width: 100%; max-width: 800px; background-color: #2b2b36; height: 40px; position: relative; border-radius: 5px; overflow: hidden; border: 1px solid #555;">
                   <div style="position: absolute; left: 0; top: 0; height: 100%; width: {pen_fill_pct}%; background-color: {bar_color}; border-radius: 5px 0 0 5px; transition: width 0.3s ease;"></div>
                   <div style="position: absolute; left: {pp_marker_pct}%; top: 0; height: 100%; width: 4px; background-color: #ff3333; z-index: 10;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; max-width: 800px; font-size: 12px; color: #aaa; margin-top: 5px;">
                    <span>0m (Hull Exterior)</span>
                    <span>Power Plant Depth: <span style="color: #ff3333; font-weight: bold;">{pp_target_depth:.2f}m</span></span>
                    <span>Max Visual Depth: {visual_max:.1f}m</span>
                </div>
                """
                st.markdown(custom_html, unsafe_allow_html=True)
                
                if strikes_pp:
                    st.success(f"💥 At {sandbox_armor_pct}% Armor, the {DataTransformer.clean_weapon_name(sandbox_weapon_name)} breaches {current_pen_depth:.2f}m deep, successfully striking the Power Plant.")
                else:
                    st.warning(f"🛡️ At {sandbox_armor_pct}% Armor, the {DataTransformer.clean_weapon_name(sandbox_weapon_name)} only penetrates {current_pen_depth:.2f}m. You must lower the armor further to reach the {pp_target_depth:.2f}m target.")
    
            st.divider()
            st.markdown(f"### Fleet-Wide Penetration Potential for {t2_attacker}")
            
            attacker_sizes = set(db.ship_configs[t2_attacker].get('hardpoints', []))
            chart_data = []
            
            for w_name, w_data in db.weapons.items():
                w = Weapon(w_data, 1.0, 1.0)
                if w.size not in attacker_sizes: continue
                if w.damage_type == 'distortion': continue 
                
                c_d_active = w.alpha_damage * (1.0 - sb_target.shield_resist.get(w.damage_type, 0.0))
                if shield_ratio > 0 and sb_target.max_shield_hp > 0:
                    c_abs_min = sb_target.shield_absorp_min[w.damage_type]
                    c_abs_max = sb_target.shield_absorp_max[w.damage_type]
                    c_absorp_current = c_abs_min + (c_abs_max - c_abs_min) * shield_ratio
                    c_d_pass = c_d_active * (1.0 - c_absorp_current)
                else:
                    c_d_pass = c_d_active
                    
                c_current_deflection = sb_target.deflection.get(w.damage_type, 0.0) * current_armor_ratio
                c_bites_armor = c_d_pass >= c_current_deflection
                c_current_pen = (w.max_pen * scale) if c_bites_armor else 0.0
                
                chart_data.append({
                    "Weapon": DataTransformer.clean_weapon_name(w_name),
                    "Current Pen (m)": round(c_current_pen, 2),
                    "Type": w.damage_type.capitalize(),
                    "Bites Armor": c_bites_armor
                })
                
            chart_df = pd.DataFrame(chart_data)
            if not chart_df.empty:
                base = alt.Chart(chart_df).encode(
                    y=alt.Y('Weapon:N', sort='-x', title=None)
                )
                bars = base.mark_bar().encode(
                    x=alt.X('Current Pen (m):Q', title=f'Current Penetration Depth at {sandbox_armor_pct}% Armor'),
                    color=alt.Color('Type:N', scale=alt.Scale(domain=['Ballistic', 'Energy'], range=['#ffaa00', '#00ffff'])),
                    tooltip=['Weapon', 'Type', 'Current Pen (m)', 'Bites Armor']
                )
                rule = alt.Chart(pd.DataFrame({'x': [pp_target_depth]})).mark_rule(color='#ff3333', strokeWidth=3, strokeDash=[5, 5]).encode(x='x:Q')
                st.altair_chart((bars + rule).properties(height=max(150, len(chart_df)*30)), use_container_width=True)

    # === TAB 3: COMBAT VISUALIZER (FLEET MODE) ===
    with tab_visualizer:
        col_t3_setup, col_t3_main = st.columns([1, 4], gap="large")
        
        with col_t3_setup:
            st.subheader("⚙️ Match Setup")
            t3_target = st.selectbox("Target Ship", defender_options, index=defender_options.index("Arrow") if "Arrow" in defender_options else 0, key="t3_tgt")
            
            t3_shield, t3_pp = render_target_components("t3", t3_target, db)
            t3_dist = st.number_input("Engagement Distance (m)", value=500.0, step=100.0, key="t3_dst")
            
            run_render = st.button("🎬 Generate Battle Render", type="primary", use_container_width=True)
            st.button("↺ Reset Target", key="rst_t3", use_container_width=True, on_click=reset_tab_defaults, args=("t3", "t3_tgt"))
            
            st.divider()
            
            # --- ATTACKER 1 (LEAD) ---
            st.markdown("### 🟢 Attacker 1 (Lead)")
            t3_attacker_1 = st.selectbox("Ship", attacker_options, index=attacker_options.index("F7A Hornet Mk II") if "F7A Hornet Mk II" in attacker_options else 0, key="t3_atk1")
            t3_trigger_1 = st.selectbox("Trigger Logic (A1)", ["Benchmark", "Human", "AI"], help=trigger_help, key="t3_trig1")
            t3_angle_1 = st.selectbox("Attack Angle (A1)", ["Front", "Right", "Rear", "Left"], key="t3_ang1")
            t3_force_1 = st.checkbox("Force Identical Weapons (A1)", value=True, key="t3_frc1")
            
            a1_ammo_mod = db.ship_configs[t3_attacker_1].get('max_ammo_mod', 1.0)
            a1_regen_mod = db.ship_configs[t3_attacker_1].get('max_regen_sec_mod', 1.0)
            attacker_hp_1 = db.ship_configs[t3_attacker_1]['hardpoints']
            selected_weapons_1 = []
            
            if t3_force_1:
                hp_counts_1 = collections.Counter(attacker_hp_1)
                for hp_size, count in sorted(hp_counts_1.items(), reverse=True):
                    valid_w = [w for w, d in db.weapons.items() if hp_size - 1 <= DataTransformer.get_num(d.get('Weapon_Size')) <= hp_size]
                    default_idx = valid_w.index("Panther Repeater") if valid_w and "Panther Repeater" in valid_w and hp_size >= 3 else 0
                    w_choice = st.selectbox(f"{count}x Size {hp_size} Mounts", sorted(valid_w), index=default_idx, key=f"vis_hp1_grp_{hp_size}")
                    selected_weapons_1.extend([w_choice] * count) 
            else:
                for i, hp_size in enumerate(attacker_hp_1):
                    valid_w = [w for w, d in db.weapons.items() if hp_size - 1 <= DataTransformer.get_num(d.get('Weapon_Size')) <= hp_size]
                    default_idx = valid_w.index("Panther Repeater") if valid_w and "Panther Repeater" in valid_w and hp_size >= 3 else 0
                    w_choice = st.selectbox(f"Slot {i+1} (S{hp_size})", sorted(valid_w), index=default_idx, key=f"vis_hp1_{i}")
                    selected_weapons_1.append(w_choice)

            st.divider()

            # --- ATTACKER 2 (WINGMAN) ---
            st.markdown("### 🔵 Attacker 2 (Wingman)")
            attacker_options_with_none = ["None"] + attacker_options
            t3_attacker_2 = st.selectbox("Ship", attacker_options_with_none, index=0, key="t3_atk2")
            
            selected_weapons_2 = []
            if t3_attacker_2 != "None":
                t3_trigger_2 = st.selectbox("Trigger Logic (A2)", ["Benchmark", "Human", "AI"], help=trigger_help, key="t3_trig2")
                t3_angle_2 = st.selectbox("Attack Angle (A2)", ["Front", "Right", "Rear", "Left"], index=1, key="t3_ang2")
                t3_force_2 = st.checkbox("Force Identical Weapons (A2)", value=True, key="t3_frc2")
                
                a2_ammo_mod = db.ship_configs[t3_attacker_2].get('max_ammo_mod', 1.0)
                a2_regen_mod = db.ship_configs[t3_attacker_2].get('max_regen_sec_mod', 1.0)
                attacker_hp_2 = db.ship_configs[t3_attacker_2]['hardpoints']
                if t3_force_2:
                    hp_counts_2 = collections.Counter(attacker_hp_2)
                    for hp_size, count in sorted(hp_counts_2.items(), reverse=True):
                        valid_w = [w for w, d in db.weapons.items() if hp_size - 1 <= DataTransformer.get_num(d.get('Weapon_Size')) <= hp_size]
                        default_idx = valid_w.index("Panther Repeater") if valid_w and "Panther Repeater" in valid_w and hp_size >= 3 else 0
                        w_choice = st.selectbox(f"{count}x Size {hp_size} Mounts", sorted(valid_w), index=default_idx, key=f"vis_hp2_grp_{hp_size}")
                        selected_weapons_2.extend([w_choice] * count) 
                else:
                    for i, hp_size in enumerate(attacker_hp_2):
                        valid_w = [w for w, d in db.weapons.items() if hp_size - 1 <= DataTransformer.get_num(d.get('Weapon_Size')) <= hp_size]
                        default_idx = valid_w.index("Panther Repeater") if valid_w and "Panther Repeater" in valid_w and hp_size >= 3 else 0
                        w_choice = st.selectbox(f"Slot {i+1} (S{hp_size})", sorted(valid_w), index=default_idx, key=f"vis_hp2_{i}")
                        selected_weapons_2.append(w_choice)
            else:
                t3_trigger_2 = "Benchmark"
                t3_angle_2 = 'Front'

        with col_t3_main:
            st.header("Interactive Combat Playback")
            if run_render:
                actual_pp = None if t3_pp == "Default" else t3_pp
                actual_shield = None if t3_shield == "None" else t3_shield
                
                vis_target = DefenderLoadout(t3_target, db, actual_pp)
                vis_target.equip_shields(actual_shield, db)
                shield_faces_val = getattr(vis_target, 'shield_faces', 1.0)
                
                vis_weapons_1 = [Weapon(db.weapons[w], a1_ammo_mod, a1_regen_mod) for w in selected_weapons_1]
                vis_weapons_2 = [Weapon(db.weapons[w], a2_ammo_mod, a2_regen_mod) for w in selected_weapons_2] if t3_attacker_2 != "None" else []
                
                with st.spinner("Rendering Physics..."):
                    # Unpack the 4 variables now
                    frames, final_ttk, death_reason, combat_log = simulate_visual_fight(
                        vis_weapons_1, vis_weapons_2, vis_target, 
                        engagement_distance=t3_dist, 
                        trigger_1=t3_trigger_1,
                        trigger_2=t3_trigger_2,
                        angle_1=t3_angle_1,
                        angle_2=t3_angle_2,
                        db=db
                    )
                    
                if len(frames) == 0:
                    st.error("Simulation failed to generate frames.")
                else:
                    st.success(f"Render Complete! TTK: {final_ttk:.2f}s ({death_reason})")
                    
                    json_frames = json.dumps(frames)
                    canvas_w = 1100 if t3_attacker_2 != "None" else 900
                    
                    try:
                        # 1. Load Templates
                        with open("visualizer.html", "r", encoding="utf-8") as f_html:
                            html_template = f_html.read()
                        with open("visualizer.js", "r", encoding="utf-8") as f_js:
                            js_logic = f_js.read()
                            
                        # Load custom images safely
                        art_folder = os.path.join("Art", "Ship Art")
                        bg_img = get_base64_image(os.path.join(art_folder, "background.jpg"))
                        tgt_img = get_base64_image(os.path.join(art_folder, "target_ship.png"))
                        a1_img = get_base64_image(os.path.join(art_folder, "attacker1.png"))
                        a2_img = get_base64_image(os.path.join(art_folder, "attacker2.png"))
                            
                        data_script = f"""
                        <script>
                            const SIM_DATA = {{
                                frames: {json_frames},
                                initialDistance: {t3_dist},
                                shieldFaces: {int(shield_faces_val)},
                                images: {{
                                    bg: {json.dumps(bg_img)},
                                    target: {json.dumps(tgt_img)},
                                    a1: {json.dumps(a1_img)},
                                    a2: {json.dumps(a2_img)}
                                }}
                            }};
                        </script>
                        """
                        
                        logic_script = f"<script>\n{js_logic}\n</script>"
                        final_html = html_template.replace("__CANVAS_W__", str(canvas_w)) \
                                                  .replace("__DATA_INJECTION__", data_script) \
                                                  .replace("__JS_INJECTION__", logic_script)
                                                  
                        components.html(final_html, height=650, scrolling=True)

                        # --- NEW: RENDER COMBAT TELEMETRY LOG ---
                        st.divider()
                        st.subheader("📡 Combat Telemetry Log")
                        st.markdown("*(Real-time mathematical milestones tracking deflection, penetration, and component damage)*")
                        
                        for entry in combat_log:
                            st.markdown(f"<span style='color: {entry['color']}; font-family: monospace; font-size: 1rem;'><b>[{entry['t']:.2f}s]</b> - {entry['msg']}</span>", unsafe_allow_html=True)
                            
                    except FileNotFoundError as e:
                        st.error(f"Error loading visualizer files: {e}")