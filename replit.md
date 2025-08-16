# Overview

The Rewards Redemption Optimizer is a Streamlit-based web application that helps frequent travelers and points collectors determine the optimal strategy for booking flights - whether to use airline miles or pay cash. The tool analyzes flight data from a SQLite database to calculate value per mile metrics and recommends the most cost-effective booking approach. It supports both direct flights and synthetic routes with layovers, providing comprehensive route optimization across major airports.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Frontend Architecture
- **Framework**: Streamlit web application with custom CSS styling
- **Design System**: Modern, Stripe-inspired dark theme with Hustura/Framer aesthetic
- **Styling**: CSS variables for theming with light/dark mode support
- **Layout**: Wide container layout with card-based components and hero sections
- **Visualization**: Integration with Pydeck for optional interactive airport maps

## Backend Architecture
- **Data Layer**: SQLite database (`travel_data_with_miles.db`) containing flight information
- **Business Logic**: Recommendation engine (`recommendation_tool.py`) for route optimization
- **Core Algorithm**: Value-per-mile calculation comparing cash prices vs. miles redemption
- **Route Types**: Support for both direct flights and synthetic routes with layovers
- **Optimization Strategies**: Multiple objectives including maximum value and minimum fees

## Data Storage
- **Database**: SQLite with flights table containing airline, route, pricing, and miles data
- **Schema**: Flight records with origin/destination airports, dates, prices, and miles requirements
- **Data Constraints**: Limited to specific airports (LAX, JFK, DXB, DFW, ORD, ATL) and August 2025 timeframe
- **Export**: CSV download functionality for filtered results

## Core Features
- **Route Search**: Direct flight lookup and synthetic route generation with layover analysis
- **Value Optimization**: Calculate and rank routes by value per mile metrics
- **Filtering System**: Price limits, airline preferences, and miles balance constraints
- **Savings Calculator**: Dollar savings estimation for each route option
- **Interactive Visualizations**: Bar charts, scatter plots, and optional map displays

# External Dependencies

## Python Packages
- **streamlit**: Web application framework for the user interface
- **pandas**: Data manipulation and analysis for flight data processing
- **numpy**: Mathematical operations for calculations and data handling
- **pydeck**: Deck.gl integration for interactive map visualizations

## Database
- **SQLite**: Local database file for flight data storage and querying
- **Schema**: Flights table with columns for airline, flight_number, departure_time, arrival_time, price, miles, route_origin, route_destination, and date

## Configuration
- **Streamlit Config**: Custom theme configuration with Stripe-inspired color palette
- **CSS Framework**: Custom styling system with CSS variables for consistent theming
- **Color Scheme**: Primary colors include Stripe indigo (#635bff) and purple accent (#7c3aed)