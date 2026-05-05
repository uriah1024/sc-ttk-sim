import os
import streamlit as st
import streamlit.components.v1 as components

def render_aim_trainer_poc():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(script_dir, "aim_trainer.html")
    js_path = os.path.join(script_dir, "aim_trainer.js")

    # Safely load the static files
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()
    except FileNotFoundError as e:
        st.error(f"Missing aim trainer web asset: {e}")
        return

    # Inject the JavaScript directly into the HTML payload before the closing body tag
    if "</body>" in html_content:
        parts = html_content.split("</body>")
        final_html = parts[0] + f"<script>\n{js_content}\n</script>\n</body>" + parts[1]
    else:
        final_html = html_content + f"<script>\n{js_content}\n</script>"

    # Render the combined component
    components.html(final_html, height=750, scrolling=False)