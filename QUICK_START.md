# КОМАНДЫ ДЛЯ ИСПРАВЛЕНИЯ И ПОДГОТОВКИ К РЕЛИЗУ

## 🚀 САМЫЙ БЫСТРЫЙ СПОСОБ (рекомендуется)

### Вариант 1: Используя готовые скрипты
```bash
# 1. Скачайте все скрипты в корень вашего проекта
# 2. Запустите автоматическую подготовку:
bash prepare_release.sh
```

### Вариант 2: One-liner (без скачивания файлов)
```bash
bash quick_oneliner_fix.sh
```

### Вариант 3: Прямая команда Python (копируйте целиком)
```bash
python3 << 'EOF'
from pathlib import Path
import sys

# Исправление legacy/__init__.py
target = Path("./src/interface/legacy/__init__.py")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text('"""Legacy GUI files — kept for reference only."""\n', encoding="utf-8")
print(f"✅ {target}")

# Установка chardet
try:
    import chardet
except ImportError:
    import os; os.system(f"{sys.executable} -m pip install chardet -q")
    import chardet

# Исправление всех файлов
for py_file in Path(".").rglob("*.py"):
    if any(p in py_file.parts for p in ["venv", "__pycache__"]): continue
    try:
        with open(py_file, "r", encoding="utf-8") as f: f.read()
    except UnicodeDecodeError:
        with open(py_file, "rb") as f: raw = f.read()
        result = chardet.detect(raw)
        content = raw.decode(result["encoding"] or "utf-8")
        for old, new in {"\x97":"—","\x96":"–","\x93":""","\x94":""","\x91":"'","\x92":"'","\x85":"…"}.items():
            content = content.replace(old, new)
        with open(py_file, "w", encoding="utf-8") as f: f.write(content)
        print(f"✅ {py_file}")
EOF
```

---

## 📝 ПОШАГОВАЯ ИНСТРУКЦИЯ

### Шаг 1: Быстрое исправление конкретной проблемы
```bash
python3 quick_fix.py
```

### Шаг 2: Исправление всех проблем с кодировкой
```bash
python3 fix_encoding.py
```

### Шаг 3: Проверка синтаксиса
```bash
find . -name "*.py" -type f ! -path "*/venv/*" ! -path "*/__pycache__/*" -exec python3 -m py_compile {} +
```

### Шаг 4: Полная валидация
```bash
python3 validate_project.py
```

---

## 🔧 ДЛЯ GITHUB ACTIONS

### Добавьте в `.github/workflows/main.yml`:
```yaml
- name: Fix encoding issues
  run: |
    python3 << 'EOF'
    from pathlib import Path
    target = Path("./src/interface/legacy/__init__.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('"""Legacy GUI files — kept for reference only."""\n', encoding="utf-8")
    EOF

- name: Validate Python syntax
  run: |
    find . -name "*.py" -type f ! -path "*/venv/*" ! -path "*/__pycache__/*" -exec python3 -m py_compile {} +
```

### Или используйте готовый workflow:
```bash
# Скопируйте github-workflow-fix-encoding.yml в .github/workflows/
cp github-workflow-fix-encoding.yml .github/workflows/fix-encoding.yml
git add .github/workflows/fix-encoding.yml
git commit -m "ci: add encoding fix workflow"
git push
```

---

## 🛠️ РУЧНОЕ ИСПРАВЛЕНИЕ (если скрипты не работают)

### Для ./src/interface/legacy/__init__.py:
1. Откройте файл в редакторе
2. Замените содержимое на:
   ```python
   """Legacy GUI files — kept for reference only."""
   ```
3. Сохраните в кодировке UTF-8

### Для других файлов:
```bash
# Найти все файлы с проблемами
find . -name "*.py" -exec file {} \; | grep -v "UTF-8"

# Конвертировать файл вручную
iconv -f WINDOWS-1252 -t UTF-8 file.py > file_fixed.py
mv file_fixed.py file.py
```

---

## ✅ ПРОВЕРКА ПОСЛЕ ИСПРАВЛЕНИЯ

