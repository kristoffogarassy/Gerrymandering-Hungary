# Gerrymandering Hungary

Egy Python-alapú eszköz, amely a 2026-os magyar országgyűlési választás szavazóköri eredményeiből újraépíti a 106 országgyűlési egyéni választókerületet (OEVK), majd egy **MCMC-alapú (ReCom) algoritmussal** újrarajzolja a körzethatárokat egy kiválasztott párt javára. A célja annak mérése, hogy ugyanezekkel a szavazatokkal mennyivel térne el a mandátumeloszlás más határvonalak mellett. A választási adatok tisztításában és geokódolásában, a regex kódok megírásában, a kiindulási gráfok és térképek elkészítésében és a UI létrehozása során gyakran használtuk a ChatGPT és a Gemini segítségét (és persze sokat tanultunk tőlük a fő gerrymandering file struktúrájának megalkotásáról, és az egyes könyvtárak használatáról).


## Előkészületek

Python 3.10+ szükséges. A függőségek telepítése:

```
pip install -r requirements.txt
```

Ez telepíti a `pandas`, `geopandas`, `shapely`, `pyproj`, `rtree`, `networkx`, `folium`, `branca`, `geopy`, `openpyxl`, `xlrd` csomagokat. 

A Tkinter GUI nélkül is futtatható minden, csak a paramétereket kódból kell állítani.

## A program részei

| Fájl | Mit csinál |
|---|---|
| `pipeline_2026.py` | NVI listás XLS-ek + körzetállomány CSV + admin8 shapefile → szavazóköri tábla, elemzési egységek (4 193 db), szomszédossági gráf, Folium HTML térképek. |
| `gerrymander_2026.py` | A ReCom-lite MCMC algoritmus. Bemenet: `output/egysegek_2026.geojson`. Vármegyénként optimalizál egy kiválasztott pártnak kedvező OEVK-térképet. |
| `gerrymander_ui_2026.py` | Tkinter alapú grafikus indító az algoritmushoz. |

A klónozott repó **`output/` mappája már egy lefuttatott pipeline-kimenetet tartalmaz**, így az MCMC-rész azonnal futtatható – a pipeline csak akkor kell, ha új adattal akarsz dolgozni.

## Bemeneti adatok

A `data/` mappa szerkezete:

```
data/
├── lista/        ← 20 db NVI vármegyei listás XLS (a repóban van)
├── teruletek/
│   └── admin8.*  ← OSM-alapú településhatárok (a repóban van)
└── Korzet_levalogatas20260116_ORSZAGOS.csv   ← KÜLÖN letöltendő a valasztas.hu-ról
```

A 9 nagyvárosban (Budapest, Debrecen, Szeged, Miskolc, Pécs, Győr, Nyíregyháza, Kecskemét, Székesfehérvár) a szavazóköri címeket a Nominatim geokódolja; ezek koordinátáit a `cache/szavazokor_geocode.csv` el is tárolja, hogy ne kelljen újra lekérdezni.

## Futtatás

### 1. Pipeline (csak ha újra kell építeni az adatot)

```
cd valasztas2026
python pipeline_2026.py --no-geocode
```

A `--no-geocode` kapcsoló miatt csak a meglévő cache-ből dolgozik (gyors). Cache nélkül a Nominatim 1 hívás/mp limit miatt 30+ percig fut.

### 2. MCMC GUI-ból

```
cd valasztas2026
python gerrymander_ui_2026.py
```

Tkinter-ablak nyílik, ahol minden paramétert beállíthatsz. A futás a terminálba ír haladásüzeneteket, a végén kiírja, hova mentett.

### 3. MCMC GUI nélkül

A `gerrymander_2026.py` tetején lévő globális konstansokat kell átírni, majd:

```
python gerrymander_2026.py
```

## Konfiguráció

A főbb beállítások a `gerrymander_2026.py` tetején vagy a GUI mezőin:

