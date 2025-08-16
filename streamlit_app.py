import streamlit as st
import pandas as pd
import os
import numpy as np
from datetime import date, timedelta, datetime
import pydeck as pdk
import recommendation_tool as recommendation

# ---- flatten flights_json into readable columns ----
def _fmt(ts):
    try:
        return datetime.fromisoformat(str(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts) if ts else ""

def _leg_columns(df_in: pd.DataFrame) -> pd.DataFrame:
    df_out = df_in.copy()
    # add empty columns (safe even if we re-run)
    for col in [
        "Leg 1 Flight", "Leg 1 Departs", "Leg 1 Arrives",
        "Leg 2 Flight", "Leg 2 Departs", "Leg 2 Arrives",
        "Layover (min)"
    ]:
        if col not in df_out.columns:
            df_out[col] = ""

    # iterate rows to extract legs
    for i, row in df_out.iterrows():
        legs = row.get("flights_json", [])
        if isinstance(legs, list) and len(legs) >= 1:
            l1 = legs[0]
            l1_label = f"{l1.get('airline','')} {l1.get('flight_number','')}".strip()
            df_out.at[i, "Leg 1 Flight"]  = l1_label
            df_out.at[i, "Leg 1 Departs"] = _fmt(l1.get("departure_time"))
            df_out.at[i, "Leg 1 Arrives"] = _fmt(l1.get("arrival_time"))

        if isinstance(legs, list) and len(legs) >= 2:
            l2 = legs[1]
            l2_label = f"{l2.get('airline','')} {l2.get('flight_number','')}".strip()
            df_out.at[i, "Leg 2 Flight"]  = l2_label
            df_out.at[i, "Leg 2 Departs"] = _fmt(l2.get("departure_time"))
            df_out.at[i, "Leg 2 Arrives"] = _fmt(l2.get("arrival_time"))

            # compute layover
            try:
                arr1 = datetime.fromisoformat(legs[0]["arrival_time"])
                dep2 = datetime.fromisoformat(legs[1]["departure_time"])
                lay = int((dep2 - arr1).total_seconds() / 60)
                df_out.at[i, "Layover (min)"] = str(lay)  # Convert to string to avoid type issues
            except Exception:
                df_out.at[i, "Layover (min)"] = ""

    # remove raw object column from UI/CSV
    if "flights_json" in df_out.columns:
        df_out = df_out.drop(columns=["flights_json"])
    return df_out

# Page config
st.set_page_config(
    page_title="Rewards Redemption Optimizer",
    page_icon="✈️",
    layout="wide"
)

# Load and inject CSS
with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Hero section
st.markdown("""
<div class="hero">
    <h1>✈️ Rewards Redemption Optimizer</h1>
    <p>Find the best value airline routes using miles vs cash</p>
</div>
""", unsafe_allow_html=True)

# Dataset Tips card
st.markdown("""
<div class="tips-card" id="dataset-tips">
    <h3>📋 Dataset Tips</h3>
    <ul>
        <li><strong>Origins:</strong> LAX, JFK, DXB, DFW, ORD, ATL</li>
        <li>⚠️ <strong>For synthetic routing to work consistently, use LAX as the origin</strong></li>
        <li><strong>Destinations:</strong> JFK, LHR, DXB, ORD, ATL, DFW</li>
        <li>⚠️ <strong>Synthetic is most likely to be selected as best value with JFK or LHR</strong></li>
        <li><strong>Dates:</strong> Only August 2025 is supported</li>
        <li>– Aug 31 has no layover data (directs only)</li>
        <li>– For LHR as destination, use Aug 2–26 for best coverage</li>
        <li><strong>Missing routes:</strong> DXB → LHR and LHR → JFK do not exist in the DB, as well as some other pairs</li>
    </ul>
</div>
""", unsafe_allow_html=True)

# Sidebar inputs
st.sidebar.header("🎯 Search Parameters")

# Airport selections
origin_options = ["LAX", "JFK", "DXB", "DFW", "ORD", "ATL"]
destination_options = ["JFK", "LHR", "DXB", "ORD", "ATL", "DFW"]

origin = st.sidebar.selectbox(
    "Origin Airport",
    origin_options,
    index=0,  # Default to LAX
    help="For synthetic routing to work consistently, use LAX as origin"
)

destination = st.sidebar.selectbox(
    "Destination Airport",
    destination_options,
    index=0,  # Default to JFK
    help="Synthetic often best with JFK or LHR"
)

# Date inputs with validation
today = date.today()
default_start = date(2025, 8, 15)  # Default to mid-August 2025
default_end = default_start

start_date = st.sidebar.date_input(
    "Start Date",
    value=default_start,
    min_value=date(2025, 8, 1),
    max_value=date(2025, 8, 31)
)

end_date = st.sidebar.date_input(
    "End Date",
    value=default_end,
    min_value=date(2025, 8, 1),
    max_value=date(2025, 8, 31)
)

# Other parameters
include_synthetic = st.sidebar.checkbox(
    "Include Synthetic Routes",
    value=True,
    help="Include routes with layovers/connections"
)

min_layover_minutes = st.sidebar.slider(
    "Minimum Layover (minutes)",
    min_value=0,
    max_value=240,
    value=45,
    help="Minimum connection time between flights"
)

ui_objective = st.sidebar.selectbox(
    "Objective",
    ["Value per Mile", "Minimum Price"],
    index=0,
    help="Choose how to rank the results."
)

min_vpm_cents = st.sidebar.number_input(
    "Minimum Value per Mile (¢)",
    min_value=0.0,
    value=0.0,
    step=0.1,
    help="Filter routes below this value per mile threshold"
)

max_price = st.sidebar.number_input(
    "Maximum Price ($)",
    min_value=0.0,
    value=0.0,
    step=10.0,
    help="Filter routes above this price threshold"
)

airline_allowlist_text = st.sidebar.text_input(
    "Allowed Airlines (comma-separated)",
    value="",
    placeholder="e.g., American Airlines, Delta, JetBlue",
    help="Leave blank to include all airlines"
)

miles_balance = st.sidebar.number_input(
    "Your Miles Balance",
    min_value=0,
    value=0,
    step=1000,
    help="Optional: Your current miles balance for filtering"
)

max_results = st.sidebar.number_input(
    "Maximum Results",
    min_value=1,
    max_value=1000,
    value=100
)



# Validation checks
errors = []
warnings = []
infos = []

# Date validation
if start_date < date(2025, 8, 1) or start_date > date(2025, 8, 31):
    errors.append("Start date must be in August 2025")
if end_date < date(2025, 8, 1) or end_date > date(2025, 8, 31):
    errors.append("End date must be in August 2025")

# Route validation
if (origin == "DXB" and destination == "LHR") or (origin == "LHR" and destination == "JFK"):
    errors.append(f"Route {origin} → {destination} does not exist in the database")

# Database file check
if not os.path.exists("travel_data_with_miles.db"):
    errors.append("Database file 'travel_data_with_miles.db' not found")

# Special date warnings
if start_date <= date(2025, 8, 31) <= end_date and include_synthetic:
    infos.append("Aug 31 has only direct flights; synthetic may return zero results")

if destination == "LHR" and (end_date < date(2025, 8, 2) or start_date > date(2025, 8, 26)):
    warnings.append("For LHR destination, use dates between Aug 2-26 for best coverage")

# Display validation messages
for error in errors:
    st.error(error)

for warning in warnings:
    st.warning(warning)

for info in infos:
    st.info(info)

# Helper function to run search and cache results
def _run_search_and_cache():
    # call backend exactly as we already do (objective="vpm" per our previous change)
    results = recommendation.recommend_routes(
        origin=origin,
        destination=destination,
        start_date=str(start_date),
        end_date=str(end_date),
        include_synthetic=include_synthetic,
        min_layover_minutes=int(min_layover_minutes),
        objective="vpm",  # always vpm; UI decides final sort
        min_vpm_cents=min_vpm_cents_arg,
        max_price=max_price_arg,
        airline_allowlist=airline_allowlist_list,
        max_results=int(max_results),
        db_path="travel_data_with_miles.db",
    )
    df_local = pd.DataFrame(results) if not isinstance(results, pd.DataFrame) else results.copy()
    # store in session for later toggles / chart interactions
    st.session_state["results_df"] = df_local
    return df_local

# Main content
if not errors:
    # Parse inputs for backend call
    airline_allowlist_list = None
    if airline_allowlist_text.strip():
        airline_allowlist_list = [airline.strip() for airline in airline_allowlist_text.split(",") if airline.strip()]
    
    min_vpm_cents_arg = None if min_vpm_cents <= 0 else min_vpm_cents
    max_price_arg = None if max_price <= 0 else max_price
    
    # Search button with session state persistence
    search_clicked = st.button("🔍 Search Routes", type="primary")
    
    if search_clicked:
        df = _run_search_and_cache()
    elif "results_df" in st.session_state:
        df = st.session_state["results_df"].copy()
    else:
        df = pd.DataFrame()
    
    if df.empty:
        st.markdown("""
        <div class="info-card">
            <h3>No routes found</h3>
            <p>No routes found for these settings. Try adjusting your filters or date range.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Process results
        # Rename and add computed columns
        df = df.rename(columns={"value_per_mile_cents": "Value per Mile (¢)"})
        df["Estimated $ Saved"] = np.maximum(df["price"] - df["taxes"], 0).round(2)
        
        # Flatten flights_json into readable columns
        df = _leg_columns(df)
        
        # --- Robust "within my miles" handling (works across reruns) ---
        if not df.empty and "miles" in df.columns:
            df["miles"] = pd.to_numeric(df["miles"], errors="coerce")

        only_within = False
        within_mask = pd.Series(False, index=df.index)

        if miles_balance and miles_balance > 0 and not df.empty:
            within_mask = (df["miles"] <= int(miles_balance))
            num_within = int(within_mask.sum())

            if num_within > 0:
                only_within = st.toggle(
                    f"Show only routes within my miles ({num_within} found)",
                    value=False,
                    key="within_toggle"
                )
            else:
                st.toggle("Show only routes within my miles", value=False, disabled=True, key="within_toggle")
                st.caption(f"No routes are within your miles balance ({int(miles_balance):,}).")

            df["Within Your Miles?"] = within_mask

        # Build view_df (never let the table disappear)
        if only_within and within_mask.any():
            view_df = df.loc[within_mask].copy()
        elif only_within and not within_mask.any():
            st.info(f"No routes within {int(miles_balance):,} miles. Showing all results instead.")
            view_df = df.copy()
        else:
            view_df = df.copy()
        
        # Global sort based on UI objective
        if "Value per Mile (¢)" in view_df.columns and "price" in view_df.columns:
            if ui_objective == "Minimum Price":
                if "taxes" in view_df.columns:
                    view_df = view_df.sort_values(
                        ["price", "taxes", "Value per Mile (¢)"],
                        ascending=[True, True, False],
                        kind="mergesort"
                    )
                else:
                    view_df = view_df.sort_values(["price", "Value per Mile (¢)"], ascending=[True, False], kind="mergesort")
            else:
                view_df = view_df.sort_values(
                    ["Value per Mile (¢)", "price"],
                    ascending=[False, True],
                    kind="mergesort"
                )
        
        # Preferred columns order
        preferred_cols = [
            "date", "type", "origin", "destination", "airline",
            "price", "miles", "taxes", "Value per Mile (¢)", "Estimated $ Saved",
            "route", "Layover (min)",
            "Leg 1 Flight", "Leg 1 Departs", "Leg 1 Arrives",
            "Leg 2 Flight", "Leg 2 Departs", "Leg 2 Arrives",
            "Within Your Miles?"
        ]
        
        # ---- Map (optional via airports.csv) ----
        import os, re, pandas as pd, pydeck as pdk

        st.markdown("### 🗺️ Map")

        csv_path = "airports.csv"
        if not os.path.exists(csv_path):
            st.caption("Add **airports.csv** (columns: `iata,lat,lon`) to enable the map.")
        else:
            airports_df = pd.read_csv(csv_path)
            airports_df["iata"] = airports_df["iata"].astype(str).str.upper()

            codes = set()

            # from columns
            if "origin" in view_df.columns:
                codes |= set(view_df["origin"].dropna().astype(str).str.upper().tolist())
            if "destination" in view_df.columns:
                codes |= set(view_df["destination"].dropna().astype(str).str.upper().tolist())

            # try to parse tokens like LAX, DEN, JFK inside the route column if it exists
            if "route" in view_df.columns:
                for r in view_df["route"].astype(str).fillna(""):
                    for tok in re.findall(r"\b[A-Z]{3}\b", r):
                        codes.add(tok)

            pins = airports_df[airports_df["iata"].isin(sorted(codes))].copy()

            if pins.empty:
                st.caption("No matching airports from current results found in **airports.csv**.")
            else:
                # pydeck wants columns named lon/lat
                pins = pins.rename(columns={"lon": "longitude", "lat": "latitude"})
                midpoint = {
                    "latitude": float(pins["latitude"].mean()),
                    "longitude": float(pins["longitude"].mean()),
                }

                # set a reasonable zoom (wider if points spread out)
                if len(pins) == 1:
                    zoom = 8
                else:
                    zoom = 3

                layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=pins,
                    get_position="[longitude, latitude]",
                    get_color=[255, 69, 0, 255],  # Bright orange-red color
                    get_radius=100000,  # Larger radius for better visibility
                    pickable=True,
                )

                tooltip = {"text": "{iata}"}

                view_state = pdk.ViewState(
                    latitude=midpoint["latitude"], longitude=midpoint["longitude"], zoom=zoom
                )

                st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip))

        
        # Layout: two columns
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📊 Results")
            
            if view_df.empty:
                st.info("No routes match your current filters.")
            else:
                # Display sortable table with preferred column order
                cols_to_show = [c for c in preferred_cols if c in view_df.columns]
                st.dataframe(
                    view_df[cols_to_show] if cols_to_show else view_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Download button
                st.download_button(
                    label="📥 Download CSV",
                    data=view_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"recommendations_{origin}_{destination}_{start_date}_{end_date}.csv",
                    mime="text/csv"
                )
        
        with col2:
            st.subheader("📈 Summary & Charts")
            
            if not view_df.empty:
                # Summary metrics
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-value">{len(view_df)}</div>
                    <div class="metric-label">Total Routes</div>
                </div>
                """, unsafe_allow_html=True)
                
                if "Value per Mile (¢)" in view_df.columns:
                    best_vpm = view_df["Value per Mile (¢)"].max()
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{best_vpm:.2f}¢</div>
                        <div class="metric-label">Best Value/Mile</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Charts - Top 10 with unique labels
                if not view_df.empty and "Value per Mile (¢)" in view_df.columns:
                    st.write("**Top 10 by Value per Mile**")
                    top = view_df.nlargest(10, "Value per Mile (¢)").copy()
                    safe_type = top.get("type").astype(str) if "type" in top.columns else ""
                    top["Label"] = top["airline"].astype(str) + " • " + top["date"].astype(str) + " • " + safe_type
                    top = top.set_index("Label")
                    st.bar_chart(top[["Value per Mile (¢)"]])
                
                if "price" in view_df.columns and "miles" in view_df.columns and len(view_df) > 1:
                    st.write("**Price vs Miles**")
                    st.scatter_chart(view_df, x="miles", y="price")


