# --- show startup errors on the page instead of a blank crash ---
import traceback
import streamlit as st

def _render_startup_error(e: Exception):
    st.error(f"Startup error: {e}")
    st.code("".join(traceback.format_exc()), language="python")

# ----------------------------- app code -----------------------------

import os
import re
from datetime import date, timedelta, datetime

import numpy as np
import pandas as pd
import pydeck as pdk

import recommendation_tool as recommendation


# --------------- helpers: leg flattening / formatting ----------------
def _fmt(ts):
    try:
        return datetime.fromisoformat(str(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts) if ts else ""

def _leg_columns(df_in: pd.DataFrame) -> pd.DataFrame:
    """Expand flights_json into readable columns + layover minutes."""
    df_out = df_in.copy()

    for col in [
        "Leg 1 Flight", "Leg 1 Departs", "Leg 1 Arrives",
        "Leg 2 Flight", "Leg 2 Departs", "Leg 2 Arrives",
        "Layover (min)"
    ]:
        if col not in df_out.columns:
            df_out[col] = ""

    for i, row in df_out.iterrows():
        legs = row.get("flights_json", [])
        if isinstance(legs, list) and len(legs) >= 1:
            l1 = legs[0]
            df_out.at[i, "Leg 1 Flight"]  = f"{l1.get('airline','')} {l1.get('flight_number','')}".strip()
            df_out.at[i, "Leg 1 Departs"] = _fmt(l1.get("departure_time"))
            df_out.at[i, "Leg 1 Arrives"] = _fmt(l1.get("arrival_time"))

        if isinstance(legs, list) and len(legs) >= 2:
            l2 = legs[1]
            df_out.at[i, "Leg 2 Flight"]  = f"{l2.get('airline','')} {l2.get('flight_number','')}".strip()
            df_out.at[i, "Leg 2 Departs"] = _fmt(l2.get("departure_time"))
            df_out.at[i, "Leg 2 Arrives"] = _fmt(l2.get("arrival_time"))
            # layover
            try:
                arr1 = datetime.fromisoformat(legs[0]["arrival_time"])
                dep2 = datetime.fromisoformat(legs[1]["departure_time"])
                lay = int((dep2 - arr1).total_seconds() / 60)
                df_out.at[i, "Layover (min)"] = lay
            except Exception:
                df_out.at[i, "Layover (min)"] = ""

    if "flights_json" in df_out.columns:
        df_out = df_out.drop(columns=["flights_json"])
    return df_out


def app():
    # ---- page config
    st.set_page_config(page_title="Rewards Redemption Optimizer", page_icon="✈️", layout="wide")

    # ---- CSS (don’t crash if file missing)
    try:
        with open("style.css", "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

    # ---- hero
    st.markdown(
        """
        <div class="hero">
            <h1>✈️ Rewards Redemption Optimizer</h1>
            <p>Find the best value airline routes using miles vs cash</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- dataset tips
    st.markdown(
        """
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
                <li><strong>Missing routes:</strong> DXB → LHR and LHR → JFK don’t exist in the DB, as well as some other pairs</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------- SIDEBAR: inputs ---------------------
    st.sidebar.header("🎯 Search Parameters")

    origin_options = ["LAX", "JFK", "DXB", "DFW", "ORD", "ATL"]
    destination_options = ["JFK", "LHR", "DXB", "ORD", "ATL", "DFW"]

    origin = st.sidebar.selectbox("Origin Airport", origin_options, index=0,
                                  help="For synthetic routing to work consistently, use LAX as origin")
    destination = st.sidebar.selectbox("Destination Airport", destination_options, index=0,
                                       help="Synthetic often best with JFK or LHR")

    default_start = date(2025, 8, 15)
    start_date = st.sidebar.date_input("Start Date", value=default_start,
                                       min_value=date(2025, 8, 1), max_value=date(2025, 8, 31))
    end_date = st.sidebar.date_input("End Date", value=default_start,
                                     min_value=date(2025, 8, 1), max_value=date(2025, 8, 31))

    include_synthetic = st.sidebar.checkbox("Include Synthetic Routes", value=True)
    min_layover_minutes = st.sidebar.slider("Minimum Layover (minutes)", 0, 240, 45,
                                            help="Minimum connection time between flights")

    ui_objective = st.sidebar.selectbox("Objective", ["Value per Mile", "Minimum Price"], index=0,
                                        help="Choose how to rank the results.")

    min_vpm_cents = st.sidebar.number_input("Minimum Value per Mile (¢)", min_value=0.0, value=0.0, step=0.1)
    max_price = st.sidebar.number_input("Maximum Price ($)", min_value=0.0, value=0.0, step=10.0)

    airline_allowlist_text = st.sidebar.text_input(
        "Allowed Airlines (comma-separated)",
        value="",
        placeholder="e.g., American Airlines, Delta, JetBlue",
        help="Leave blank to include all airlines",
    )

    miles_balance = st.sidebar.number_input("Your Miles Balance", min_value=0, value=0, step=1000)
    max_results = st.sidebar.number_input("Maximum Results", min_value=1, max_value=1000, value=100)

    # ------------------ validations / messages ------------------
    errors, warnings, infos = [], [], []

    if not (date(2025, 8, 1) <= start_date <= date(2025, 8, 31)):
        errors.append("Start date must be in August 2025.")
    if not (date(2025, 8, 1) <= end_date <= date(2025, 8, 31)):
        errors.append("End date must be in August 2025.")

    if (origin == "DXB" and destination == "LHR") or (origin == "LHR" and destination == "JFK"):
        errors.append(f"Route {origin} → {destination} does not exist in the database.")

    if not os.path.exists("travel_data_with_miles.db"):
        errors.append("Database file 'travel_data_with_miles.db' not found in the repo root.")

    if start_date <= date(2025, 8, 31) <= end_date and include_synthetic:
        infos.append("Aug 31 has only direct flights; synthetic may return zero results.")
    if destination == "LHR" and (end_date < date(2025, 8, 2) or start_date > date(2025, 8, 26)):
        warnings.append("For LHR destination, use dates between Aug 2–26 for best coverage.")

    for m in errors: st.error(m)
    for m in warnings: st.warning(m)
    for m in infos: st.info(m)

    # ------------------- run backend (on click) -------------------
    def _run_search_and_cache():
        airline_allowlist_list = None
        if airline_allowlist_text.strip():
            airline_allowlist_list = [a.strip() for a in airline_allowlist_text.split(",") if a.strip()]

        min_vpm_cents_arg = None if min_vpm_cents <= 0 else float(min_vpm_cents)
        max_price_arg = None if max_price <= 0 else float(max_price)

        results = recommendation.recommend_routes(
            origin=origin,
            destination=destination,
            start_date=str(start_date),
            end_date=str(end_date),
            include_synthetic=include_synthetic,
            min_layover_minutes=int(min_layover_minutes),
            objective="vpm",                 # always compute by VPM; UI decides final sort
            min_vpm_cents=min_vpm_cents_arg,
            max_price=max_price_arg,
            airline_allowlist=airline_allowlist_list,
            max_results=int(max_results),
            db_path="travel_data_with_miles.db",
        )
        df_local = results if isinstance(results, pd.DataFrame) else pd.DataFrame(results)
        st.session_state["results_df"] = df_local
        return df_local

    if not errors:
        clicked = st.button("🔍 Search Routes", type="primary")
        if clicked:
            df = _run_search_and_cache()
        elif "results_df" in st.session_state:
            df = st.session_state["results_df"].copy()
        else:
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()

    # ---------------------- display results ----------------------
    if df.empty:
        st.markdown(
            """
            <div class="info-card">
                <h3>No routes found</h3>
                <p>No routes found for these settings. Try adjusting your filters or date range.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # rename & compute
    if "value_per_mile_cents" in df.columns:
        df = df.rename(columns={"value_per_mile_cents": "Value per Mile (¢)"})
    if {"price", "taxes"}.issubset(df.columns):
        df["Estimated $ Saved"] = np.maximum(df["price"] - df["taxes"], 0).round(2)

    # flatten legs
    df = _leg_columns(df)

    # ensure numeric for miles
    if "miles" in df.columns:
        df["miles"] = pd.to_numeric(df["miles"], errors="coerce")

    # within-my-miles toggle (never hide the whole table)
    only_within = False
    within_mask = pd.Series(False, index=df.index)
    if miles_balance and miles_balance > 0 and not df.empty and "miles" in df.columns:
        within_mask = (df["miles"] <= int(miles_balance))
        n = int(within_mask.sum())
        if n > 0:
            only_within = st.toggle(f"Show only routes within my miles ({n} found)", value=False, key="within_toggle")
        else:
            st.toggle("Show only routes within my miles", value=False, disabled=True, key="within_toggle")
            st.caption(f"No routes are within your miles balance ({int(miles_balance):,}).")

        df["Within Your Miles?"] = within_mask

    if only_within and within_mask.any():
        view_df = df.loc[within_mask].copy()
    elif only_within and not within_mask.any():
        st.info(f"No routes within {int(miles_balance):,} miles. Showing all results instead.")
        view_df = df.copy()
    else:
        view_df = df.copy()

    # global sort according to UI objective (stable mergesort to not split direct/synthetic sections)
    if {"Value per Mile (¢)", "price"}.issubset(view_df.columns):
        if ui_objective == "Minimum Price":
            if "taxes" in view_df.columns:
                view_df = view_df.sort_values(["price", "taxes", "Value per Mile (¢)"],
                                              ascending=[True, True, False], kind="mergesort")
            else:
                view_df = view_df.sort_values(["price", "Value per Mile (¢)"],
                                              ascending=[True, False], kind="mergesort")
        else:
            view_df = view_df.sort_values(["Value per Mile (¢)", "price"],
                                          ascending=[False, True], kind="mergesort")

    preferred_cols = [
        "date", "type", "origin", "destination", "airline",
        "price", "miles", "taxes", "Value per Mile (¢)", "Estimated $ Saved",
        "route", "Layover (min)",
        "Leg 1 Flight", "Leg 1 Departs", "Leg 1 Arrives",
        "Leg 2 Flight", "Leg 2 Departs", "Leg 2 Arrives",
        "Within Your Miles?"
    ]

    # --------------------------- map ---------------------------
    st.markdown("### 🗺️ Map")
    csv_path = "airports.csv"
    if not os.path.exists(csv_path):
        st.caption("Add **airports.csv** (columns: `iata,lat,lon`) to enable the map.")
    else:
        airports_df = pd.read_csv(csv_path)
        airports_df["iata"] = airports_df["iata"].astype(str).str.upper()

        codes = set()
        if "origin" in view_df.columns:
            codes |= set(view_df["origin"].dropna().astype(str).str.upper())
        if "destination" in view_df.columns:
            codes |= set(view_df["destination"].dropna().astype(str).str.upper())
        if "route" in view_df.columns:
            for r in view_df["route"].astype(str).fillna(""):
                for tok in re.findall(r"\b[A-Z]{3}\b", r):
                    codes.add(tok)

        pins = airports_df[airports_df["iata"].isin(sorted(codes))].copy()
        if pins.empty:
            st.caption("No matching airports from current results found in **airports.csv**.")
        else:
            pins = pins.rename(columns={"lon": "longitude", "lat": "latitude"})
            midpoint = {"latitude": float(pins["latitude"].mean()), "longitude": float(pins["longitude"].mean())}
            zoom = 8 if len(pins) == 1 else 3

            layer = pdk.Layer(
                "ScatterplotLayer",
                data=pins,
                get_position="[longitude, latitude]",
                get_color=[255, 69, 0, 255],
                get_radius=100000,
                pickable=True,
            )
            view_state = pdk.ViewState(latitude=midpoint["latitude"], longitude=midpoint["longitude"], zoom=zoom)
            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "{iata}"}))

    # --------------------- layout: table + charts ---------------------
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📊 Results")
        if view_df.empty:
            st.info("No routes match your current filters.")
        else:
            cols_to_show = [c for c in preferred_cols if c in view_df.columns]
            st.dataframe(view_df[cols_to_show] if cols_to_show else view_df, use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Download CSV",
                data=view_df.to_csv(index=False).encode("utf-8"),
                file_name=f"recommendations_{origin}_{destination}_{start_date}_{end_date}.csv",
                mime="text/csv",
            )

    with col2:
        st.subheader("📈 Summary & Charts")
        if not view_df.empty:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-value">{len(view_df)}</div>
                    <div class="metric-label">Total Routes</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if "Value per Mile (¢)" in view_df.columns:
                best_vpm = view_df["Value per Mile (¢)"].max()
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-value">{best_vpm:.2f}¢</div>
                        <div class="metric-label">Best Value/Mile</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            # bar: unique labels so bars don't stack by airline name
            if "Value per Mile (¢)" in view_df.columns and not view_df.empty:
                st.write("**Top 10 by Value per Mile**")
                top = view_df.nlargest(10, "Value per Mile (¢)").copy()
                safe_type = top["type"].astype(str) if "type" in top.columns else ""
                top["Label"] = top["airline"].astype(str) + " • " + top["date"].astype(str) + " • " + safe_type
                top = top.set_index("Label")
                st.bar_chart(top[["Value per Mile (¢)"]])

            if {"price", "miles"}.issubset(view_df.columns) and len(view_df) > 1:
                st.write("**Price vs Miles**")
                st.scatter_chart(view_df, x="miles", y="price")


# ---------------------------- run app ----------------------------
if __name__ == "__main__":
    try:
        app()
    except Exception as e:
        _render_startup_error(e)
