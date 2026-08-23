# Makefile для сайта Moscow QA.
#
# Обёртка над командами, которые описаны в CLAUDE.md, EVENT_GUIDE.md и
# parsers/README.md — сами скрипты по-прежнему можно запускать напрямую.
#
#   make            список целей
#   make serve      собрать сайт и открыть его локально
#
# Переменные окружения передаются сборке как есть, например:
#   TIMEPAD_WIDGET_MODE=popup make build

PYTHON ?= python3
VENV ?= .venv
PORT ?= 8000
DIST := dist

.DEFAULT_GOAL := help

.PHONY: help install install-parsers venv build serve clean check \
	sync sync-dry sync-heisenbug sync-sqadays \
	collect-heisenbug collect-sqadays photo

help: ## Показать этот список
	@awk 'BEGIN {FS = ":.*##"} \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
		/^[a-zA-Z_-]+:.*##/ { printf "  \033[36m%-19s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)
	@echo ""

##@ Сборка сайта

install: ## Установить зависимости сборки
	$(PYTHON) -m pip install -r requirements.txt

build: ## Собрать сайт в dist/
	$(PYTHON) build.py

serve: build ## Собрать и поднять локальный сервер (PORT=8000)
	@echo "→ http://127.0.0.1:$(PORT)/  (Ctrl+C — остановить)"
	@cd $(DIST) && $(PYTHON) -m http.server $(PORT)

clean: ## Удалить dist/ и кэш Python
	rm -rf $(DIST)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

check: ## Проверить синтаксис Python и прогнать сборку
	$(PYTHON) -m compileall -q build.py parsers scripts
	$(PYTHON) build.py
	@test -s $(DIST)/index.html || { echo "dist/index.html не собрался"; exit 1; }
	@test -s $(DIST)/sitemap.xml || { echo "dist/sitemap.xml не собрался"; exit 1; }
	@echo "OK"

##@ Спикеры и конференции

install-parsers: ## Установить зависимости парсеров
	$(PYTHON) -m pip install -r parsers/requirements.txt

venv: ## Создать .venv и поставить в него все зависимости
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt -r parsers/requirements.txt
	@echo "Активировать: source $(VENV)/bin/activate"

sync: sync-heisenbug sync-sqadays ## Подтянуть внешние доклады спикеров (обязательно после добавления нового спикера)

sync-heisenbug: ## Подтянуть доклады с Heisenbug
	$(PYTHON) parsers/sync_heisenbug.py $(ARGS)

sync-sqadays: ## Подтянуть доклады с SQA Days
	$(PYTHON) parsers/sync_sqadays.py $(ARGS)

sync-dry: ## Показать, что изменит sync, ничего не записывая
	$(PYTHON) parsers/sync_heisenbug.py --dry-run
	$(PYTHON) parsers/sync_sqadays.py --dry-run

collect-heisenbug: ## Заново собрать данные с heisenbug.ru (ARGS="--edition '2026 Spring'")
	$(PYTHON) parsers/collect_heisenbug.py $(ARGS)

collect-sqadays: ## Заново собрать данные с sqadays.com (ARGS="--event 144051")
	$(PYTHON) parsers/collect_sqadays.py $(ARGS)

##@ Прочее

photo: ## Сжать фото спикера до ~1080px (FILE=static/images/speakers/name.png)
	@test -n "$(FILE)" || { echo "Укажите файл: make photo FILE=static/images/speakers/name.png"; exit 1; }
	$(PYTHON) scripts/compress_photo.py $(FILE) $(ARGS)
