# smart-home-iot

## 1) Preduslovi (Windows)
- Docker Desktop instaliran i pokrenut.
- Python 3.11+

## 2) Podešavanje tokena i podešavanja
### 2.1. InfluxDB token
U fajlu [docker-compose.yml](docker-compose.yml) promeniti vrednost:

```
DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: TOKEN
```

### 2.2. settings.json
U fajlu [simulation/settings.json](simulation/settings.json) postaviti:

```
"influx": {
	"url": "http://localhost:8086",
	"token": "ISTI_TAJ_TOKEN",
	"org": "smart-home",
	"bucket": "iot"
}
```

## 3) Pokretanje servisa (Docker)
Iz korena projekta pokrenuti:

```
docker compose up -d
```

Time se podižu:
- Mosquitto MQTT broker (localhost:1883)
- InfluxDB (http://localhost:8086)
- Grafana (http://localhost:3000)

## 4) Prva prijava u InfluxDB
1. Otvoriti http://localhost:8086
2. Ulogovati se:
	 - username: `admin`
	 - password: `admin123`
3. Proveriti da li postoji bucket `iot` i org `smart-home`.

## 5) Pokretanje MQTT → Influx servera
U novom terminalu pokrenuti:

```
python simulation/collector/mqtt_influx_server.py
```

Vidi se:
```
[SERVER] MQTT connected
```

## 6) Pokretanje PI1 kontrolera
U drugom terminalu pokrenuti:

```
python simulation/main.py
```

## 6.1) Pokretanje PI2 kontrolera
U istom `main.py` meniju izabrati `2 - PI2 - Kitchen Controller`.

## 6.2) Web aplikacija (ALARM + timer)
U novom terminalu pokrenuti:

```
python simulation/webapp/app.py
```

Web UI je na: `http://localhost:5000`

Funkcije:
- Deaktivacija alarma
- Setovanje vremena tajmera
- Setovanje BTN increment vrednosti
- Real-time status (alarm, timer, display)

## 7) Provera podataka u InfluxDB (Data Explorer)
U Influx UI (Data Explorer) nalepiti Flux upit:

```
from(bucket: "iot")
	|> range(start: -1h)
	|> filter(fn: (r) => r._measurement == "iot")
```

## 8) Grafana podešavanje
1. Otvoriti http://localhost:3000
2. Login:
	 - user: `admin`
	 - pass: `admin123`

PI2 dashboard (import JSON): `grafana/smart-home-pi2-dashboard.json`
