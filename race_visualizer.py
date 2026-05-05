import os
import json
import base64
import streamlit.components.v1 as components
from kinematics import ShipKinematics

# Accept the dictionary of allocations
def render_drag_race(db, selected_ship_names, mode="SCM", max_time=30, allocations=None):
    if allocations is None: allocations = {}
    if not selected_ship_names: return
        
    ship_data_payload = {}
    max_distance_overall = 0.0
    
    for name in selected_ship_names:
        # Use .copy() so we don't accidentally permanently modify the loaded database in memory
        flight_data = db.flight_data.get(name, {}).copy() 
        
        kinematics_engine = ShipKinematics(name, flight_data)
        
        # Grab the user's specific tick selection for THIS ship (default to max if not found)
        assigned_ticks = allocations.get(name, kinematics_engine.max_segments)
        
        timeline = kinematics_engine.generate_timeline(max_time, mode, dt=0.1, assigned_segments=assigned_ticks)

        # Find the max distance in the final frame to set our track length
        final_distance = timeline[-1]['distance']
        if final_distance > max_distance_overall:
            max_distance_overall = final_distance
            
        ship_data_payload[name] = timeline

    if max_distance_overall == 0: max_distance_overall = 1.0

    json_data = json.dumps(ship_data_payload)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # FIX: Point explicitly to the Drag Race UI files, NOT the TTK Combat UI files!
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

    # --- NEW: Load Ship Images as Base64 ---
    ship_images = {}
    for name in selected_ship_names:
        # Construct the filename using your exact folder structure
        img_path = os.path.join(script_dir, "Art", "Ship Art", f"{name}.png") 
        
        if os.path.exists(img_path):
            with open(img_path, "rb") as img_file:
                encoded = base64.b64encode(img_file.read()).decode()
                ship_images[name] = f"data:image/png;base64,{encoded}"
        else:
            print(f"DEBUG: Could not find image at: {img_path}")

    json_images = json.dumps(ship_images)
    # --- END NEW ---

    # --- UPDATE: Add SHIP_IMAGES to the injection string ---
    data_injection = f"""
    <script>
        window.SHIP_DATA = {json_data};
        window.MAX_DISTANCE = {max_distance_overall};
        window.MAX_TIME = {max_time};
        window.SHIP_IMAGES = {json_images}; 
    </script>
    """
    
    # Safe Injection: Split the HTML and insert everything right before </body>
    if "</body>" in html_content:
        parts = html_content.split("</body>")
        final_html = parts[0] + data_injection + f"\n<script>\n{js_content}\n</script>\n</body>" + parts[1]
    else:
        final_html = html_content + data_injection + f"\n<script>\n{js_content}\n</script>"

    height = 900 + (len(selected_ship_names) * 80) 
    components.html(final_html, height=height, scrolling=False)