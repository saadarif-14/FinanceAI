from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine
import models
from routers import auth, transactions, chat, budgets, analytics

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Personal Finance Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(chat.router)
app.include_router(budgets.router)
app.include_router(analytics.router)


@app.get("/health")
def health():
    return {"status": "ok"}
