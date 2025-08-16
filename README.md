# ✈️ Rewards Redemption Optimizer

A Streamlit-based application that helps travelers find the best value airline routes using miles vs cash payments. The tool analyzes flight data to recommend optimal redemption strategies for points and miles collectors.

## 🎯 Target User

Points and miles collectors who want to assess whether a redemption beats paying cash for flights. The tool helps users maximize the value of their rewards by comparing value per mile across different route options.

## 🚀 User Journey

1. **Arrive** at the application
2. **Pick** origin/destination airports and travel dates
3. **Choose** optimization objective ("maximize value" vs "minimum fees")
4. **Set** optional filters (price limits, airline preferences, miles balance)
5. **View** ranked results with value analysis
6. **Explore** interactive charts and optional map visualization
7. **Download** results as CSV for further analysis
8. **Leave** feedback to help improve the tool

## ✨ Features

### Core Functionality
- **Smart Route Search**: Find both direct flights and synthetic routes with layovers
- **Value Optimization**: Calculate value per mile to identify best redemption opportunities
- **Flexible Filtering**: Filter by price, airlines, and miles balance
- **Date Range Search**: Search across multiple dates in August 2025

### Visualizations
- **Comparison Charts**: Bar charts showing top routes by value per mile
- **Price vs Miles Scatter Plot**: Visualize the relationship between cost and miles required
- **Interactive Map**: Optional airport visualization (requires airports.csv)

### User Experience
- **Savings Calculator**: Shows estimated dollar savings for each route
- **Miles Balance Integration**: Filter routes based on your available miles
- **Modern UI**: Stripe-inspired dark theme with clean, accessible design
- **Export Functionality**: Download filtered results as CSV
- **Feedback System**: Submit suggestions and comments

## 📊 Dataset Constraints

### Supported Airports
- **Origins**: LAX, JFK, DXB, DFW, ORD, ATL
- **Destinations**: JFK, LHR, DXB, ORD, ATL, DFW

⚠️ **Important**: For synthetic routing to work consistently, use LAX as the origin. Synthetic routes are most likely to be selected as best value with JFK or LHR destinations.

### Date Limitations
- **Supported Period**: August 2025 only (2025-08-01 to 2025-08-31)
- **August 31**: Direct flights only (no layover data available)
- **LHR Destinations**: Best results between August 2-26

### Missing Routes
The following route combinations do not exist in the database:
- DXB → LHR
- LHR → JFK

## 🎨 Accessibility & UX Design

### Design Principles
- **Sensible Defaults**: LAX→JFK with upcoming dates pre-selected
- **Large Interactive Elements**: Easy-to-use inputs and buttons
- **High Contrast**: Dark theme optimized for readability
- **Clear Labels**: Plain English terminology (e.g., "Value per Mile (¢)")
- **Helpful Guidance**: Tooltips and help text throughout

### Error Handling
- **Plain English Messages**: Clear, actionable error descriptions
- **Graceful Degradation**: Informative empty states when no results found
- **Input Validation**: Real-time feedback on invalid selections

### Always-Visible Information
- **Dataset Tips Card**: Key constraints and recommendations prominently displayed
- **Validation Messages**: Real-time feedback on input constraints

## 🧪 User Testing Checklist

### Basic Functionality Tests
1. **Find Best Value Route**: Search LAX→JFK for next week, maximize VPM, export CSV
2. **Miles Balance Filtering**: Set balance to 25,000 miles, filter to routes within balance, identify top option
3. **Objective Comparison**: Switch from "maximize value" to "minimum fees", observe changes

### Advanced Features
4. **Date Range Search**: Test multiple dates across August 2025
5. **Synthetic Routes**: Compare direct vs. layover options
6. **Chart Interaction**: Verify bar chart and scatter plot functionality
7. **Feedback Submission**: Submit test feedback and verify CSV creation

### Edge Cases
8. **Invalid Routes**: Attempt DXB→LHR (should be blocked)
9. **Date Constraints**: Try dates outside August 2025
10. **Empty Results**: Search with very restrictive filters

## 🚀 How to Run

### Installation
```bash
pip install -r requirements.txt
