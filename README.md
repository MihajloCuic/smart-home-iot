# smart-home-iot

Ovaj projekat pokriva KT2 zahteve: MQTT batch slanje, InfluxDB skladištenje i Grafana vizualizaciju.

## 1) Preduslovi (Windows)
- Docker Desktop instaliran i pokrenut.
- Python 3.11+ (projekat već ima `.venv`).

## 2) Podešavanje tokena i podešavanja
### 2.1. InfluxDB token
U fajlu [docker-compose.yml](docker-compose.yml) promeni vrednost:

```
DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: TVOJ_JAK_TOKEN
```

To može biti bilo koji dugačak string (npr. 32+ karaktera). Taj isti token mora da stoji i u settings.

### 2.2. settings.json
U fajlu [simulation/settings.json](simulation/settings.json) postavi:

```
"influx": {
	"url": "http://localhost:8086",
	"token": "ISTI_TAJ_TOKEN",
	"org": "smart-home",
	"bucket": "iot"
}
```

Ako menjaš org/bucket u docker-compose, obavezno isto promeni i ovde.

## 3) Pokretanje servisa (Docker)
Iz korena projekta pokreni:

```
docker compose up -d
```

Time se podižu:
- Mosquitto MQTT broker (localhost:1883)
- InfluxDB (http://localhost:8086)
- Grafana (http://localhost:3000)

## 4) Prva prijava u InfluxDB
1. Otvori http://localhost:8086
2. Uloguj se:
	 - username: `admin`
	 - password: `admin123`
3. Proveri da postoji bucket `iot` i org `smart-home`.

## 5) Pokretanje MQTT → Influx servera
U novom terminalu pokreni:

```
python simulation/collector/mqtt_influx_server.py
```

Treba da vidiš:
```
[SERVER] MQTT connected
```

## 6) Pokretanje PI1 kontrolera
U drugom terminalu pokreni:

```
python simulation/main.py
```

Probaj komande:
- `7` / `8` (door open/close)
- `1` (toggle light)
- `9` (motion)

## 7) Provera podataka u InfluxDB (Data Explorer)
U Influx UI (Data Explorer) nalepi Flux upit:

```
from(bucket: "iot")
	|> range(start: -1h)
	|> filter(fn: (r) => r._measurement == "iot")
```

Ako vidiš podatke – sve radi.

## 8) Grafana podešavanje
1. Otvori http://localhost:3000
2. Login:
	 - user: `admin`
	 - pass: `admin123`
3. Dodaj Data Source:
	 - Type: InfluxDB
	 - Query Language: Flux
	 - URL:
		 - Ako Grafana ide preko Docker-a: `http://influxdb:8086`
		 - Ako Grafana nije u Docker-u: `http://localhost:8086`
	 - Org: `smart-home`
	 - Token: isti token iz settings.json
	 - Bucket: `iot`
4. Klikni **Save & Test**.

## 9) Import dashboard-a
U Grafani:
1. Klikni **Dashboards → New → Import**
2. Izaberi fajl [grafana/smart-home-kt2-dashboard.json](grafana/smart-home-kt2-dashboard.json)
3. Kada te pita za datasource, izaberi InfluxDB koji si upravo dodao.

## 10) Gotovo
Ako se paneli pune podacima – KT2 je kompletan.

## Napomene
- Ako pokrećeš na Raspberry Pi, podesi `simulate: false` u [simulation/settings.json](simulation/settings.json) za konkretne GPIO komponente.
- U slučaju da ne vidiš podatke, proveri da `mqtt_influx_server.py` radi i da PI1 kontroler šalje događaje.
