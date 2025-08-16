# this file is used to get the data from the database and return it in a way that can be used by the recommendation tool
import sqlite3
import re
from datetime import datetime, timedelta  # this is used for the layover routes to make sure that the 2nd flight departs after the first flight arrives



# utilizing Kathan's value-per-mile function
def calculate_value_per_mile(cash_price, taxes_and_fees, miles_used):
    if miles_used == 0:
        raise ValueError("Miles used cannot be zero.")
    value = (cash_price - taxes_and_fees) / miles_used
    return round(value * 100, 2)


# gets all of the direct flights from the database for a given origin, destination, and date
def get_direct_flights(origin, destination, date):
    conn = sqlite3.connect("travel_data_with_miles.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT airline, flight_number, departure_time, arrival_time, price, miles
        FROM flights
        WHERE route_origin = ? AND route_destination = ? AND date = ?
    """, (origin, destination, date))

    results = cursor.fetchall()
    conn.close()
    return results


# finds all hub airports that have flights from origin and to destination on the given date
def get_possible_hub_airports(origin, destination, date):
    conn = sqlite3.connect("travel_data_with_miles.db")
    cursor = conn.cursor()

    # get all airports the origin flies to on this date
    cursor.execute("""
        SELECT DISTINCT route_destination
        FROM flights
        WHERE route_origin = ? AND date = ?
    """, (origin, date))
    from_origin = set(row[0] for row in cursor.fetchall())

    # get all airports that fly to the destination on this date
    cursor.execute("""
        SELECT DISTINCT route_origin
        FROM flights
        WHERE route_destination = ? AND date = ?
    """, (destination, date))
    to_dest = set(row[0] for row in cursor.fetchall())

    conn.close()

    # intersection gives us valid hubs
    return list(from_origin & to_dest)


# since there are no specific taxes/fees in the database, we will estimate them based on the origin and destination
def estimate_taxes_and_fees(origin, destination):
    # higher fees for international routes, lower for domestic
    international_routes = [("JFK", "LHR"), ("DXB", "LHR"), ("LAX", "HND")]
    if (origin, destination) in international_routes:
        return 50.00
    else:
        return 11.20


# gets all of the routes with layovers for a given origin, destination, date, and hub airports
def get_synthetic_routes(origin, destination, date, hub_airports, min_layover_minutes=45):
    conn = sqlite3.connect("travel_data_with_miles.db")
    cursor = conn.cursor()
    synthetic_routes = []

    for hub in hub_airports:
        # first leg: origin to midway hub
        cursor.execute("""
            SELECT airline, flight_number, departure_time, arrival_time, price, miles
            FROM flights
            WHERE route_origin = ? AND route_destination = ? AND date = ?
        """, (origin, hub, date))
        first_legs = cursor.fetchall()

        # second leg: midway hub to destination
        cursor.execute("""
            SELECT airline, flight_number, departure_time, arrival_time, price, miles
            FROM flights
            WHERE route_origin = ? AND route_destination = ? AND date = ?
        """, (hub, destination, date))
        second_legs = cursor.fetchall()

        for flight1 in first_legs:
            for flight2 in second_legs:
                # make sure the layover timing is valid (ex. if flight1 arrives at 12:00, flight2 must depart after that)
                arr1 = datetime.fromisoformat(flight1[3])
                dep2 = datetime.fromisoformat(flight2[2])

                # ✅ enforce minimum layover window
                if dep2 <= arr1 + timedelta(minutes=min_layover_minutes):
                    continue

                total_price = flight1[4] + flight2[4]
                total_miles = flight1[5] + flight2[5]
                taxes = estimate_taxes_and_fees(origin, hub) + estimate_taxes_and_fees(hub, destination)
                synthetic_routes.append((hub, flight1, flight2, total_price, total_miles, taxes))

    conn.close()
    return synthetic_routes


# main function to recommend the best route based on value per mile
def recommend_best_route(origin, destination, date, hub_airports, min_layover_minutes=45):
    direct_options = get_direct_flights(origin, destination, date)
    synthetic_options = get_synthetic_routes(
        origin, destination, date, hub_airports, min_layover_minutes=min_layover_minutes
    )

    all_options = []

    # addressing direct flights
    for flight in direct_options:
        airline, flight_number, dep, arr, price, miles = flight
        taxes = estimate_taxes_and_fees(origin, destination)
        value = calculate_value_per_mile(price, taxes, miles)

        all_options.append({  # creating a dictionary for each flight option
            "type": "Direct",
            "route": [(origin, destination)],
            "flights": [flight],
            "price": price,
            "miles": miles,
            "taxes": taxes,
            "value_per_mile": value
        })

    # addressing flights with layovers
    for hub, flight1, flight2, total_price, total_miles, taxes in synthetic_options:
        value = calculate_value_per_mile(total_price, taxes, total_miles)

        all_options.append({
            "type": "Synthetic",
            "route": [(origin, hub), (hub, destination)],
            "flights": [flight1, flight2],
            "price": total_price,
            "miles": total_miles,
            "taxes": taxes,
            "value_per_mile": value
        })

    # if no flight options are available, return a message
    if not all_options:
        return "No flights available for that day."

    # determining the best option based on value per mile. looks through each dictionary in the list called all_options, finding which has the highest value of the key value_per_mile
    best_option = max(all_options, key=lambda x: x["value_per_mile"])
    return best_option

# now allows users to get recommendations for a range of dates, with more options and filters
import pandas as pd

def recommend_routes(
    origin: str,
    destination: str,
    start_date: str,
    end_date: str,
    include_synthetic: bool = True,
    min_layover_minutes: int = 45,
    objective: str = "vpm",             # "vpm" or "min_fees"
    min_vpm_cents = None,        # e.g., 1.2 (cents)
    max_price = None,            # e.g., 350.0 ($)
    airline_allowlist = None,  # e.g., ["AA","DL","B6"]
    max_results: int = 100,
    db_path: str = "travel_data_with_miles.db",
) -> pd.DataFrame:
    """
    Return a DataFrame of candidate routes across a date range for UI consumption.
    Columns (at minimum): date, type, origin, destination, airline, price, miles, taxes, value_per_mile_cents, route, flights_json
    """
    # local helpers reuse your functions but allow db_path override
    def _get_direct_flights(origin, destination, date):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT airline, flight_number, departure_time, arrival_time, price, miles
            FROM flights
            WHERE route_origin = ? AND route_destination = ? AND date = ?
        """, (origin, destination, date))
        results = cursor.fetchall()
        conn.close()
        return results

    def _get_possible_hub_airports(origin, destination, date):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT route_destination
            FROM flights
            WHERE route_origin = ? AND date = ?
        """, (origin, date))
        from_origin = set(row[0] for row in cursor.fetchall())
        cursor.execute("""
            SELECT DISTINCT route_origin
            FROM flights
            WHERE route_destination = ? AND date = ?
        """, (destination, date))
        to_dest = set(row[0] for row in cursor.fetchall())
        conn.close()
        return list(from_origin & to_dest)

    def build_synthetic_routes(origin, destination, date, hub_airports):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        synthetic_routes = []
        for hub in hub_airports:
            cursor.execute("""
                SELECT airline, flight_number, departure_time, arrival_time, price, miles
                FROM flights
                WHERE route_origin = ? AND route_destination = ? AND date = ?
            """, (origin, hub, date))
            first_legs = cursor.fetchall()
            cursor.execute("""
                SELECT airline, flight_number, departure_time, arrival_time, price, miles
                FROM flights
                WHERE route_origin = ? AND route_destination = ? AND date = ?
            """, (hub, destination, date))
            second_legs = cursor.fetchall()

            for flight1 in first_legs:
                for flight2 in second_legs:
                    arr1 = datetime.fromisoformat(flight1[3])
                    dep2 = datetime.fromisoformat(flight2[2])

                    # layover rule
                    if dep2 <= arr1 + timedelta(minutes=min_layover_minutes):
                        continue

                    total_price = float(flight1[4]) + float(flight2[4])
                    total_miles = int(flight1[5]) + int(flight2[5])
                    taxes = estimate_taxes_and_fees(origin, hub) + estimate_taxes_and_fees(hub, destination)

                    synthetic_routes.append((hub, flight1, flight2, total_price, total_miles, taxes))
        conn.close()
        return synthetic_routes

    # iterate dates
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    if end < start:
        start, end = end, start

    rows = []
    day = start
    while day <= end:
        date_str = day.isoformat()

        # DIRECTS
        for f in _get_direct_flights(origin, destination, date_str):
            airline, flight_number, dep, arr, price, miles = f
            taxes = estimate_taxes_and_fees(origin, destination)
            vpm_cents = calculate_value_per_mile(float(price), float(taxes), int(miles))

            rows.append({
                "date": date_str,
                "type": "Direct",
                "origin": origin,
                "destination": destination,
                "airline": airline,
                "price": float(price),
                "miles": int(miles),
                "taxes": float(taxes),
                "value_per_mile_cents": float(vpm_cents),
                "route": [(origin, destination)],
                "flights_json": [
                    {"airline": airline, "flight_number": flight_number,
                     "departure_time": dep, "arrival_time": arr,
                     "price": float(price), "miles": int(miles)}
                ],
            })

        # SYNTHETIC
        if include_synthetic:
            hubs = _get_possible_hub_airports(origin, destination, date_str)
            for hub, f1, f2, total_price, total_miles, taxes in build_synthetic_routes(origin, destination, date_str, hubs):
                vpm_cents = calculate_value_per_mile(float(total_price), float(taxes), int(total_miles))
                rows.append({
                    "date": date_str,
                    "type": "Synthetic",
                    "origin": origin,
                    "destination": destination,
                    "airline": f"{f1[0]}+{f2[0]}",
                    "price": float(total_price),
                    "miles": int(total_miles),
                    "taxes": float(taxes),
                    "value_per_mile_cents": float(vpm_cents),
                    "route": [(origin, hub), (hub, destination)],
                    "flights_json": [
                        {"airline": f1[0], "flight_number": f1[1], "departure_time": f1[2], "arrival_time": f1[3], "price": float(f1[4]), "miles": int(f1[5])},
                        {"airline": f2[0], "flight_number": f2[1], "departure_time": f2[2], "arrival_time": f2[3], "price": float(f2[4]), "miles": int(f2[5])},
                    ],
                })
        day += timedelta(days=1)

    # Always use a fixed schema so empty results don't break the UI
    cols = [
        "date", "type", "origin", "destination", "airline", "price",
        "miles", "taxes", "value_per_mile_cents", "route", "flights_json"
    ]
    df = pd.DataFrame(rows, columns=cols)


    # filters
    if not df.empty:
        if min_vpm_cents is not None:
            df = df[df["value_per_mile_cents"] >= float(min_vpm_cents)]
        if max_price is not None:
            df = df[df["price"] <= float(max_price)]
        if airline_allowlist:
            # escape special regex characters, ignore empties, case-insensitive match
            pats = [re.escape(str(s).strip()) for s in airline_allowlist if s and str(s).strip()]
            if pats:
                pattern = "|".join(pats)
                df = df[df["airline"].str.contains(pattern, case=False, regex=True, na=False)]

        # objective sort
        if objective == "min_fees" and "taxes" in df.columns:
            df = df.sort_values(["taxes", "price", "value_per_mile_cents"], ascending=[True, True, False])
        else:
            df = df.sort_values(["value_per_mile_cents", "price"], ascending=[False, True])

        if max_results:
            df = df.head(int(max_results))

    return df.reset_index(drop=True)

# this function runs the recommendation tool, allowing users to input their origin, destination, and date
if __name__ == "__main__":  # using this to make sure that the code only runs when this file is run directly, not when it is imported
    print("Flight Recommendation Tool")

    origin = input("Enter origin airport code (e.g., LAX): ").upper()
    destination = input("Enter destination airport code (e.g., JFK): ").upper()
    date = input("Enter travel date (YYYY-MM-DD): ")

    # automatically find valid hubs based on actual flight paths on this date
    hub_airports = get_possible_hub_airports(origin, destination, date)

    # ask the user for minimum layover minutes (optional, default 45)
    raw = input("Minimum layover (minutes, default 45): ").strip()
    try:
        mlm = int(raw) if raw else 45
        if mlm < 0:
            print("Layover can't be negative; using 45.")
            mlm = 45
    except ValueError:
        print("Invalid number; using 45.")
        mlm = 45

    # get the recommendation with the specified layover minutes
    result = recommend_best_route(origin, destination, date, hub_airports, min_layover_minutes=mlm)

    print("\nBest Flight Option:")
    if isinstance(result, str):
        print(result)
    else:
        print("Type (Synthetic or Direct):", result["type"])
        route_str = " -> ".join([leg[0] for leg in result["route"]] + [result["route"][-1][1]])
        print("Route:", route_str)
        print("Total Price: $", result["price"])
        print("Flights:")
        for flight in result["flights"]:
            print(f"  {flight[0]} {flight[1]} | Dep: {flight[2]} → Arr: {flight[3]} | Price: ${flight[4]} | Miles: {flight[5]}")
        print("Taxes and Fees: $", result["taxes"])
        print("Value per Mile:", result["value_per_mile"], "cents")