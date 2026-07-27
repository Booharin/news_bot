# Деплой на VPS

Без Docker: обычный venv плюс systemd timer. На сервере с Ubuntu/Debian это
проще и прозрачнее контейнера — логи и ручной запуск доступны штатными командами.

## 1. Подготовка сервера

```bash
ssh root@72.56.88.55

apt update
apt install -y python3-venv python3-pip git
```

## 2. Забрать код

Если репозиторий приватный, сначала нужен доступ. Проще всего — deploy key:

```bash
ssh-keygen -t ed25519 -C "news-bot-server" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Полученную строку добавь в GitHub: репозиторий → Settings → Deploy keys →
Add deploy key. Галку «Allow write access» не ставь, серверу писать не нужно.

```bash
git clone git@github.com:Booharin/news_bot.git /opt/news_bot
cd /opt/news_bot
```

## 3. Окружение

```bash
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

## 4. Ключи

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

`.env` живёт только на сервере и в репозиторий не попадает — он в `.gitignore`.

## 5. Проверка

```bash
./venv/bin/python test_offline.py     # 8/8
./venv/bin/python main.py --collect   # живые заголовки из лент
./venv/bin/python main.py --dry-run   # полный дайджест в консоль
./venv/bin/python main.py             # отправка в Telegram
```

Проходи по порядку и не иди дальше, пока предыдущий шаг не отработал.

## 6. Расписание

Часовой пояс сервера — почти наверняка UTC. Выставь свой, иначе дайджест
придёт не в то время:

```bash
timedatectl set-timezone Europe/Moscow
timedatectl        # проверь
```

Создай сервис `/etc/systemd/system/news-bot.service`:

```ini
[Unit]
Description=Morning news digest
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/news_bot
ExecStart=/opt/news_bot/venv/bin/python main.py
```

И таймер `/etc/systemd/system/news-bot.timer`:

```ini
[Unit]
Description=Run morning digest at 08:00

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

`Persistent=true` важен: если сервер лежал в 08:00, дайджест уйдёт сразу
после включения, а не пропадёт.

```bash
systemctl daemon-reload
systemctl enable --now news-bot.timer
systemctl list-timers news-bot.timer   # когда следующий запуск
```

## Эксплуатация

```bash
journalctl -u news-bot.service -n 100      # логи последнего прогона
journalctl -u news-bot.service -f          # следить в реальном времени
systemctl start news-bot.service           # запустить прямо сейчас
```

Обновление после правок в config.py:

```bash
cd /opt/news_bot && git pull && systemctl start news-bot.service
```

## Если что-то не пришло

Смотри `journalctl -u news-bot.service -n 100`. Типичные причины:

- **Пусто в выпуске** — все новости не добрали `MIN_SCORE`. Порог в `config.py`.
- **Telegram 403** — ты не написал боту первым либо неверный `TELEGRAM_CHAT_ID`.
- **Все ленты в предупреждениях** — сервер без интернета или блокирует исходящие.
- **disk I/O error** — база на неподходящей ФС, задай `DIGEST_DB` в `.env`.
