# Frontend Take-Home Assignment

Welcome to the Flight Search Frontend Take-Home Assignment!

In this exercise, you'll implement the UI for a simple **Flight Search Application** with three key screens:

1. **Flight Search** – A form where users can enter origin, destination, and dates.
2. **Flight List** – A screen displaying a list of matching flights based on the search.
3. **Flight Details** – A detailed view of a selected flight.

The goal of this assignment is to assess your ability to:
- Design a clean, functional user interface.
- Make reasonable assumptions about API design.
- Implement data flow and state management without an existing backend.
- Write clear, maintainable code.

---

## 🧭 Scenario

In this assignment, you’ll simulate a **frontend-first development scenario** — where the backend is not yet ready.  
You’ll need to **define the data models and mock APIs** that your frontend would use.

You can implement your mock APIs however you like:
- A simple JSON file.
- Local data with delays to simulate API latency.
- A lightweight mock server using tools like `msw`, `json-server`, or `miragejs`.

Be ready to explain your assumptions about:
- API endpoints.
- Request and response formats.
- Data modeling decisions.

---

## 🕐 Time Consideration

We value your time!  
If this assignment takes you more than **8 hours**, please submit whatever you have by that point.

Focus on **clarity, UX quality, and code structure**.  
While it doesn’t need to be 100% production-ready, it should be demo-quality and easy to navigate.

Include a short README in your submission describing:
- How to run your project.
- What you would improve or do differently with more time.

---

## ⚙️ Getting Started

1. **Fork this repository** so that you have your own version to work with.
2. **Create your frontend project** under the `client/` directory.
3. You may use **any frontend framework** you like — React, Vue, Svelte, etc.
4. Implement your mock backend data using whichever method feels natural for your stack.

---

## 🎨 Design Reference

You’ll receive a **Figma file** with design guidelines for:
- Flight Search
- Flight List
- Flight Details

If you haven’t received access, please reach out to us.

While the Figma file provides the overall look and feel, you’ll need to design **loading, empty, and error states** yourself.  
Focus on **consistency and polish** — small UI touches matter.

---

## 🧩 Tasks Overview

Please complete the following tasks in order.  
If you can’t complete all of them, focus on **quality over quantity**.

### 1. Flight Search Screen
- Create a form that allows the user to input:
  - Origin airport
  - Destination airport
  - Departure date
  - Return date (optional)
- Add a “Search Flights” button that triggers a request to your mock API.
- Validate input fields (e.g., required fields, invalid dates).

### 2. Flight List Screen
- Display the list of available flights based on the search parameters.
- Each flight should show key information:
  - Airline name
  - Flight number
  - Departure and arrival airports
  - Departure and arrival times
  - Price
- Include a **loading state**, **empty state**, and **error state**.
- Clicking a flight should navigate to the **Flight Details** screen.

### 3. Flight Details Screen
- Display detailed flight information, such as:
  - Aircraft type
  - Duration
  - Fare breakdown
  - Baggage allowance
  - Cancellation policy
- Include a “Back to Results” link or button.

### [Bonus]
- Add sorting and filtering (e.g., by price or duration).
- Implement pagination or infinite scrolling for flight results.
- Include unit tests for core logic.
- Add smooth transitions between screens.
