import streamlit as st

# Set page config
st.set_page_config(page_title="Device Control UI", layout="wide")

# --- Top left logo & buttons ---
col1, col2, col3, col4 = st.columns([1, 3, 3, 3])

with col1:
    st.image("logo.png", width=120)

with col2:
    st.header("AutoPEOtic")

with col3:
    st.write("")  # Spacer
    start_run = st.button("🚀 Set up new run")


with col4:
    st.write("")  # Spacer

    documentation_link = "[📄 Documentation](https://docs.google.com/document/d/17tfXUzGl-OupitV5ytVnEuogHbemvR__a-Q2hwokxvw/edit?usp=sharing)"
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
    st.success("Running...")
    #st.error("Not running...")

    col1, col2 = st.columns([1, 7])
    with col1: stop = st.button("🛑 STOP")
    with col2: start = st.button("🟢 START")

    if stop:
        st.warning("Stop command sent!")

    st.subheader("Progress")
    st.text("cutting wire")
    st.text("pumping")
    st.info("doing PEO")
    st.text("flushing")
    st.text("drying")
    st.text("measuring spectrum")

# Right column: Device values
with right_col:
    st.subheader("Current Parameters")
    st.metric("PEO time", "30s")
    st.metric("KOH concentration", "0.5 g/L")
    st.metric("Upos", "500 V")
    st.metric("Uneg", "100 V")
    # Add more metrics or live graphs here

