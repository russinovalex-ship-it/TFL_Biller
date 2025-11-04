
# Создаём файл requirements.txt
requirements = """python-telegram-bot==20.7
pandas==2.2.0
openpyxl==3.1.2
"""

with open('requirements.txt', 'w', encoding='utf-8') as f:
    f.write(requirements)

print("✅ Файл requirements.txt создан успешно!")
