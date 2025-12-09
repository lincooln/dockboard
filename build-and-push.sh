#!/bin/bash
# Скрипт для сборки и публикации образа

set -e  # Выход при ошибке

IMAGE_NAME="lincoolns/dockerboard"
VERSION="1.0.0"

echo "🔨 Сборка Docker образа..."
docker build -t ${IMAGE_NAME}:${VERSION} -t ${IMAGE_NAME}:latest .

echo "🔒 Логин в Docker Hub..."
docker login

echo "🚀 Публикация образа..."
docker push ${IMAGE_NAME}:${VERSION}
docker push ${IMAGE_NAME}:latest

echo "✅ Образ опубликован!"
echo "📦 Пользователи могут использовать:"
echo "   docker run -d -p 5000:5000 \\"
echo "     -v /var/run/docker.sock:/var/run/docker.sock:ro \\"
echo "     -v dashboard_data:/app/data \\"
echo "     ${IMAGE_NAME}:latest"
