FROM python:3.12-slim

WORKDIR /app

# Зависимости отдельным слоем — пересобираются только при их изменении
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

# База лежит на томе, чтобы история отправленного пережила деплой
ENV DIGEST_DB=/data/digest.db
VOLUME /data

# supercronic вместо системного cron: работает от непривилегированного
# пользователя и пишет логи в stdout, как ждут контейнерные хостинги
ADD https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic

# 08:00 по московскому времени; поменяй TZ под себя
ENV TZ=Europe/Moscow
RUN echo "0 8 * * * cd /app && python main.py" > /app/crontab

CMD ["supercronic", "/app/crontab"]
