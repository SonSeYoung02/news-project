# 리버스 프록시·정적 파일 서버. 공식 multi-arch 이미지라 라즈베리파이(ARM64)에서도 그대로 빌드된다.
# 화면 파일은 compose의 additional_contexts(frontend-dist: service:frontend)로 받은
# 프론트 빌드 이미지에서 복사하므로, 다시 빌드할 때마다 이전 산출물이 남지 않는다.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-dist /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