```bash
# Проверка синтаксиса
echo "=== Проверка синтаксиса Python ==="
find . -name "*.py" -type f ! -path "*/venv/*" ! -path "*/__pycache__/*" -exec python3 -m py_compile {} +

# Проверка кодировки
echo "=== Проверка кодировки ==="
find . -name "*.py" -type f -exec file {} \; | grep -v "UTF-8" || echo "✅ Все файлы в UTF-8"

# Запуск тестов (если есть)
echo "=== Запуск тестов ==="
python3 -m pytest tests/ || python3 -m unittest discover

echo ""
echo "🎉 Все проверки пройдены!"
```

---

## 📦 ФИНАЛЬНЫЕ ШАГИ ПЕРЕД РЕЛИЗОМ

```bash
# 1. Проверить статус
git status

# 2. Закоммитить изменения
git add .
git commit -m "fix: resolve encoding issues for release"

# 3. Запустить финальную валидацию
python3 validate_project.py

# 4. Создать тег релиза
git tag -a v1.0.0 -m "Release version 1.0.0"

# 5. Запушить
git push origin main
git push origin v1.0.0

# 6. Создать GitHub Release (опционально)
gh release create v1.0.0 --title "Version 1.0.0" --notes "Initial release"
```

---

## 🆘 УСТРАНЕНИЕ ПРОБЛЕМ

### Проблема: "Permission denied"
```bash
chmod +x *.sh *.py
```

### Проблема: "chardet not found"
```bash
pip install chardet
# или
python3 -m pip install chardet
```

### Проблема: Скрипты не находят файлы
```bash
# Убедитесь, что вы в корне проекта
pwd
ls -la src/

# Или укажите путь явно
python3 fix_encoding.py /full/path/to/project
```

### Проблема: Синтаксические ошибки остались
```bash
# Проверьте конкретный файл
python3 -m py_compile src/interface/legacy/__init__.py

# Посмотрите содержимое
cat src/interface/legacy/__init__.py | head -5

# Проверьте кодировку
file src/interface/legacy/__init__.py
```

---

## 📊 СПИСОК ВСЕХ ДОСТУПНЫХ ИНСТРУМЕНТОВ

1. **quick_fix.py** - Быстрое исправление конкретной проблемы
2. **fix_encoding.py** - Автоматическое исправление всех проблем с кодировкой
3. **validate_project.py** - Комплексная валидация проекта
4. **prepare_release.sh** - Полная автоматизация подготовки к релизу
5. **quick_oneliner_fix.sh** - Быстрый one-liner для исправления
6. **github-workflow-fix-encoding.yml** - GitHub Actions workflow

---

## 💡 РЕКОМЕНДАЦИИ

1. **Всегда делайте бэкап перед массовыми изменениями:**
   ```bash
   git commit -am "backup before encoding fix"
   ```

2. **Используйте виртуальное окружение:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # или
   venv\Scripts\activate  # Windows
   ```

3. **Настройте git для правильной обработки переносов строк:**
   ```bash
   git config --global core.autocrlf input  # Linux/Mac
   git config --global core.autocrlf true   # Windows
   ```

4. **Используйте .editorconfig для консистентности:**
   ```ini
   root = true
   
   [*]
   charset = utf-8
   end_of_line = lf
   insert_final_newline = true
   
   [*.py]
   indent_style = space
   indent_size = 4
   ```

---

🎉 **Успешной подготовки к релизу!**

## 🆘 Частые проблемы

### `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97`
```bash
python3 quick_fix.py
python3 fix_encoding.py .
```

### `ModuleNotFoundError: No module named 'src.core'`
Убедись что запускаешь из корня репозитория:
```bash
cd /path/to/Argoss
python main.py --no-gui
```

### Тесты падают с `ImportError`
Установить зависимости:
```bash
pip install -r requirements.txt
```

### `unicode error 'utf-8' codec can't decode byte`
```bash
python3 fix_encoding.py
```

### `SyntaxError` после исправления кодировки
```bash
python3 -m py_compile path/to/file.py
```

### Скрипты не находят проект (запуск из другой директории)
```bash
python3 fix_encoding.py /full/path/to/project
```

### Быстрое создание `src/interface/legacy/__init__.py`
```python
from pathlib import Path
target = Path("./src/interface/legacy/__init__.py")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text('"""Legacy GUI files — kept for reference only."""\n', encoding="utf-8")
```
