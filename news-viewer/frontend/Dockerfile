# 프론트엔드는 화면 빌드까지만 담당한다(Vite 8은 Node 20.19+ 또는 22 필요).
# 정적 파일 제공과 /api 프록시는 루트 nginx/ 이미지가 맡으며, nginx 빌드 시 이 이미지의 /app/dist를 복사한다.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY . .
RUN npm run build

# 빌드 산출물만 담은 최종 이미지. 실행할 프로세스가 없으므로 컨테이너로 띄우지 않는다.
FROM scratch
COPY --from=build /app/dist /app/dist
