import os

# 确保目录存在
os.makedirs('static/avatars', exist_ok=True)

colors = ['#E6B9A6', '#A64D4D', '#5d544b', '#9e9a91', '#2C2C2C']

for i, c in enumerate(colors):
    filename = f'static/avatars/default_avatar_{i+1}.svg'
    content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="50" fill="{c}"/>
  <text x="50" y="65" font-size="40" text-anchor="middle" fill="white" font-family="sans-serif" font-weight="bold">{i+1}</text>
</svg>'''
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Generated {filename}")
