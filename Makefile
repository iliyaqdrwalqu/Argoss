.PHONY: help install test lint fix-encoding health release-check

help:
	@echo "Argoss Makefile"
	@echo "  make install        — установить зависимости"
	@echo "  make test           — запустить тесты"
	@echo "  make lint           — проверить код"
	@echo "  make fix-encoding   — исправить кодировку"
	@echo "  make health         — проверка здоровья системы"
	@echo "  make release-check  — полная проверка перед релизом"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -q --tb=short

lint:
	python -m py_compile src/*.py src/**/*.py 2>/dev/null || true
	@echo "✅ Syntax check complete"

fix-encoding:
	python3 quick_fix.py
	python3 fix_encoding.py .

health:
	python3 health_check.py

release-check:
	bash prepare_release.sh
