import asyncio
import json
import sqlite3
import hashlib
import uuid
import urllib.request
import urllib.error
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import RedirectResponse
from pydantic import BaseModel
import uvicorn
import os

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory=".")

# Database Config
DB_FILE = "mybook.db"
GEMINI_API_KEY = "AIzaSyABxytI-RrsGtVydOxhisaobG_gSQDYgcw"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Check if table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not c.fetchone():
        c.execute('''CREATE TABLE users
                     (id TEXT PRIMARY KEY, username TEXT UNIQUE, password TEXT, 
                      avatar TEXT, signature TEXT)''')
        # Add test users
        test_users = [
            ("test_user_1", "123456", "default_avatar_1.svg", "书山有路勤为径"),
            ("book_lover", "123456", "default_avatar_2.svg", "也就是想读点好书"),
            ("poem_soul", "123456", "default_avatar_3.svg", "生活不只是眼前的苟且"),
        ]
        for name, pwd, ava, sig in test_users:
            try:
                pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
                uid = str(uuid.uuid4())
                c.execute("INSERT INTO users (id, username, password, avatar, signature) VALUES (?, ?, ?, ?, ?)",
                          (uid, name, pwd_hash, ava, sig))
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

# Models
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    signature: str = "这个人很懒，什么都没写"
    avatar: str = "default_avatar_1.svg"

class ChatMessage(BaseModel):
    message: str

# Helper Functions
def get_db_connection():
    return sqlite3.connect(DB_FILE)

def blocking_gemini_call(prompt: str) -> str:
    """Synchronous Gemini call to be run in a thread"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    system_instruction = "你叫“会意”，是用户的知心阅读书友。你的回复要温暖、有深度、富有同理心，结合用户提到的书本内容进行回应，而不是机械地回答问题。"
    
    payload = {
        "contents": [{
            "parts": [{"text": system_instruction + "\n\n用户说: " + prompt}]
        }]
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode('utf-8'))
            try:
                return result['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError):
                return "抱歉，我从书海中抬头时走神了，没听清您只要说什么。（API返回格式异常）"
    except urllib.error.HTTPError as e:
        return f"书友会连接中断（API Error: {e.code}）"
    except Exception as e:
        return f"发生了点小意外：{str(e)}"

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/{page}", response_class=HTMLResponse)
async def serve_pages(request: Request, page: str):
    # Generic handler for simple pages
    if page in ["bookshelf", "chat", "profile", "reader", "notes"]:
        return templates.TemplateResponse(f"{page}.html", {"request": request})
    raise HTTPException(status_code=404, detail="Page not found")

# --- API Endpoints ---

@app.post("/api/login")
async def login(data: LoginRequest):
    conn = get_db_connection()
    c = conn.cursor()
    pwd_hash = hashlib.sha256(data.password.encode()).hexdigest()
    c.execute("SELECT id FROM users WHERE username=? AND password=?", (data.username, pwd_hash))
    user = c.fetchone()
    conn.close()
    
    if user:
        return {"message": "登录成功", "user_id": user[0]}
    else:
        return JSONResponse(status_code=401, content={"error": "用户名或密码错误"})

@app.post("/api/register")
async def register(data: RegisterRequest):
    if not data.username or not data.password:
        return JSONResponse(status_code=400, content={"error": "用户名和密码不能为空"})
    
    conn = get_db_connection()
    c = conn.cursor()
    try:
        pwd_hash = hashlib.sha256(data.password.encode()).hexdigest()
        user_id = str(uuid.uuid4())
        c.execute("INSERT INTO users (id, username, password, avatar, signature) VALUES (?, ?, ?, ?, ?)",
                  (user_id, data.username, pwd_hash, data.avatar, data.signature))
        conn.commit()
        return {"message": "注册成功", "user_id": user_id}
    except sqlite3.IntegrityError:
        return JSONResponse(status_code=400, content={"error": "用户名已存在"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        conn.close()

@app.post("/api/chat")
async def chat(data: ChatMessage):
    # Run the blocking API call in a separate thread to ensure non-blocking
    ai_response = await asyncio.to_thread(blocking_gemini_call, data.message)
    return {"response": ai_response}

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 to accessible from network
    print("启动异步服务器 (UVicorn)...")
    print("请访问 http://localhost:8000")
    print("按 Ctrl+C 停止服务")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
