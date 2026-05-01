import os
import json
import streamlit.components.v1 as components
from kinematics import ShipKinematics

def render_drag_race(db, selected_ship_names, mode="SCM", max_time=30):
    if not selected_ship_names:
        return
        
    # 1. Pre-calculate the physics data for smooth JS playback
    ship_data_payload = {}
    max_distance_overall = 0.0
    
    for name in selected_ship_names:
        flight_data = db.flight_data.get(name, {})
        kinematics_engine = ShipKinematics(name, flight_data)
        
        timeline = []
        for t_ticks in range(0, max_time * 10 + 1):
            t = t_ticks / 10.0
            state = kinematics_engine.calculate_state_at_time(t, mode)
            timeline.append(state)
            
            if state['distance'] > max_distance_overall:
                max_distance_overall = state['distance']
                
        ship_data_payload[name] = timeline

    if max_distance_overall == 0: max_distance_overall = 1.0

    json_data = json.dumps(ship_data_payload)

    # 2. Read the external HTML and JS files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(script_dir, "race_visualizer.html")
    js_path = os.path.join(script_dir, "race_visualizer.js")
    
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()
    except FileNotFoundError as e:
        import streamlit as st
        st.error(f"Missing visualizer file: {e}")
        return

    # 3. Inject the dynamic data and the Javascript into the HTML
    data_injection = f"""
    <script>
        window.SHIP_DATA = {json_data};
        window.MAX_DISTANCE = {max_distance_overall};
        window.MAX_TIME = {max_time};
    </script>
    """
    
    final_html = html_content.replace("", data_injection)
    final_html = final_html.replace("", f"<script>\n{js_content}\n</script>")

    # 4. Render the component in Streamlit
    height = 100 + (len(selected_ship_names) * 70) 
    components.html(final_html, height=height, scrolling=True)