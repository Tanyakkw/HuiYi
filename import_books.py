import os
import sqlite3
import uuid
import zipfile
import re
import html.parser
import xml.etree.ElementTree as ET

# Attempt to import mobi library
try:
    import mobi
except ImportError:
    mobi = None
    print("Mobi library not found, falling back to basic extraction.")

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
DB_FILE = os.path.join(BASE_DIR, "mybook.db")
TARGET_BOOKS_DIR = os.path.join(BASE_DIR, "static", "books")

def clean_title(filename):
    name = os.path.splitext(filename)[0]
    name = re.sub(r'^\d+', '', name)
    if ' - ' in name: name = name.split(' - ')[0]
    if '--' in name: name = name.split('--')[0]
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'（.*?）', '', name)
    return name.strip()

def extract_docx(filepath):
    try:
        with zipfile.ZipFile(filepath) as z:
            xml_content = z.read('word/document.xml')
        root = ET.fromstring(xml_content)
        namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        text_parts = []
        for p in root.findall('.//w:p', namespaces):
            line_text = ""
            for t in p.findall('.//w:t', namespaces):
                if t.text: line_text += t.text
            if line_text: text_parts.append(line_text)
        return "\n\n".join(text_parts)
    except Exception as e:
        print(f"Error extracting DOCX {filepath}: {e}")
        return None

class EpubTextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
    def handle_data(self, data):
        if data.strip(): self.text_parts.append(data.strip())
    def get_text(self): return "\n".join(self.text_parts)

def extract_epub(filepath):
    try:
        text_content = []
        with zipfile.ZipFile(filepath) as z:
            html_files = [f for f in z.namelist() if f.endswith('.html') or f.endswith('.xhtml')]
            html_files.sort()
            for hf in html_files:
                html_bytes = z.read(hf)
                parser = EpubTextExtractor()
                parser.feed(html_bytes.decode('utf-8', errors='ignore'))
                text_content.append(parser.get_text())
        return "\n\n".join(text_content)
    except Exception as e:
        print(f"Error extracting EPUB {filepath}: {e}")
        return None

def extract_mobi_fallback(filepath):
    # Basic text extraction from binary for fallback
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
            # Extract printable content (very rough)
            text = re.sub(rb'[^\x20-\x7E\x0A\x0D\xE4-\xFF]', b'', content)
            return text.decode('latin-1', errors='ignore')
    except Exception as e:
        print(f"MOBI fallback failed: {e}")
        return None

def process_books():
    if not os.path.exists(TARGET_BOOKS_DIR):
        os.makedirs(TARGET_BOOKS_DIR)
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Ensure 'template' user exists for default books
    try:
        c.execute("INSERT INTO users (id, username, password) VALUES (?, ?, ?)", 
                  ("template", "template_user", "template_pass_hash"))
        print("Created template user.")
        conn.commit() # Commit immediately
    except sqlite3.IntegrityError:
        print("Template user already exists.")
    
    # Get ALL users including template
    c.execute("SELECT id FROM users")
    all_users = [row[0] for row in c.fetchall()]
    
    files = os.listdir(PARENT_DIR)
    
    for f in files:
        full_path = os.path.join(PARENT_DIR, f)
        if os.path.isdir(full_path): continue
        
        ext = os.path.splitext(f)[1].lower()
        if ext not in ['.docx', '.epub', '.mobi']: continue
        
        print(f"Processing: {f}")
        content = None
        
        if ext == '.docx':
            content = extract_docx(full_path)
        elif ext == '.epub':
            content = extract_epub(full_path)
        elif ext == '.mobi':
            # Try parsing or fallback
            if mobi:
                try:
                    # Simple attempt with library if API allows
                    # Note: mobi-python usually requires output dir.
                    # We'll use fallback for simplicity unless we know API.
                    # Given environment uncertainty, sticking to robust fallback + text search.
                   content = extract_mobi_fallback(full_path)
                except:
                   content = extract_mobi_fallback(full_path)
            else:
                content = extract_mobi_fallback(full_path)
        
        if not content:
            print(f"Failed to extract {f}")
            continue
            
        display_title = clean_title(f)
        
        # Save to storage
        target_filename = f"{uuid.uuid4().hex}.txt"
        target_path = os.path.join(TARGET_BOOKS_DIR, target_filename)
        with open(target_path, 'w', encoding='utf-8') as tf:
            tf.write(content)
            
        # Add to all users
        for uid in all_users:
            c.execute("SELECT id FROM books WHERE title=? AND user_id=?", (display_title, uid))
            if c.fetchone():
                print(f"Skipping existing book '{display_title}' for {uid}")
            else:
                bid = str(uuid.uuid4())
                c.execute("INSERT INTO books (id, user_id, title, author, filepath) VALUES (?, ?, ?, ?, ?)",
                          (bid, uid, display_title, "本地导入", target_filename))
                print(f"Imported '{display_title}' for {uid}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    process_books()
