# -*- coding: utf-8 -*-
import http.server
import socketserver
import json
import os
import mimetypes
import sqlite3
import urllib.request
import urllib.error
import hashlib
import uuid
import base64
import sys
import os

# --- Configuration ---
PORT = int(os.environ.get("PORT", 8000))
# Ensure we use the absolute path for the DB to avoid CWD issues
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "mybook.db")
BOOKS_DIR = os.path.join(BASE_DIR, "static", "books")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

# --- Default Books Configuration ---
# These books will be added to ALL users (new and existing)
DEFAULT_BOOKS = [
    ("红楼梦", "曹雪芹", "cc325b26ff584180bf504bcf50a44514.txt"),
    ("生育制度", "费孝通", "f653423cc7d24a929180bccaf790d219.txt"),
    ("长安的荔枝", "马伯庸", "9180b8ab333f44cabd0c98dd5d9c76be.txt"),
    ("基层女性", "王慧玲", "jicengNvxing.txt"),
]

# --- AI System Prompt Configuration ---
# You can edit this prompt directly here.
SYSTEM_PROMPT = """你叫“会意”，是用户的知心阅读书友。你的回复要温暖、有深度、富有同理心。

【核心原则】
1. 如果用户问到他书架里有的书，请结合你对这本书的了解进行深度分析和讨论。
2. 如果用户问到他书架里没有的书，请凭借你丰富的知识储备，详细介绍这本书的内容、作者背景、核心思想，并给出你的阅读感受和推荐理由。不要回避说"我不知道"，而是积极分享你所了解的信息，并且与用户一起讨论内容。
3. 你可以主动推荐相关书籍，帮助用户拓展阅读视野。
4. 回复时兼顾深度和趣味性，像一个真正热爱阅读的好友在聊天。
5. 【重要】绝对禁止使用括号来描写动作、神态或场景（例如不要写“（微笑）”、“（拿起书翻开）”等）。直接输出对话内容即可。


"""

# Ensure directories exist
os.makedirs(BOOKS_DIR, exist_ok=True)

