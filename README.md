# Team Holdings Exporter

Программа собирает данные о держателях токена и с помощью простых эвристик оценивает
долю, которая принадлежит команде проекта (разработчики, фонд, мультисиги, вестинг).  
Результат — Excel с вкладками **Meta**, **Summary**, **Wallets**, *(опционально)* **EarlyTransfers** и **Methodology**.

> ⚠️ Это **оценка**, а не юридическое заключение. Для высокой точности добавляйте список известных адресов команды.

---

## Быстрый старт

1) Установите Python 3.10+  
2) Распакуйте архив, перейдите в папку и установите зависимости:
```bash
pip install -r requirements.txt
```
3) Переименуйте `.env.example` в `.env` и впишите API ключи (минимум: **COVALENT_API_KEY** и/или **ETHERSCAN_API_KEY**).  
   Для Ethereum без Covalent можно использовать Ethplorer (ключ `freekey` работает, но с лимитами).

4) Запуск (пример для Ethereum):
```bash
python main.py --chain ethereum --token 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 --provider auto --top 1000 --hours 48 --include-transfers
```
Это создаст файл наподобие `team_holdings_ethereum_0xa0b8_YYYYMMDD_HHMM.xlsx`.

### Опции

- `--chain` — сеть: `ethereum`, `polygon`, `bsc`, `arbitrum`, `optimism`
- `--token` — адрес контракта токена
- `--provider` — `auto` (по умолчанию), `covalent` или `ethplorer`
- `--top` — сколько держателей запрашивать (по лимитам провайдеров)
- `--hours` — окно (в часах) после создания контракта, в котором исходящие переводы считаются «первичным распределением»
- `--team-file` — файл со списком **известных** адресов команды (по одному на строку)
- `--label-map` — CSV с двумя колонками: `address,label` (ваши метки для адресов)
- `--include-transfers` — добавить вкладку EarlyTransfers (аудит первичных распределений)
- `--out` — имя итогового Excel-файла

---

## Где взять API ключи

- **Covalent**: https://www.covalenthq.com/platform/#/auth/register — переменная `COVALENT_API_KEY`
- **Etherscan / Polygonscan / BscScan / Arbiscan / Optimistic Etherscan** — соответствующие переменные из `.env`
- **Ethplorer** (Ethereum): можно начать с `freekey` (лимиты), переменная `ETHPLORER_API_KEY`

> Рекомендуется иметь как минимум Covalent **и** Etherscan-совместимый ключ для вашей сети.

---

## Как это работает

1. Получаем `totalSupply`, `decimals`, `name`, `symbol` токена.
2. Загружаем топ держателей (Covalent — предпочтительно; fallback Ethplorer для Ethereum).
3. Находим **адрес создателя контракта** и **время создания** (Etherscan-совместимый API).
4. В окне `N` часов после создания извлекаем события `Transfer` (Covalent) и помечаем адреса,
   которые получили токены от **создателя** или от **самого контракта** (часто для вестинга/минта).
5. Итоговая «команда» = `известные адреса` ∪ `инферированные по эвристике`.  
   Считаем их суммарный баланс и долю от total supply; формируем Excel.

### Важные ограничения

- Провайдеры не всегда дают **полный** список держателей (обычно топ-1000/10000). Это **выборка**, не полный срез.
- Эвристика упрощена и даёт **оценку**. Для высокоточной атрибуции добавляйте список командных кошельков и метки.
- Не все сети одинаково поддерживаются провайдерами и/или требуют отдельные API ключи.

---

## Файлы

- `main.py` — CLI утилита
- `providers.py` — обращения к API провайдеров
- `heuristics.py` — правила и логика эвристик
- `utils.py` — вспомогательные функции и пресеты сетей
- `requirements.txt` — зависимости
- `.env.example` — шаблон переменных окружения
- `samples/team_wallets_example.txt` — пример файла со списком адресов

---

## Примеры

**1) Только Ethereum, есть Covalent и Etherscan ключи:**
```bash
python main.py --chain ethereum --token 0xdAC17F958D2ee523a2206206994597C13D831ec7 --provider auto --top 2000 --hours 72 --include-transfers
```

**2) Добавить известные адреса команды и свои метки:**
```bash
python main.py --chain polygon --token 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174 \
  --team-file samples/team_wallets_example.txt \
  --label-map my_labels.csv \
  --top 3000 --hours 24
```

---

## Выходной Excel

- **Meta** — общая информация о токене/сети/провайдерах
- **Summary** — агрегаты по категориям (известные / инферированные / все команда / прочие)
- **Wallets** — адреса, метки, флаги принадлежности, баланс и % от total supply
- **EarlyTransfers** *(если включено)* — ранние переводы для аудита
- **Methodology** — параметры расчётов и дисклеймер

---

## Идеи для развития

- Добавить разбор Gnosis Safe (мультисиг) владельцев и timelock/vesting контрактов
- Интеграция с TokenUnlocks / DeFiLlama вендорными метаданными
- Экспорт в CSV/Parquet и Telegram-бот для запуска из чата
