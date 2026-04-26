# Effective Mobile DevOps Test

Тестовое задание на позицию DevOps.

Проект разворачивает минимальное веб-приложение из двух Docker-контейнеров:

- **backend** - простой HTTP-сервер на Python, слушающий порт `8080`
- **nginx** - reverse proxy, принимающий HTTP-запросы на порт `80` и проксирующий их в backend

## Структура проекта

```text
.
├── backend/
│   ├── app.py
│   └── Dockerfile
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Используемые технологии

- Docker
- Docker Compose
- Python 3
- Nginx

## Запуск проекта

Убедитесь, что на системе установлены:

- Docker
- Docker Compose

Запуск:

```bash
docker compose up --build -d
```

Проверка, что контейнеры запущены:

```bash
docker compose ps
```

## Проверка результата

После запуска выполните:

```bash
curl http://localhost
```

Ожидаемый ответ:

```text
Hello from Effective Mobile!
```

## Как работает схема

Схема взаимодействия:

```text
Client -> nginx:80 -> backend:8080
```

Описание:

1. Пользователь отправляет HTTP-запрос на `localhost:80`
2. Контейнер `nginx` принимает запрос
3. `nginx` проксирует его во внутреннюю Docker-сеть на сервис `backend`
4. `backend` возвращает ответ:

```text
Hello from Effective Mobile!
```

## Особенности реализации

- backend запускается в отдельном контейнере
- backend не публикует порт наружу
- наружу проброшен только порт `80` у `nginx`
- `nginx` использует отдельный конфигурационный файл
- сервисы взаимодействуют по имени сервиса внутри Docker Compose
- для backend добавлен `HEALTHCHECK`
- backend запускается не от root
- структура проекта простая и понятная

## Полезные команды

Остановить проект:

```bash
docker compose down
```

Остановить проект с удалением сети:

```bash
docker compose down -v
```

Пересобрать и перезапустить:

```bash
docker compose up --build -d
```

Посмотреть логи:

```bash
docker compose logs -f
```

## Примечания

- backend доступен только внутри Docker-сети
- прямой доступ к backend с хоста отсутствует
- все внешние HTTP-запросы проходят только через nginx

## Автор

Тестовое задание выполнено для Effective Mobile.