| Beállítás | Leírás | Default |
|---|---|---|
| `TARGET_COL` | Melyik pártnak kedvezzen az algoritmus | `"tisza_szavazat"` (másik: `"fidesz_szavazat"`) |
| `OPPONENT_COL` | A „másik” párt (ezt packel-jük) | `"fidesz_szavazat"` |
| `RUN_COUNTIES` | Csak ezekre a megyékre fusson, üresen az összes | `[]` |
| `EPSILON` | Maximális népességeltérés a megyei átlaghoz képest | `0.12` (= ±12 %) |
| `RESTARTS` | Független MCMC-láncok száma | `4` |
| `STEPS_PER_RESTART` | Egy lánc lépésszáma | `3500` |
| `RECOM_PROBABILITY` | ReCom vs. boundary-flip arány | `0.78` |
| `RANDOM_SEED` | Reprodukálhatóság miatt | `20260508` |
| `SEAT_WEIGHT` | Egy nyert mandátum értéke a célfüggvényben | `350 000` |
| `POP_PENALTY_WEIGHT` | Népességeltérés büntetés súlya | `220 000` |
| `CUT_LENGTH_WEIGHT` | Kompaktság (cut length, méterben) | `0.055` |
| `BP_KERULET_SPLIT_WEIGHT` | Budapesti kerület szétvágásának büntetése | `70 000` |

## Algoritmus röviden

Vármegyénként külön optimalizálunk (mert OEVK-k nem léphetik át a vármegyehatárt). Kezdőtérképnek a tényleges 2026-os OEVK-felosztást vesszük. Lépésenként vagy egy **ReCom-lépés** (két szomszédos körzet uniójára feszítőfa, abból egy él kivágása új partícióra) vagy egy **boundary-flip** (egyetlen csomópont szomszédos körzetbe írása) történik. Minden javasolt lépés érvényességét ellenőrizzük (összefüggőség, populáció), majd **simulated annealing** elfogadással haladunk. A célfüggvény jutalmazza a célpárt mandátumait és az ellenfél packelését, bünteti a populációs eltérést, a hosszú vágásokat (kompaktság), a budapesti kerületek szétvágását és a Duna-átszelő körzeteket.

## Példa futtatás

Egy példa futtatás már elérhető a repóban Szabolcs-Szatmár-Bereg megyére, de amint lefutnak az országos kódok, feltöltjük azt is és írunk róluk részletesebben is.


| Fájl | Tartalma |
|---|---|
| `szavazokorok_2026.csv` | Mind a 10 022 szavazókör mestertáblája. |
| `szavazokor_eredmeny_2026.csv` | Szavazókör + listás eredmény. |
| `egysegek_2026.geojson` | A 4 193 elemzési egység (Voronoi + település). **Az MCMC bemenete.** |
| `terkepek/*.html` | 6 db Folium interaktív térkép. |
| `gerrymandering_graf/gerry_graph_2026.graphml` | NetworkX szomszédossági gráf (4 193 csomópont, 12 227 él). |

Egy MCMC-futás (`output/gerry_recom_lite_runs/<futás>/`):

| Fájl | Tartalma |
|---|---|
| `00_osszefoglalo.csv` | A fő mérőszám: eredeti vs. szimulált mandátumok, kompaktság, népesség. |
| `01_megyei_mandatumvaltozas.csv` | Megyénkénti mandátum-delta. |
| `02_korzet_osszehasonlitas.csv` | Mind a 2N körzet adatai egymás mellé téve. |
| `03_legszorosabb_korzetek.csv` | A legszűkebb körzetek (a térkép „törési pontjai”). |
| `01_szimulalt_margin.html`, `03_eredeti_margin.html` | Folium térképek a két verzióhoz. |
| `recom_districts_2026.geojson` | A szimulált OEVK-határok (GIS-be tölthető). |
| `metadata.json` | Minden bemeneti paraméter és a futás eredménye. |
| `png_abrak/01..06_*.png` | 6 db PNG ábra a futásról. |

## Megjegyzés

A listás eredményt használjuk az egyéni szavazási hajlandóság proxyjaként, mert az egyéni jelölt népszerűsége erősen befolyásolja az eredményeket, új körzeteknél azonban persze más jelöltek lehetnek. A korreláció erős, de nem 100 %.