# --- Database Initialization ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id TEXT PRIMARY KEY, username TEXT UNIQUE, password TEXT, 
                  avatar TEXT, signature TEXT, current_book_id TEXT)''')
    
    # Migration: Add current_book_id if missing
    try:
        c.execute("ALTER TABLE users ADD COLUMN current_book_id TEXT")
    except sqlite3.OperationalError:
        pass 
    
    # 2. Books Table 
    c.execute('''CREATE TABLE IF NOT EXISTS books
                 (id TEXT PRIMARY KEY, user_id TEXT, title TEXT, author TEXT, 
                  filepath TEXT, progress INTEGER DEFAULT 0, 
                  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                  
    # Check if we need to seed test users
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        print("Seeding test users...")
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
    
    # --- Ensure Default Books for ALL Users (Migration) ---
    c.execute("SELECT id FROM users")
    all_users = c.fetchall()
    
    for (user_id,) in all_users:
        # For each default book, check if user has it
        for title, author, filename in DEFAULT_BOOKS:
            # Check by title/author/filepath intersection to avoid duplicates
            # Using filename as unique key is safest
            c.execute("SELECT count(*) FROM books WHERE user_id=? AND filepath=?", (user_id, filename))
            if c.fetchone()[0] == 0:
                # print(f"Adding default book '{title}' to user {user_id}") - Commented out to prevent UnicodeEncodeError in logs
                book_id = str(uuid.uuid4())
                c.execute("INSERT INTO books (id, user_id, title, author, filepath) VALUES (?, ?, ?, ?, ?)",
                          (book_id, user_id, title, author, filename))

    conn.commit()
    conn.close()

init_db()

# --- Server Handler ---

ROUTE_MAP = {
    "/": "index.html",
    "/login": "login.html",
    "/chat": "chat.html",
    "/bookshelf": "bookshelf.html",
    "/profile": "profile.html",
    "/reader": "reader.html",
    "/notes": "notes.html",
}

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence logs to keep output clean, or uncomment for debugging
        # sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format%args))
        pass

    def do_GET(self):
        path = self.path.split('?')[0]
        query = ""
        if '?' in self.path:
            query = self.path.split('?')[1]
            
        if path == "/":
            self.send_response(302)
            self.send_header('Location', '/login')
            self.end_headers()
            return

        # API: Get Books
        if path == "/api/books":
            self.handle_get_books(query)
            return
            
        # API: Book Content
        if path == "/api/book_content":
            self.handle_get_book_content(query)
            return
        
        # API: Get Current Book
        if path == "/api/current_book":
            self.handle_get_current_book(query)
            return
        
        # API: Get User Profile
        if path == "/api/user_profile":
            self.handle_get_user_profile(query)
            return

        if path in ROUTE_MAP:
            self.serve_file(ROUTE_MAP[path])
        else:
            # Check if file exists in static (default behavior)
            # Security: Prevent escaping web root
            if ".." in path:
                self.send_error(403)
                return
            super().do_GET()

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            if self.path == '/api/register':
                self.handle_register(data)
            elif self.path == '/api/login':
                self.handle_login(data)
            elif self.path == '/api/chat':
                self.handle_chat(data)
            elif self.path == '/api/upload':
                self.handle_upload(data)
            elif self.path == '/api/update_current_book':
                self.handle_update_current_book(data)
            else:
                self.send_error(404, "API not found")
        except Exception as e:
            self.send_error(500, str(e))

    # --- API Handlers ---

    def handle_register(self, data):
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        signature = data.get('signature', '这个人很懒，什么都没写')
        avatar = data.get('avatar', 'default_avatar_1.svg')
        
        if not username or not password:
            self.send_json_response(400, {"error": "Missing fields"})
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        try:
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            user_id = str(uuid.uuid4())
            c.execute("INSERT INTO users (id, username, password, avatar, signature) VALUES (?, ?, ?, ?, ?)",
                      (user_id, username, pwd_hash, avatar, signature))
            
            # --- Copy Default Books ---
            for title, author, filename in DEFAULT_BOOKS:
                book_id = str(uuid.uuid4())
                c.execute("INSERT INTO books (id, user_id, title, author, filepath) VALUES (?, ?, ?, ?, ?)",
                          (book_id, user_id, title, author, filename))
            # -----------------------------------------------

            conn.commit()
            self.send_json_response(200, {"message": "Success", "user_id": user_id})
        except sqlite3.IntegrityError:
            self.send_json_response(400, {"error": "Username taken"})
        except Exception as e:
            print(f"Register Error: {e}")
            self.send_json_response(500, str(e))
        finally:
            conn.close()

    def handle_login(self, data):
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        c.execute("SELECT id, avatar, signature FROM users WHERE username=? AND password=?", (username, pwd_hash))
        user = c.fetchone()
        conn.close()

        if user:
            # Return more info for caching
            self.send_json_response(200, {
                "message": "Login successful", 
                "user_id": user[0],
                "avatar": user[1],
                "signature": user[2]
            })
        else:
            self.send_json_response(401, {"error": "Invalid credentials"})

    def handle_upload(self, data):
        user_id = data.get('user_id')
        filename = data.get('filename') # Just the name, e.g., "book.txt"
        file_content_base64 = data.get('content') # Base64 encoded string
        author = data.get('author', 'Unknown')
        
        if not user_id or not filename or not file_content_base64:
            self.send_json_response(400, {"error": "Missing data"})
            return

        try:
            # Save file
            safe_filename = f"{uuid.uuid4().hex}_{filename}" # Avoid collisions
            file_path = os.path.join(BOOKS_DIR, safe_filename)
            
            # Decode base64
            # Handle data URL prefix if present (e.g., "data:text/plain;base64,....")
            if ',' in file_content_base64:
                file_content_base64 = file_content_base64.split(',')[1]
                
            file_bytes = base64.b64decode(file_content_base64)
            
            with open(file_path, 'wb') as f:
                f.write(file_bytes)
            
            # DB Insert
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            book_id = str(uuid.uuid4())
            # Simplified title from filename
            title = os.path.splitext(filename)[0]
            
            cursor.execute("INSERT INTO books (id, user_id, title, author, filepath) VALUES (?, ?, ?, ?, ?)",
                           (book_id, user_id, title, author, safe_filename))
            conn.commit()
            conn.close()
            
            self.send_json_response(200, {"message": "Upload successful", "book_id": book_id})
            
        except Exception as e:
            print(f"Upload Error: {e}")
            self.send_json_response(500, {"error": "Upload failed"})

    def handle_get_books(self, query):
        # Parse query for user_id
        # query string: user_id=...
        params = {}
        if query:
            for p in query.split('&'):
                if '=' in p:
                    k, v = p.split('=')
                    params[k] = v
        
        user_id = params.get('user_id')
        if not user_id:
            self.send_json_response(400, {"error": "Missing user_id"})
            return
            
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row # Return dict-like rows
        c = conn.cursor()
        c.execute("SELECT id, title, author, progress FROM books WHERE user_id=? ORDER BY added_at DESC", (user_id,))
        rows = c.fetchall()
        conn.close()
        
        books = [dict(row) for row in rows]
        self.send_json_response(200, {"books": books})

    def handle_get_book_content(self, query):
        params = {}
        if query:
            for p in query.split('&'):
                if '=' in p:
                    k, v = p.split('=')
                    params[k] = v
        
        book_id = params.get('book_id')
        if not book_id:
            self.send_json_response(400, {"error": "Missing book_id"})
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT filepath, title, author FROM books WHERE id=?", (book_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            self.send_json_response(404, {"error": "Book not found"})
            return
            
        filepath, title, author = row
        full_path = os.path.join(BOOKS_DIR, filepath)
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Simple chunking could happen here, but sending full text for now (assuming < 2MB txt)
            self.send_json_response(200, {"title": title, "author": author, "content": content})
        except Exception as e:
            self.send_json_response(500, {"error": "Could not read book file"})

    def handle_get_current_book(self, query):
        params = {}
        if query:
            for p in query.split('&'):
                if '=' in p:
                    k, v = p.split('=')
                    params[k] = v
        
        user_id = params.get('user_id')
        if not user_id:
            self.send_json_response(400, {"error": "Missing user_id"})
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT current_book_id FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        
        if not row or not row[0]:
            # No current book set, return first book or null
            c.execute("SELECT id, title, author FROM books WHERE user_id=? ORDER BY added_at DESC LIMIT 1", (user_id,))
            book_row = c.fetchone()
            conn.close()
            if book_row:
                self.send_json_response(200, {"book_id": book_row[0], "title": book_row[1], "author": book_row[2]})
            else:
                self.send_json_response(200, {"book_id": None})
            return
        
        current_book_id = row[0]
        c.execute("SELECT id, title, author FROM books WHERE id=?", (current_book_id,))
        book_row = c.fetchone()
        conn.close()
        
        if book_row:
            self.send_json_response(200, {"book_id": book_row[0], "title": book_row[1], "author": book_row[2]})
        else:
            self.send_json_response(200, {"book_id": None})

    def handle_update_current_book(self, data):
        user_id = data.get('user_id')
        book_id = data.get('book_id')
        
        if not user_id or not book_id:
            self.send_json_response(400, {"error": "Missing user_id or book_id"})
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        try:
            c.execute("UPDATE users SET current_book_id=? WHERE id=?", (book_id, user_id))
            conn.commit()
            self.send_json_response(200, {"success": True})
        except Exception as e:
            self.send_json_response(500, {"error": str(e)})
        finally:
            conn.close()

    def handle_get_user_profile(self, query):
        params = {}
        if query:
            for p in query.split('&'):
                if '=' in p:
                    k, v = p.split('=')
                    params[k] = v
        
        user_id = params.get('user_id')
        if not user_id:
            self.send_json_response(400, {"error": "Missing user_id"})
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username, avatar, signature FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        
        if row:
            self.send_json_response(200, {
                "username": row[0],
                "avatar": row[1] or "default_avatar_1.svg",
                "signature": row[2] or "懂书也懂你"
            })
        else:
            self.send_json_response(404, {"error": "User not found"})
        conn.close()

    def handle_chat(self, data):
        message = data.get('message', '')
        user_id = data.get('user_id') 
        current_book_content = data.get('book_context', '') # Context from frontend
        
        # Build context-aware prompt using the global configuration
        # Make a copy to avoid appending to the global constant forever
        system_prompt = SYSTEM_PROMPT
        
        # 1. Add User's Library Context
        if user_id:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT title, author FROM books WHERE user_id=? ORDER BY added_at DESC", (user_id,))
            books = c.fetchall()
            conn.close()
            
            if books:
                book_list = ", ".join([f"《{b[0]}》({b[1]})" for b in books])
                system_prompt += f"\n\n你的用户目前藏书有：{book_list}。请在回答中适时关联这些书的内容，分析用户的阅读口味。"

        # 2. Add Current Book Context
        if current_book_content:
            # Truncate context if too long
            context_snippet = current_book_content[:5000] 
            system_prompt += f"\n\n用户正在阅读以下内容（节选）：\n{context_snippet}\n\n请结合这段内容回答用户的问题，如果用户问的是书里的人或事，请根据这段内容进行分析。如果用户在闲聊，也尽量关联到这段内容所体现的主题。"
        else:
             system_prompt += "结合用户提到的书本内容进行回应。"

        ai_response = self.call_qwen(message, system_prompt)
        self.send_json_response(200, {"response": ai_response})

    def call_qwen(self, prompt, system_instruction):
        # Use Qwen via DashScope compatible API
        # Endpoint for Qwen-Turbo (Flash equivalent)
        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DASHSCOPE_API_KEY}'
        }
        
        # User requested "qwen-flash-character" explicitly for free tier.
        payload = {
            "model": "qwen-flash-character", 
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                try:
                    return result['choices'][0]['message']['content']
                except:
                    return "我似乎走神了（API返回结构异常）"
        except urllib.error.HTTPError as e:
            return f"AI服务异常: {e.code} - {e.reason}"
        except Exception as e:
            return f"连接中断: {str(e)}"

    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def serve_file(self, filename):
        if os.path.exists(filename):
            try:
                # Binary mode for images, text mode for html/css/js? 
                # Actually rb is safest for all
                with open(filename, 'rb') as f:
                    content = f.read()
                
                self.send_response(200)
                ctype, _ = mimetypes.guess_type(filename)
                self.send_header('Content-Type', ctype or 'application/octet-stream')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, str(e))
        else:
            self.send_error(404, "File not found")

class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    print(f"Starting server on port {PORT}...")
    with ThreadingTCPServer(("0.0.0.0", PORT), MyHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
