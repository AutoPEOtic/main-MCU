import streamlit as st
import os
import sys
import time  # for sleep

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

temp_file = open("temp.txt", "r")
try:
    status, progress, PEO_time, KOH_concentration, Upos, Uneg, Ipos, Ineg = temp_file.read().split(";")
except:
    status = False
    progress = "no progress"
    PEO_time = KOH_concentration = Upos = Uneg = Ipos = Ineg = "N/A"
st.set_page_config(page_title="AutoPEOtic control panel", layout="wide")

temp_file.close()



# --- Top left logo & buttons ---
col1, col2, col3, col4 = st.columns([1, 3, 3, 3])

with col1:
    st.image("logo.png", width=120)

with col2:
    st.header("AutoPEOtic")

with col3:
    start_run = st.button("Set up new run", "start_run_button")

with col4:
    documentation_link = "[Documentation](https://docs.google.com/document/d/17tfXUzGl-OupitV5ytVnEuogHbemvR__a-Q2hwokxvw/edit?usp=sharing)"
    st.markdown(documentation_link, unsafe_allow_html=True)

# Redirect if "Start Run" is clicked
if start_run:
    st.write("Navigating to Start Run page (to be designed)…")

st.markdown("---")  # Divider

# --- Main Body ---
left_col, right_col = st.columns(2)

# Left column: Status & Stop
with left_col:
    st.subheader("Status")
    if status:
        st.success("Running...")
    else:
        st.error("Not running...")

    col1, col2 = st.columns([1, 1])
    with col1:

        stop = st.button("STOP")
        if stop:
            temp_file = open("temp.txt", "w")
            temp_file.truncate(0)
            temp_file.seek(0)
            temp_file.write("OFF")
            temp_file.close()

    with col2:
        start = st.button("START")
        if start:
            temp_file = open("temp.txt", "w")
            temp_file.truncate(0)
            temp_file.seek(0)
            temp_file.write("ON")
            temp_file.close()

    st.subheader("Progress")
    if progress == "cutting wire":
        st.info("cutting wire")
    else: st.text("cutting wire")

    if progress == "pumping":
        st.info("pumping")
    else: st.text("pumping")

    if progress == "doing PEO":
        st.info("doing PEO")
    else: st.text("doing PEO")
    
    if progress == "flushing":
        st.info("flushing")
    else: st.text("flushing")

    if progress == "drying":
        st.info("drying")
    else: st.text("drying")
    
    if progress == "measuring spectrum":
        st.info("measuring spectrum")
    else: st.text("mesuring spectrum")

    # Right column: Device values
    with right_col:
        st.subheader("Current Parameters")
        st.metric("PEO time", PEO_time)
        st.metric("KOH concentration", KOH_concentration)
        st.metric("Upos", Upos)
        st.metric("Uneg", Uneg)
        st.metric("Ipos", Ipos)
        st.metric("Ineg", Ineg)

time.sleep(2)
st.rerun()