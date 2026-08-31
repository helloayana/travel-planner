# AI Travel Planner

A web app that generates a personalized travel itinerary from budget, destination, and trip length — with user accounts to save and revisit routes.

## Features

- User authentication (registration/login)
- Generate a day-by-day itinerary based on **budget, country, and number of days**
- Save generated routes to a personal dashboard
- Mark routes as favorites
- User profile with route/favorites/cities stats

## Live Demo

🔗 [travel-planner-yl9n.onrender.com](https://travel-planner-yl9n.onrender.com/)

## How it works

1. User registers/logs in and submits budget, country, and trip duration
2. `main.py` builds a prompt from these inputs and sends it to the **Google Gemini API**
3. The LLM response is parsed into a structured itinerary
4. The route is saved to the database (`database.py`, `models.py`) and linked to the user's account, so it can be revisited or favorited later

## Tech Stack

**Backend:** Python, FastAPI
**Auth:** `auth.py` — user registration/login
**Database:** SQLite (`models.py`, `database.py`)
**LLM:** Google Gemini API
**Frontend:** HTML/CSS/JS (`static/`)
**Deployment:** Render (`Procfile`)

## Running locally

```bash
git clone https://github.com/helloayana/travel-planner.git
cd travel-planner
pip install -r requirements.txt
```

Create a `.env` file with your own credentials (Gemini API key, session secret, etc. — see `auth.py`/`main.py` for required variables).

Run the server:
```bash
uvicorn main:app --reload
```

## What I'd improve with more time

- Add trip preferences/interests as an input for more personalized itineraries
- Handle and validate malformed or unexpected LLM output more gracefully
- Add caching for repeated identical requests to reduce API costs
- Move from SQLite to a production-grade database for multi-user scale

## Author

Ayana — [github.com/helloayana](https://github.com/helloayana)

