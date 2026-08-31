from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
import json
import hashlib
import re
from groq import Groq
import os
from dotenv import load_dotenv
import models
import auth
from database import engine, get_db

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

models.Base.metadata.create_all(bind=engine)

cache = {}
CACHE_TTL_DAYS = 7

def get_cache_key(city: str, days: int, budget: int) -> str:
    key = f"{city.lower()}_{days}_{budget}"
    return hashlib.md5(key.encode()).hexdigest()

def get_from_cache(key: str):
    if key in cache:
        entry = cache[key]
        if datetime.now() - entry["created_at"] < timedelta(days=CACHE_TTL_DAYS):
            return entry["data"]
        else:
            del cache[key]
    return None

def save_to_cache(key: str, data: dict):
    cache[key] = {"data": data, "created_at": datetime.now()}

app = FastAPI(title="AI Travel Planner")

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class PlanRequest(BaseModel):
    city: str
    days: int
    budget: int

@app.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    user = models.User(
        username=data.username,
        email=data.email,
        hashed_password=auth.hash_password(data.password)
    )
    db.add(user)
    db.commit()
    return {"message": "Аккаунт создан!"}

@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == data.username).first()
    if not user or not auth.verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = auth.create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/plan")
def create_plan(data: PlanRequest, authorization: str = Header(...), db: Session = Depends(get_db)):
    token = authorization.replace("Bearer ", "")
    user = auth.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if data.days < 1 or data.days > 30:
        raise HTTPException(status_code=400, detail="Количество дней должно быть от 1 до 30")
    if data.budget <= 0:
        raise HTTPException(status_code=400, detail="Бюджет должен быть положительным")

    cache_key = get_cache_key(data.city, data.days, data.budget)
    cached = get_from_cache(cache_key)
    if cached:
        return {"id": None, "city": data.city, "plan": cached, "cached": True}

    prompt = f"""Ты API который возвращает ТОЛЬКО JSON. Никакого текста, никаких ```json блоков. Только чистый JSON.

Составь маршрут на {data.days} дней в городе {data.city} с бюджетом ${data.budget}.

Верни ТОЛЬКО этот JSON:
{{
  "city": "{data.city}",
  "days": [
    {{
      "day": 1,
      "title": "Название дня",
      "activities": [
        {{
          "time": "10:00",
          "title": "Название места",
          "description": "Краткое описание",
          "price": "$10-15",
          "type": "attraction"
        }}
      ],
      "total_cost": "$50-70"
    }}
  ],
  "total_budget": "$150-200",
  "tips": "Советы путешественнику"
}}

Типы: attraction, food, transport, hotel. Язык: русский. ТОЛЬКО JSON."""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    plan_text = response.choices[0].message.content

    plan = models.TravelPlan(
        city=data.city,
        days=data.days,
        budget=data.budget,
        plan_text=plan_text,
        user_id=user.id
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    try:
        clean = plan_text.strip()
        clean = re.sub(r'```json\s*', '', clean)
        clean = re.sub(r'```\s*', '', clean)
        clean = clean.strip()
        plan_json = json.loads(clean)
        save_to_cache(cache_key, plan_json)
    except:
        plan_json = {"raw": plan_text}
    return {"id": plan.id, "city": plan.city, "plan": plan_json}

@app.get("/history")
def get_history(authorization: str = Header(...), db: Session = Depends(get_db)):
    token = authorization.replace("Bearer ", "")
    user = auth.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    plans = db.query(models.TravelPlan).filter(models.TravelPlan.user_id == user.id).all()
    return [{"id": p.id, "city": p.city, "days": p.days, "budget": p.budget, "created_at": p.created_at} for p in plans]

@app.get("/plan/{plan_id}")
def get_plan(plan_id: int, authorization: str = Header(...), db: Session = Depends(get_db)):
    token = authorization.replace("Bearer ", "")
    user = auth.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    plan = db.query(models.TravelPlan).filter(models.TravelPlan.id == plan_id, models.TravelPlan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    try:
        clean = plan.plan_text.strip()
        clean = re.sub(r'```json\s*', '', clean)
        clean = re.sub(r'```\s*', '', clean)
        plan_json = json.loads(clean.strip())
    except:
        plan_json = {"raw": plan.plan_text}
    return {"id": plan.id, "city": plan.city, "days": plan.days, "budget": plan.budget, "plan": plan_json}

@app.post("/favorite/{plan_id}")
def add_favorite(plan_id: int, authorization: str = Header(...), db: Session = Depends(get_db)):
    token = authorization.replace("Bearer ", "")
    user = auth.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    existing = db.query(models.Favorite).filter(
        models.Favorite.user_id == user.id,
        models.Favorite.plan_id == plan_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Уже в избранном")
    favorite = models.Favorite(user_id=user.id, plan_id=plan_id)
    db.add(favorite)
    db.commit()
    return {"message": "Добавлено в избранное!"}

@app.delete("/favorite/{plan_id}")
def remove_favorite(plan_id: int, authorization: str = Header(...), db: Session = Depends(get_db)):
    token = authorization.replace("Bearer ", "")
    user = auth.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    favorite = db.query(models.Favorite).filter(
        models.Favorite.user_id == user.id,
        models.Favorite.plan_id == plan_id
    ).first()
    if not favorite:
        raise HTTPException(status_code=404, detail="Не найдено в избранном")
    db.delete(favorite)
    db.commit()
    return {"message": "Удалено из избранного"}

@app.get("/favorites")
def get_favorites(authorization: str = Header(...), db: Session = Depends(get_db)):
    token = authorization.replace("Bearer ", "")
    user = auth.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    favorites = db.query(models.Favorite).filter(models.Favorite.user_id == user.id).all()
    result = []
    for f in favorites:
        plan = db.query(models.TravelPlan).filter(models.TravelPlan.id == f.plan_id).first()
        if plan:
            result.append({"id": plan.id, "city": plan.city, "days": plan.days, "budget": plan.budget})
    return result

@app.delete("/plan/{plan_id}")
def delete_plan(plan_id: int, authorization: str = Header(...), db: Session = Depends(get_db)):
    token = authorization.replace("Bearer ", "")
    user = auth.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    plan = db.query(models.TravelPlan).filter(models.TravelPlan.id == plan_id, models.TravelPlan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    db.delete(plan)
    db.commit()
    return {"message": "Маршрут удалён"}

@app.get("/", response_class=HTMLResponse)
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    # запрещаем браузеру кэшировать страницу, чтобы всегда грузилась свежая версия
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    return HTMLResponse(content=html, headers=headers)