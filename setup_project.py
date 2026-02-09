import os
import shutil

# 定义目标目录
BASE_DIR = os.getcwd()
DIRS_TO_CREATE = [
    os.path.join(BASE_DIR, "static", "css"),
    os.path.join(BASE_DIR, "static", "js"),
    os.path.join(BASE_DIR, "static", "images"),
    os.path.join(BASE_DIR, "templates"),
]

# 定义文件移动映射 (源路径 -> 目标文件名)
FILE_MOVES = {
    "index.html": "index.html",
    os.path.join("书架首页_1", "code.html"): "bookshelf.html",
    os.path.join("书架首页_2", "code.html"): "bookshelf_v2.html",
    os.path.join("个人中心与书友会", "code.html"): "profile.html",
    os.path.join("ai_读书对话", "code.html"): "chat.html",
    os.path.join("阅读器界面", "code.html"): "reader.html",
    os.path.join("阅读笔记与心法", "code.html"): "notes.html",
}

def setup_project():
    print(f"Working directory: {BASE_DIR}")
    
    # 1. 创建目录
    for directory in DIRS_TO_CREATE:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"Created/Verified directory: {directory}")
        except Exception as e:
            print(f"Error creating directory {directory}: {e}")

    # 2. 移动文件
    for src_rel, dest_name in FILE_MOVES.items():
        src_path = os.path.join(BASE_DIR, src_rel)
        dest_path = os.path.join(BASE_DIR, "templates", dest_name)
        
        if os.path.exists(src_path):
            try:
                # 如果目标存在，先删除
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                
                shutil.move(src_path, dest_path)
                print(f"Moved: {src_rel} -> templates/{dest_name}")
            except Exception as e:
                print(f"Error moving {src_rel}: {e}")
        else:
            print(f"Source file not found (skipped): {src_rel}")

if __name__ == "__main__":
    setup_project()
