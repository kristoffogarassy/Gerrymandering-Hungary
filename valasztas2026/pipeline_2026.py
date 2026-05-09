

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

import folium
import geopandas as gpd
import networkx as nx
import pandas as pd
from branca.colormap import LinearColormap
from shapely.geometry import MultiPoint
from shapely.ops import voronoi_diagram
from shapely.validation import make_valid


# Beállítások.


VORONOI_VAROSOK = [
    "Budapest",
    "Debrecen",
    "Szeged",
    "Miskolc",
    "Pécs",
    "Győr",
    "Nyíregyháza",
    "Kecskemét",
    "Székesfehérvár",
]


ADMIN8_ALAP_CRS = 3857

# Munkához méteres vetület.
METERES_CRS = 23700
WGS84 = 4326


LISTA_ALAP_OSZLOPOK = {
    "AL": "nevjegyzek_szavazokor",
    "EL": "valasztopolgar",
    "JL": "megjelent",
    "M": "ervenytelen",
    "NL": "ervenyes",
}



NEV_ROVIDITESEK = [
    (r"\bKeleti\s+K\.\s*", "Keleti Károly "),
    (r"\bKossuth\s+L\.\s*", "Kossuth Lajos "),
    (r"\bBem\s+J\.\s*", "Bem József "),
    (r"\bVarsányi\s+I\.\s*", "Varsányi Irén "),
    (r"\bSzigeti\s+J\.\s*", "Szigeti József "),
    (r"\bRadnóti\s+M\.\s*", "Radnóti Miklós "),
    (r"\bRegele\s+J\.\s*", "Regele János "),
    (r"\bBajcsy\s+Zs\.\s*", "Bajcsy-Zsilinszky "),
    (r"\bKosztolányi\s+D\.\s*", "Kosztolányi Dezső "),
    (r"\bGulner\s+Gy\.\s*", "Gulner Gyula "),
    (r"\bReviczky\s+Gy\.\s*", "Reviczky Gyula "),
    (r"\bKondor\s+B\.\s*", "Kondor Béla "),
    (r"\bWlassics\s+Gy\.\s*", "Wlassics Gyula "),
    (r"\bAdy\s+E\.\s*", "Ady Endre "),
    (r"\bTáncsics\s+M\.\s*", "Táncsics Mihály "),
    (r"\bKatona\s+J\.\s*", "Katona József "),
    (r"\bCsete\s+B\.\s*", "Csete Balázs "),
    (r"\bSimon\s+B\.\s*", "Simon Bolivár "),
    (r"\bKiss\s+János\s+Atb\.\s*", "Kiss János altábornagy "),
    (r"\bKiss\s+J\.\s*Atb\.\s*", "Kiss János altábornagy "),
    (r"\bKiss\s+J\.\s*altb\.\s*", "Kiss János altábornagy "),
    (r"\bII\.?\s*Rákóczi\s+F\.\s*", "II. Rákóczi Ferenc "),

    (r"\bBencze\s+J\.\s*", "Bencze József "),
    (r"\bTörök\s+I\.\s*", "Török István "),
    (r"\bDobó\s+I\.\s*", "Dobó István "),
    (r"\bZsolnay\s+V\.\s*", "Zsolnay Vilmos "),
    (r"\bEngel\s+J\.\s*J\.\s*", "Engel János József "),
    (r"\bMajorossy\s+I\.\s*", "Majorossy Imre "),
    (r"\bMikszáth\s+K\.\s*", "Mikszáth Kálmán "),
    (r"\bJurisics\s+M\.\s*", "Jurisics Miklós "),
    (r"\bPetőfi\s+S\.\s*", "Petőfi Sándor "),
    (r"\bVeress\s+E\.\s*", "Veress Endre "),
    (r"\bEsztergár\s+L\.\s*", "Esztergár Lajos "),
    (r"\bBánki\s+D\.\s*", "Bánki Donát "),
    (r"\bPázmány\s+P\.\s*", "Pázmány Péter "),
    (r"\bFábián\s+B\.\s*", "Fábián Béla "),
    (r"\bLittke\s+J\.\s*", "Littke József "),
    (r"\bVárkonyi\s+N\.\s*", "Várkonyi Nándor "),
    (r"\bAidinger\s+J\.\s*", "Aidinger János "),
    (r"\bLovász\s+P\.\s*", "Lovász Pál "),
    (r"\bApáczai\s+Cs\.?\s*J\.\s*", "Apáczai Csere János "),
    (r"\bSoltész\s+N\.?\s*K\.\s*", "Soltész Nagy Kálmán "),
    (r"\bVörösmarty\s+M\.\s*", "Vörösmarty Mihály "),
    (r"\bSzilágyi\s+D\.\s*", "Szilágyi Dezső "),
    (r"\bHajós\s+A\.\s*", "Hajós Alfréd "),
    (r"\bGörgey\s+A\.\s*", "Görgey Artúr "),
    (r"\bSzigethy\s+M\.\s*", "Szigethy Mihály "),
    (r"\bKálvin\s+J\.\s*", "Kálvin János "),
    (r"\bBársony\s+J\.\s*", "Bársony János "),
    (r"\bHerman\s+O\.\s*", "Herman Ottó "),
    (r"\bRácz\s+Á\.\s*", "Rácz Ádám "),
    (r"\bKönyves\s+K\.\s*", "Könyves Kálmán "),
    (r"\bBolyai\s+F\.\s*", "Bolyai Farkas "),
    (r"\bMóra\s+F\.\s*", "Móra Ferenc "),
    (r"\bCsáky\s+J\.\s*", "Csáky József "),
    (r"\bBudai\s+N\.?\s*A\.\s*", "Budai Nagy Antal "),
    (r"\bJózsef\s+A\.\s*", "József Attila "),
    (r"\bTisza\s+L\.\s*", "Tisza Lajos "),
]



# segédfüggvények

def tisztit_szoveg(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def nagybetu(x) -> str:
    return tisztit_szoveg(x).upper()


def slug(x, max_len: int = 80) -> str:
    s = tisztit_szoveg(x).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:max_len] or "x")


def kod(x, hossz: int) -> str:
    s = tisztit_szoveg(x)
    if not s:
        return ""
    if re.fullmatch(r"\d+(\.0)?", s):
        s = str(int(float(s)))
    return s.zfill(hossz)


def szam(x) -> float:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 0
    if isinstance(x, (int, float)):
        return x
    s = str(x).replace("\xa0", "").strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace(",", ".")
    if not s:
        return 0
    try:
        return float(s)
    except ValueError:
        return 0


def norm_varos(x) -> str:
    s = tisztit_szoveg(x)
    if s.lower().startswith("budapest"):
        return "Budapest"
    return s


def egyszeru_norm(x) -> str:
    s = norm_varos(x).lower()
    for a, b in {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ö": "o", "ő": "o",
        "ú": "u", "ü": "u", "ű": "u",
    }.items():
        s = s.replace(a, b)
    return s


def kell_voronoi(telepules) -> bool:
    return egyszeru_norm(telepules) in {egyszeru_norm(v) for v in VORONOI_VAROSOK}



ROMAI_KERULET = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX",
    10: "X", 11: "XI", 12: "XII", 13: "XIII", 14: "XIV", 15: "XV", 16: "XVI",
    17: "XVII", 18: "XVIII", 19: "XIX", 20: "XX", 21: "XXI", 22: "XXII", 23: "XXIII",
}
ROMAI_TO_SZAM = {v: k for k, v in ROMAI_KERULET.items()}


def budapest_kerulet_szam(telepules, telepules_kod="") -> int | None:
    if not tisztit_szoveg(telepules).lower().startswith("budapest"):
        return None

    tk = kod(telepules_kod, 3)
    if tk.isdigit():
        n = int(tk)
        if 1 <= n <= 23:
            return n

    s = nagybetu(telepules)
    m = re.search(r"BUDAPEST\s+([IVXLCDM]+|\d+)", s)
    if m:
        darab = m.group(1).strip(" .")
        if darab.isdigit():
            n = int(darab)
            if 1 <= n <= 23:
                return n
        return ROMAI_TO_SZAM.get(darab)
    return None


def budapest_kerulet_nevek(telepules, telepules_kod="") -> list[str]:
    n = budapest_kerulet_szam(telepules, telepules_kod)
    if not n:
        return []
    romai = ROMAI_KERULET.get(n, str(n))
    return [
        f"Budapest {romai}. kerület",
        f"Budapest {n}. kerület",
        f"Budapest, {romai}. kerület",
        f"Budapest, {n}. kerület",
    ]


def normalizal_cim(cim: object) -> list[str]:
    c0 = tisztit_szoveg(cim)
    c1 = re.sub(r"\s*\(.*?\)", "", c0).strip()

    # gyakori rövidítések
    def exp(s: str) -> str:
        s = re.sub(r"\bu\.?\b", "utca", s, flags=re.I)
        s = re.sub(r"\bkrt\.?\b", "körút", s, flags=re.I)
        s = re.sub(r"\bkt\.?\b", "körút", s, flags=re.I)
        s = re.sub(r"\btr\.?\b", "tér", s, flags=re.I)
        s = re.sub(r"\bt\.\b", "tér", s, flags=re.I)
        s = re.sub(r"\bsgt\.?\b", "sugárút", s, flags=re.I)
        s = re.sub(r"\brkp\.?\b", "rakpart", s, flags=re.I)
        s = re.sub(r"\bltp\.?\b", "lakótelep", s, flags=re.I)
        s = re.sub(r"\bút\.\b", "út", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    c2 = exp(c1)

    # házszám nélküli fallback, ha a házszám/épület betűje zavarja
    c3 = re.sub(r"\s+\d+.*$", "", c2).strip()

    # az ilyen 9-11 néha jobb 9-ként
    c4 = re.sub(r"(\d+)\s*[-–—]\s*\d+", r"\1", c2).strip()

    out = []
    for c in [c2, c1, c0, c4, c3]:
        if c and c not in out:
            out.append(c)
    return out


def geocode_query_variaciok(row) -> list:
    telepules = tisztit_szoveg(getattr(row, "telepules", ""))
    telepules_csoport = tisztit_szoveg(getattr(row, "telepules_csoport", norm_varos(telepules)))
    telepules_kod = tisztit_szoveg(getattr(row, "telepules_kod", ""))
    irsz = kod(getattr(row, "iranyitoszam", ""), 4)
    varmegye = tisztit_szoveg(getattr(row, "varmegye", ""))
    cim = tisztit_szoveg(getattr(row, "szavazokor_cim", ""))
    cimek = normalizal_cim(cim)

    bp = telepules.lower().startswith("budapest") or telepules_csoport.lower() == "budapest"
    helyek = []

    if bp:
        # Elsőnek strukturált queryk.
        for c in cimek[:3]:
            if irsz:
                helyek.append({"street": c, "city": "Budapest", "postalcode": irsz, "country": "Hungary"})
            helyek.append({"street": c, "city": "Budapest", "country": "Hungary"})

        # Utána szöveges variációk kerülettel/irányítószámmal.
        prefixes = []
        if irsz:
            prefixes.append(f"{irsz} Budapest")
        prefixes.append("Budapest")
        prefixes.extend(budapest_kerulet_nevek(telepules, telepules_kod))

        for pref in prefixes:
            for c in cimek:
                helyek.append(f"{pref}, {c}, Magyarország")
        for c in cimek:
            if irsz:
                helyek.append(f"{c}, {irsz} Budapest, Magyarország")
            helyek.append(f"{c}, Budapest, Magyarország")
    else:
        prefixes = []
        if irsz:
            prefixes.append(f"{irsz} {telepules}")
        prefixes.append(telepules)
        if telepules_csoport and telepules_csoport != telepules:
            prefixes.append(telepules_csoport)
        if varmegye:
            prefixes.append(f"{telepules}, {varmegye}")

        for c in cimek:
            if irsz:
                helyek.append({"street": c, "city": telepules, "postalcode": irsz, "country": "Hungary"})
            for pref in prefixes:
                helyek.append(f"{pref}, {c}, Magyarország")

    # duplák ki
    seen = set()
    out = []
    for q in helyek:
        key = json.dumps(q, ensure_ascii=False, sort_keys=True) if isinstance(q, dict) else q.lower()
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out


def geocode_label(q) -> str:
    if isinstance(q, dict):
        return json.dumps(q, ensure_ascii=False)
    return str(q)

def szavazokor_id(varmegye_kod, telepules_kod, szavazokor) -> str:
    return f"{kod(varmegye_kod, 2)}-{kod(telepules_kod, 3)}-{kod(szavazokor, 3)}"


def parse_szavazokor_azon(x) -> dict:
    """
    03-060-006-9 -> 03, 060, 006
    A végén lévő ellenőrző szám nekünk nem kell.
    """
    s = tisztit_szoveg(x)
    m = re.search(r"(?P<m>\d{2})-(?P<t>\d{3})-(?P<sz>\d{3})(?:-\d+)?", s)
    if not m:
        return {"varmegye_kod": "", "telepules_kod": "", "szavazokor": "", "szavazokor_id": ""}
    d = m.groupdict()
    return {
        "varmegye_kod": d["m"],
        "telepules_kod": d["t"],
        "szavazokor": d["sz"],
        "szavazokor_id": f"{d['m']}-{d['t']}-{d['sz']}",
    }


def keres_fajlt(mappa: Path, kulcsszavak: list[str], vegzodesek: tuple[str, ...]) -> Path | None:
    talalatok = []
    if not mappa.exists():
        return None
    for p in mappa.rglob("*"):
        if not p.is_file():
            continue
        nev = p.name.lower()
        if p.suffix.lower() not in vegzodesek:
            continue
        if all(k.lower() in nev for k in kulcsszavak):
            talalatok.append(p)
    if not talalatok:
        return None
    return sorted(talalatok, key=lambda p: (len(str(p)), str(p)))[0]


def excel_fajlok(mappa: Path) -> list[Path]:
    if not mappa.exists():
        return []
    out = []
    for suf in ("*.xls", "*.xlsx"):
        out.extend(sorted(mappa.rglob(suf)))
    # ide nem kérünk ideiglenes Excel-fájlokat
    out = [p for p in out if not p.name.startswith("~$")]
    return out


# XLS olvasás. Régi .xls-nél xlrd kell, vagy LibreOffice fallback.


def libreoffice_cmd() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def excel_file(path: Path, cache_dir: Path) -> pd.ExcelFile:
    path = Path(path)

    try:
        # pandas választ engine-t: xls -> xlrd, xlsx -> openpyxl
        return pd.ExcelFile(path)
    except Exception:
        pass

    # Ha régi xls és nincs xlrd, megpróbáljuk LibreOffice-szal átkonvertálni.
    if path.suffix.lower() == ".xls":
        cmd = libreoffice_cmd()
        if not cmd:
            raise RuntimeError(
                f"Nem tudom olvasni ezt az XLS-t: {path}\n"
                "Telepítsd: pip install xlrd\n"
                "vagy telepíts LibreOffice-t."
            )

        cache_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [cmd, "--headless", "--convert-to", "xlsx", "--outdir", str(cache_dir), str(path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        uj = cache_dir / (path.stem + ".xlsx")
        if not uj.exists():
            jeloltek = list(cache_dir.glob(path.stem + "*.xlsx"))
            if not jeloltek:
                raise RuntimeError(f"LibreOffice sem tudta konvertálni: {path}")
            uj = jeloltek[0]
        return pd.ExcelFile(uj)

    raise


# Listás eredmények olvasása

def parameter_sheet(book: pd.ExcelFile) -> pd.DataFrame:
    if "Paraméterek" in book.sheet_names:
        return pd.read_excel(book, "Paraméterek", header=None)
    return pd.read_excel(book, book.sheet_names[0], header=None)


def varmegye_parameterekbol(param: pd.DataFrame) -> str:
    for _, row in param.iterrows():
        vals = [tisztit_szoveg(v) for v in row.tolist()]
        for i, v in enumerate(vals):
            if "Vármegye neve" in v and i + 1 < len(vals):
                return nagybetu(vals[i + 1])
    return ""


def partlistak(book: pd.ExcelFile) -> pd.DataFrame:
    param = parameter_sheet(book)
    start = None

    for idx, row in param.iterrows():
        vals = [nagybetu(v) for v in row.tolist()]
        if "SORSZÁM" in vals and "RÖVID NÉV" in vals:
            start = idx + 1
            break

    if start is None:
        raise RuntimeError("Nem találom a pártlistákat a Paraméterek lapon.")

    rows = []
    for _, row in param.iloc[start:].iterrows():
        sorszam = kod(row.iloc[0], 2)
        rovid = tisztit_szoveg(row.iloc[1]) if len(row) > 1 else ""
        teljes = tisztit_szoveg(row.iloc[2]) if len(row) > 2 else ""
        if not sorszam or not rovid:
            break
        rows.append({
            "lista_sorszam": sorszam,
            "part_rovid": rovid,
            "part_teljes": teljes,
            "part_slug": slug(rovid),
        })

    return pd.DataFrame(rows)


def tisztit_eredmeny_tabla(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [tisztit_szoveg(c) for c in df.columns]
    if len(df.columns) < 2:
        return pd.DataFrame()
    a, b = df.columns[0], df.columns[1]
    df = df[df[a].notna() & df[b].notna()].copy()
    df = df[~df[a].astype(str).str.contains("Település", case=False, na=False)]
    return df


def oszlop_lookup(df: pd.DataFrame) -> dict[str, str]:
    """
    Az Excel néha 1-nek, néha 01-nek látja ugyanazt.
    Ezért csinálunk egy 2 jegyű lookupot is.
    """
    out = {}
    for c in df.columns:
        cc = kod(c, 2)
        if cc:
            out[cc] = c
        out[tisztit_szoveg(c)] = c
    return out


def parse_lista_file(path: Path, cache_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    book = excel_file(path, cache_dir)
    param = parameter_sheet(book)
    varmegye = varmegye_parameterekbol(param)
    partok = partlistak(book)
    part_by_code = partok.set_index("lista_sorszam").to_dict("index")

    wide_rows = []
    long_rows = []

    for sheet in book.sheet_names:
        if sheet.lower() == "paraméterek" or "nemz" in sheet.lower():
            continue

        # A NVI táblákban általában a 2. sor a fejléc.
        df = pd.read_excel(book, sheet_name=sheet, header=1)
        df = tisztit_eredmeny_tabla(df)
        if df.empty:
            continue

        lookup = oszlop_lookup(df)
        telep_col = df.columns[0]
        azon_col = df.columns[1]

        base = pd.DataFrame({
            "varmegye": varmegye or nagybetu(sheet),
            "telepules": df[telep_col].map(tisztit_szoveg),
            "szavazokor_azon": df[azon_col].map(tisztit_szoveg),
        })

        parsed = pd.DataFrame([parse_szavazokor_azon(x) for x in base["szavazokor_azon"]])
        base = pd.concat([base.reset_index(drop=True), parsed], axis=1)

        for regi, uj in LISTA_ALAP_OSZLOPOK.items():
            if regi in lookup:
                base[uj] = df[lookup[regi]].map(szam).astype(int)
            else:
                base[uj] = 0

        party_cols = []
        col_to_party = {}

        for code, meta in part_by_code.items():
            real_col = lookup.get(code)
            if real_col is None:
                continue

            out_col = "lista_" + meta["part_slug"]
            base[out_col] = df[real_col].map(szam).astype(int)
            party_cols.append(out_col)
            col_to_party[out_col] = meta["part_rovid"]

            tmp = base[["varmegye", "telepules", "szavazokor_azon", "szavazokor_id", "ervenyes"]].copy()
            tmp["lista_sorszam"] = code
            tmp["part_rovid"] = meta["part_rovid"]
            tmp["part_teljes"] = meta["part_teljes"]
            tmp["szavazat"] = base[out_col]
            long_rows.append(tmp)

        if party_cols:
            mat = base[party_cols]
            winner_col = mat.idxmax(axis=1)
            base["gyoztes_lista"] = winner_col.map(col_to_party)
            base["gyoztes_lista_szavazat"] = mat.max(axis=1).astype(int)

            sorted_votes = mat.apply(lambda r: sorted(r.tolist(), reverse=True), axis=1)
            base["masodik_lista_szavazat"] = sorted_votes.map(lambda x: int(x[1]) if len(x) > 1 else 0)
            base["gyoztes_margin_szavazat"] = base["gyoztes_lista_szavazat"] - base["masodik_lista_szavazat"]
            base["osszes_partlista_szavazat"] = mat.sum(axis=1).astype(int)

            fidesz_cols = [c for c in party_cols if "fidesz" in c.lower() or "kdnp" in c.lower()]
            tisza_cols = [c for c in party_cols if "tisza" in c.lower()]
            base["fidesz_szavazat"] = base[fidesz_cols].sum(axis=1).astype(int) if fidesz_cols else 0
            base["tisza_szavazat"] = base[tisza_cols].sum(axis=1).astype(int) if tisza_cols else 0
            base["nem_fidesz_szavazat"] = base["osszes_partlista_szavazat"] - base["fidesz_szavazat"]
            base["egyeb_szavazat"] = base["osszes_partlista_szavazat"] - base["fidesz_szavazat"] - base["tisza_szavazat"]

        base = ujraszamol_szazalekok(base, col_to_party)
        wide_rows.append(base)

    wide = pd.concat(wide_rows, ignore_index=True) if wide_rows else pd.DataFrame()
    long = pd.concat(long_rows, ignore_index=True) if long_rows else pd.DataFrame()
    return wide, long



# Körzetállomány olvasása

def normalizal_korzet_csv(path: Path) -> pd.DataFrame:
    #PIR = irányítószám
    wanted = [
        "Vármegye kód", "Vármegye", "OEVK", "Település kód", "Település", "TEVK",
        "Szavazókör", "Szavazókör cím", "Kijelölt", "Akadálymentesített", "PIR",
    ]

    header = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig", nrows=0).columns.tolist()
    usecols = [c for c in wanted if c in header]

    kotelezo = ["Vármegye kód", "Vármegye", "OEVK", "Település kód", "Település", "Szavazókör", "Szavazókör cím"]
    hiany = [c for c in kotelezo if c not in usecols]
    if hiany:
        raise RuntimeError(f"Hiányzó oszlopok a körzet CSV-ben: {hiany}")

    frames = []
    for chunk in pd.read_csv(
        path,
        sep=";",
        dtype=str,
        encoding="utf-8-sig",
        usecols=usecols,
        chunksize=400_000,
    ):
        chunk = chunk.drop_duplicates(["Vármegye kód", "Település kód", "Szavazókör"])
        frames.append(chunk)

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(["Vármegye kód", "Település kód", "Szavazókör"])

    for c in wanted:
        if c not in df.columns:
            df[c] = ""

    out = pd.DataFrame({
        "varmegye_kod": df["Vármegye kód"].map(lambda x: kod(x, 2)),
        "varmegye": df["Vármegye"].map(nagybetu),
        "oevk": df["OEVK"].map(lambda x: kod(x, 2)),
        "telepules_kod": df["Település kód"].map(lambda x: kod(x, 3)),
        "telepules": df["Település"].map(tisztit_szoveg),
        "tevk": df["TEVK"].map(lambda x: kod(x, 2)),
        "szavazokor": df["Szavazókör"].map(lambda x: kod(x, 3)),
        "szavazokor_cim": df["Szavazókör cím"].map(tisztit_szoveg),
        "iranyitoszam": df["PIR"].map(lambda x: kod(x, 4)),
        "pir": df["PIR"].map(lambda x: kod(x, 4)),
        "kijelolt": df["Kijelölt"].map(tisztit_szoveg),
        "akadalymentes": df["Akadálymentesített"].map(tisztit_szoveg),
    })

    out["szavazokor_id"] = [
        szavazokor_id(a, b, c)
        for a, b, c in zip(out["varmegye_kod"], out["telepules_kod"], out["szavazokor"])
    ]
    out["oevk_id"] = out["varmegye_kod"] + "-" + out["oevk"]
    return out.sort_values(["varmegye_kod", "telepules_kod", "szavazokor"])


def fejléc_sor_keres(raw: pd.DataFrame, kell_szavak: list[str]) -> int:
    for idx, row in raw.iterrows():
        vals = [nagybetu(v) for v in row.tolist()]
        ok = True
        for szo in kell_szavak:
            if not any(nagybetu(szo) in v for v in vals):
                ok = False
                break
        if ok:
            return int(idx)
    raise RuntimeError("Nem találom a fejlécsort az Excelben.")


def normalizal_korzet_excel(path: Path, cache_dir: Path) -> pd.DataFrame:
    # Teszthez
    book = excel_file(path, cache_dir)
    raw = pd.read_excel(book, sheet_name=book.sheet_names[0], header=None)
    header = fejléc_sor_keres(raw, ["Vármegye", "Település", "Sorsz"])
    df = pd.read_excel(book, sheet_name=book.sheet_names[0], header=header)

    out = pd.DataFrame({
        "varmegye_kod": "",
        "varmegye": df["Vármegye"].map(nagybetu),
        "oevk": df["OEVK"].map(lambda x: kod(x, 2)) if "OEVK" in df.columns else "",
        "telepules_kod": "",
        "telepules": df["Település"].map(tisztit_szoveg),
        "tevk": df["TEVK"].map(lambda x: kod(x, 2)) if "TEVK" in df.columns else "",
        "szavazokor": df["Sorsz."].map(lambda x: kod(x, 3)),
        "szavazokor_cim": df["Címe"].map(tisztit_szoveg),
        "iranyitoszam": df["PIR"].map(lambda x: kod(x, 4)) if "PIR" in df.columns else "",
        "pir": df["PIR"].map(lambda x: kod(x, 4)) if "PIR" in df.columns else "",
        "kijelolt": "",
        "akadalymentes": df["Akadálymentes"].map(tisztit_szoveg) if "Akadálymentes" in df.columns else "",
    })

    # Itt nincs településkód, szóval ez kevésbé stabil.
    out["szavazokor_id"] = out["varmegye"] + "|" + out["telepules"] + "|" + out["szavazokor"]
    out["oevk_id"] = out["varmegye_kod"] + "-" + out["oevk"]
    return out


def normalizal_korzet(path: Path, cache_dir: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return normalizal_korzet_csv(path)
    return normalizal_korzet_excel(path, cache_dir)


# Százalékok, győztesek

def part_oszlopok(df: pd.DataFrame) -> list[str]:
    rosszak = {
        "lista_sorszam",
    }
    cols = []
    for c in df.columns:
        if c.startswith("lista_") and c not in rosszak:
            if not c.endswith("_pct"):
                cols.append(c)
    return cols


def ujraszamol_szazalekok(df: pd.DataFrame, col_to_party: dict | None = None) -> pd.DataFrame:
    out = df.copy()
    vote_cols = part_oszlopok(out)

    for c in vote_cols + [
        "ervenyes", "valasztopolgar", "megjelent", "fidesz_szavazat", "tisza_szavazat",
        "nem_fidesz_szavazat", "egyeb_szavazat", "osszes_partlista_szavazat",
    ]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    if vote_cols:
        mat = out[vote_cols]
        winner_col = mat.idxmax(axis=1)
        names = col_to_party or {c: c.replace("lista_", "") for c in vote_cols}
        out["gyoztes_lista"] = winner_col.map(names)
        out["gyoztes_lista_szavazat"] = mat.max(axis=1).astype(int)

        sorted_votes = mat.apply(lambda r: sorted(r.tolist(), reverse=True), axis=1)
        out["masodik_lista_szavazat"] = sorted_votes.map(lambda x: int(x[1]) if len(x) > 1 else 0)
        out["gyoztes_margin_szavazat"] = out["gyoztes_lista_szavazat"] - out["masodik_lista_szavazat"]

        if "ervenyes" in out.columns:
            denom = out["ervenyes"].replace(0, pd.NA)
            out["gyoztes_arany_pct"] = (out["gyoztes_lista_szavazat"] / denom * 100).fillna(0).round(3)
            out["margin_pct"] = (out["gyoztes_margin_szavazat"] / denom * 100).fillna(0).round(3)
            for c in vote_cols:
                out[c.replace("lista_", "pct_")] = (out[c] / denom * 100).fillna(0).round(3)

    if {"fidesz_szavazat", "tisza_szavazat", "ervenyes"}.issubset(out.columns):
        denom = out["ervenyes"].replace(0, pd.NA)
        out["fidesz_pct"] = (out["fidesz_szavazat"] / denom * 100).fillna(0).round(3)
        out["tisza_pct"] = (out["tisza_szavazat"] / denom * 100).fillna(0).round(3)
        out["fidesz_tisza_margin_pct"] = (out["fidesz_pct"] - out["tisza_pct"]).round(3)
        out["abs_margin_pct"] = out["fidesz_tisza_margin_pct"].abs().round(3)

    if {"megjelent", "valasztopolgar"}.issubset(out.columns):
        denom = out["valasztopolgar"].replace(0, pd.NA)
        out["reszvetel_pct"] = (out["megjelent"] / denom * 100).fillna(0).round(3)

    return out


def osszeg_oszlopok(df: pd.DataFrame) -> list[str]:
    fix = {
        "nevjegyzek_szavazokor", "valasztopolgar", "megjelent", "ervenytelen", "ervenyes",
        "fidesz_szavazat", "tisza_szavazat", "nem_fidesz_szavazat", "egyeb_szavazat",
        "osszes_partlista_szavazat", "gyoztes_lista_szavazat", "masodik_lista_szavazat",
        "gyoztes_margin_szavazat",
    }
    out = []
    for c in df.columns:
        if c in fix or c.startswith("lista_"):
            if not c.endswith("_pct") and "margin_pct" not in c:
                out.append(c)
    return out



# Geokódolás, Cache-sel.


def olvas_cache(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, dtype=str)
    return pd.DataFrame(columns=["cache_key", "latitude", "longitude", "talalat"])


def ment_cache(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.drop_duplicates("cache_key", keep="last").to_csv(path, index=False, encoding="utf-8-sig")


BUDAPEST_ROMAI = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
    "XIII": 13, "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17,
    "XVIII": 18, "XIX": 19, "XX": 20, "XXI": 21, "XXII": 22, "XXIII": 23,
}

# Ezeket a cache-mintákból raktam bele.
# csak extra query-variációt adnak a geokódolónak.
UTCA_NEV_ROVIDITESEK = [
    (r"\bII\s*\.\s*Rákóczi\s+F\.", "II. Rákóczi Ferenc"),
    (r"\bII\s*Rákóczi\s+F\.", "II. Rákóczi Ferenc"),
    (r"\bApáczai\s+Cs\s*\.\s*J\.", "Apáczai Csere János"),
    (r"\bSoltész\s+N\s*\.\s*K\.", "Soltész Nagy Kálmán"),
    (r"\bBudai\s+N\s*\.\s*A\.", "Budai Nagy Antal"),
    (r"\bEngel\s+J\s*\.\s*J\.", "Engel János József"),
    (r"\bKiss\s+J\s*\.\s*(?:altb|atb)\.?", "Kiss János altábornagy"),
    (r"\bKiss\s+János\s+(?:altb|atb)\.?", "Kiss János altábornagy"),

    (r"\bKeleti\s+K\.", "Keleti Károly"),
    (r"\bKossuth\s+L\.", "Kossuth Lajos"),
    (r"\bBem\s+J\.", "Bem József"),
    (r"\bVarsányi\s+I\.", "Varsányi Irén"),
    (r"\bSzigeti\s+J\.", "Szigeti József"),
    (r"\bRadnóti\s+M\.", "Radnóti Miklós"),
    (r"\bRegele\s+J\.", "Regele János"),
    (r"\bPeregi\s+u\.", "Peregi utca"),
    (r"\bBajcsy\s+Zs\.", "Bajcsy-Zsilinszky"),
    (r"\bKosztolányi\s+D\.", "Kosztolányi Dezső"),
    (r"\bGulner\s+Gy\.", "Gulner Gyula"),
    (r"\bReviczky\s+Gy\.", "Reviczky Gyula"),
    (r"\bKondor\s+B\.", "Kondor Béla"),
    (r"\bWlassics\s+Gy\.", "Wlassics Gyula"),
    (r"\bBókay\s+Á\.", "Bókay Árpád"),
    (r"\bAdy\s+E\.", "Ady Endre"),
    (r"\bKatona\s+J\.", "Katona József"),
    (r"\bTáncsics\s+M\.", "Táncsics Mihály"),
    (r"\bCsete\s+B\.", "Csete Balázs"),
    (r"\bMészáros\s+J\.", "Mészáros József"),
    (r"\bSimon\s+B\.", "Simon Bolivár"),
    (r"\bTichy\s+L\.", "Tichy Lajos"),

    (r"\bBencze\s+J\.", "Bencze József"),
    (r"\bTörök\s+I\.", "Török István"),
    (r"\bDobó\s+I\.", "Dobó István"),
    (r"\bKodály\s+Z\.", "Kodály Zoltán"),
    (r"\bZsolnay\s+V\.", "Zsolnay Vilmos"),
    (r"\bMajorossy\s+I\.", "Majorossy Imre"),
    (r"\bMikszáth\s+K\.", "Mikszáth Kálmán"),
    (r"\bJurisics\s+M\.", "Jurisics Miklós"),
    (r"\bPetőfi\s+S\.", "Petőfi Sándor"),
    (r"\bVeress\s+E\.", "Veress Endre"),
    (r"\bBabits\s+M\.", "Babits Mihály"),
    (r"\bEsztergár\s+L\.", "Esztergár Lajos"),
    (r"\bBánki\s+D\.", "Bánki Donát"),
    (r"\bPázmány\s+P\.", "Pázmány Péter"),
    (r"\bFábián\s+B\.", "Fábián Béla"),
    (r"\bLittke\s+J\.", "Littke József"),
    (r"\bVárkonyi\s+N\.", "Várkonyi Nándor"),
    (r"\bAidinger\s+J\.", "Aidinger János"),
    (r"\bLovász\s+P\.", "Lovász Pál"),

    (r"\bVörösmarty\s+M\.", "Vörösmarty Mihály"),
    (r"\bSzilágyi\s+D\.", "Szilágyi Dezső"),
    (r"\bHajós\s+A\.", "Hajós Alfréd"),
    (r"\bGörgey\s+A\.", "Görgey Artúr"),
    (r"\bSzigethy\s+M\.", "Szigethy Mihály"),
    (r"\bBársony\s+J\.", "Bársony János"),
    (r"\bHerman\s+O\.", "Herman Ottó"),
    (r"\bKálvin\s+J\.", "Kálvin János"),
    (r"\bRácz\s+Á\.", "Rácz Ádám"),
    (r"\bKönyves\s+K\.", "Könyves Kálmán"),
    (r"\bBolyai\s+F\.", "Bolyai Farkas"),
    (r"\bMóra\s+F\.", "Móra Ferenc"),
    (r"\bCsáky\s+J\.", "Csáky József"),
    (r"\bJózsef\s+A\.", "József Attila"),
    (r"\bTisza\s+L\.", "Tisza Lajos"),
    (r"\bDeák\s+F\.", "Deák Ferenc"),
    (r"\bZipernowsky\s+Károly", "Zipernowsky Károly"),
    (r"\bIrinyi\s+út", "Irinyi út"),
]


def budapest_kerulet(telepules) -> int | None:
    s = tisztit_szoveg(telepules)
    if not s.lower().startswith("budapest"):
        return None
    rest = s[len("Budapest"):].strip().replace(".", "")
    if not rest:
        return None
    rest = rest.upper()
    if rest in BUDAPEST_ROMAI:
        return BUDAPEST_ROMAI[rest]
    m = re.search(r"\d+", rest)
    if m:
        return int(m.group(0))
    return None


def rovid_nevek_kibontasa(s: str) -> str:
    """Utcanevekben lévő 'Kossuth L.' típusú rövidítések kibontása."""
    s = tisztit_szoveg(s)
    # N.K.u. / Cs.J.KRT. jellegű összetapadások.
    s = re.sub(r"(?<=[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])\.(?=[A-ZÁÉÍÓÖŐÚÜŰ])", ". ", s)
    s = re.sub(r"(?<=[IVXLCDM])\.(?=[A-ZÁÉÍÓÖŐÚÜŰ])", ". ", s)
    for pat, repl in UTCA_NEV_ROVIDITESEK:
        s = re.sub(pat, repl, s, flags=re.I)
    # Ha a rövidítés után közterület jött
    s = re.sub(r"([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])(?=(?:u|krt|kt|sgt|rkp|stny|tr)\.)", r"\1 ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def cim_tisztitas(cim) -> str:

    #Címtisztítás Nominatimhoz

    s = tisztit_szoveg(cim)
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = s.replace(";", " ").replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()

    # Intézménynév és megjegyzés le. (vagy zárójel nélküli /-es megjegyzés)
    s = re.sub(r"\s*\(.*", "", s).strip()
    s = re.sub(r"\s+/\s*.*$", "", s).strip()
    s = re.sub(r"\.\s*/.*$", "", s).strip()


    s = re.sub(r"\b(?:magasföldszint|magasfoldszint|földszint|foldszint|fszt|fsz|em|emelet|ajtó|ajto|terem|ebédlő|ebedlo|helyiség|helyiseg)\b.*$", "", s, flags=re.I).strip()

    s = rovid_nevek_kibontasa(s)

    s = re.sub(r"\b(?:atb|altb)\.?\s*u\.?\s*", "altábornagy utca ", s, flags=re.I)
    s = re.sub(r"\b(?:atb|altb)\.?\s*(?=\d)", "altábornagy utca ", s, flags=re.I)
    s = re.sub(r"\b(?:atb|altb)\.?", "altábornagy ", s, flags=re.I)
    s = s.replace("altábornagy.", "altábornagy")

    s = re.sub(r"altábornagy\s*(?=\d)", "altábornagy utca ", s, flags=re.I)

    # Közterület-típus rövidítések.
    s = re.sub(r"\bkrt\.?\s*", "körút ", s, flags=re.I)
    s = re.sub(r"\bkt\.?\s*", "körút ", s, flags=re.I)
    s = re.sub(r"\bsgt\.?\s*", "sugárút ", s, flags=re.I)
    s = re.sub(r"\brkp\.?\s*", "rakpart ", s, flags=re.I)
    s = re.sub(r"\bstny\.?\s*", "sétány ", s, flags=re.I)
    s = re.sub(r"\bltp\.?\s*", "lakótelep ", s, flags=re.I)
    s = re.sub(r"\blakótelepi\b", "lakótelep", s, flags=re.I)

    tipusok = [
        (r"\bu\.\s*", "utca "),
        (r"\bu\s+", "utca "),
        (r"\butc\.\s*", "utca "),
        (r"\bsét\.\s*", "sétány "),
        (r"\bset\.\s*", "sétány "),
        (r"\btr\.?\s*", "tér "),
    ]
    for pat, repl in tipusok:
        s = re.sub(pat, repl, s, flags=re.I)

    if re.search(r"lakótelep", s, flags=re.I):
        s = re.sub(r"\s+(óvoda|iskola|gimnázium|technikum|központ).*$", "", s, flags=re.I).strip()

    # Ha a közterület után rögtön szám jön, legyen szóköz.
    kozter = r"utca|út|körút|sugárút|rakpart|sétány|tér|köz|park|lakótelep|sor|dűlő|tanya"
    s = re.sub(rf"\b({kozter})\.?\s*(?=\d)", r"\1 ", s, flags=re.I)

    # Irányítószám/adatfájlok néha '1.D.ÉP.' jellegű épületkód.
    s = re.sub(r"\s+", " ", s).strip(" .,/;:")
    return s


def utca_hazszam(cim) -> tuple[str, str]:
    #'Úri utca 38.' -> ('Úri utca', '38')
    s = cim_tisztitas(cim)
    kozter = r"utca|útja|út|körút|sugárút|rakpart|sétány|tér|tere|köz|park|lakótelep|sor|dűlő|tanya"

    # Normál eset: van közterület.
    pat1 = rf"^(?P<utca>.*?\b(?:{kozter})\b)\s*\.?\s*(?P<haz>\d+\s*(?:[-/]\s*\d+)?\s*(?:[/]?[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])?)\b"
    m = re.search(pat1, s, flags=re.I)
    if m:
        utca = m.group("utca").strip(" .,")
        haz = re.sub(r"\s+", "", m.group("haz").strip(" .,"))
        return utca, haz

    # Tanya / városrész jellegű cím
    m = re.search(r"^(?P<utca>.*?\D)\s*(?P<haz>\d+\s*(?:[-/]\s*\d+)?\s*(?:[/]?[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])?)\b", s, flags=re.I)
    if m:
        utca = m.group("utca").strip(" .,")
        haz = re.sub(r"\s+", "", m.group("haz").strip(" .,"))
        return utca, haz

    return s, ""


def hazszam_variaciok(haz: str) -> list[str]:
    """33/b -> 33/b és 33; 88-90 -> 88-90 és 88."""
    haz = tisztit_szoveg(haz).replace(" ", "").strip(" .,")
    if not haz:
        return []
    out = [haz]
    # Tartomány első házszáma.
    m = re.match(r"(\d+)[-–—](\d+)", haz)
    if m:
        out.append(m.group(1))
    # Betű/szint nélkül
    m = re.match(r"(\d+)", haz)
    if m:
        out.append(m.group(1))
    # 1/b -> 1/B
    m = re.match(r"(\d+)/(\w)", haz, flags=re.I)
    if m:
        out.append(f"{m.group(1)}/{m.group(2).upper()}")
    seen = set()
    res = []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            res.append(x)
    return res


def utca_variaciok(utca: str) -> list[str]:
    utca = tisztit_szoveg(utca).strip(" .,")
    if not utca:
        return []
    out = [utca]
    out.append(utca.replace("-", " "))
    out.append(utca.replace("Bajcsy Zsilinszky", "Bajcsy-Zsilinszky"))
    out.append(utca.replace("Bajcsy-Zsilinszky", "Bajcsy Zsilinszky"))
    # Néha a hivatalos név utca/út eltér
    if re.search(r"\butca$", utca, flags=re.I):
        out.append(re.sub(r"\butca$", "út", utca, flags=re.I))
    if re.search(r"\bút$", utca, flags=re.I):
        out.append(re.sub(r"\bút$", "utca", utca, flags=re.I))
    if utca.lower().startswith("ii. rákóczi"):
        out.append(re.sub(r"^II\.\s*", "", utca, flags=re.I))

    # Teljes név -> csak vezetéknév fallback.
    kozter2 = r"utca|útja|út|körút|sugárút|rakpart|sétány|tér|tere|köz|park|lakótelep|sor|dűlő|tanya"
    m = re.match(rf"^([A-ZÁÉÍÓÖŐÚÜŰ][A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű\-]+)\s+[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+\s+(.*\b(?:{kozter2})\b)$", utca, flags=re.I)
    if m:
        out.append(f"{m.group(1)} {m.group(2)}")

    seen = set()
    res = []
    for x in out:
        x = re.sub(r"\s+", " ", x).strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            res.append(x)
    return res




def intezmeny_nevek(cim) -> list[str]:
    #Ha az utcacímet nem találja, néha az intézmény nevét megtalálja.
    eredeti = tisztit_szoveg(cim)
    out = []

    # Zárójeles intézménynév.
    for m in re.finditer(r"\((.*?)\)", eredeti):
        nev = tisztit_szoveg(m.group(1))
        if nev:
            out.append(nev)

    # Perjeles megjegyzés: pl Belgrád rakpart 27 / Idősek Klubja.
    # Fontos: a 38/a házszámot ne vágjuk ketté.
    m_slash = re.search(r"(?:\s+/\s*|\.\s*/\s*)(.+)$", eredeti)
    if m_slash:
        after = tisztit_szoveg(m_slash.group(1))
        if after:
            out.append(after)

    res = []
    seen = set()
    for nev in out:
        nev = rovid_nevek_kibontasa(nev)
        jav = nev
        jav = re.sub(r"\bÁlt\.?\s*Isk\.?\b", "Általános Iskola", jav, flags=re.I)
        jav = re.sub(r"\bÁltalános\s+Isk\.?\b", "Általános Iskola", jav, flags=re.I)
        jav = re.sub(r"\bGimn\.?\b", "Gimnázium", jav, flags=re.I)
        jav = re.sub(r"\bSzakgimn\.?\b", "Szakgimnázium", jav, flags=re.I)
        jav = re.sub(r"\bSzakkép\.?\s*I\.?\b", "Szakképző Iskola", jav, flags=re.I)
        jav = re.sub(r"\bRef\.?", "Református", jav, flags=re.I)
        jav = re.sub(r"\bRóm\.?\s*Kat\.?", "Római Katolikus", jav, flags=re.I)
        jav = jav.replace("Református.", "Református")
        jav = jav.replace("Római Katolikus.", "Római Katolikus")
        jav = re.sub(r"\bMc-i\b", "Miskolci", jav, flags=re.I)
        jav = re.sub(r"\s+", " ", jav).strip(" .,/;:")
        for x in [jav, nev]:
            x = tisztit_szoveg(x).strip(" .,/;:")
            if x and x.lower() not in seen:
                seen.add(x.lower())
                res.append(x)
    return res

def cim_variaciok(telepules, telepules_csoport, cim, pir="") -> list[dict]:
    cim_full = cim_tisztitas(cim)
    utca, haz = utca_hazszam(cim)
    pir = kod(pir, 4) if tisztit_szoveg(pir) else ""

    eredeti_telepules = tisztit_szoveg(telepules)
    csoport = tisztit_szoveg(telepules_csoport) or norm_varos(telepules)
    ker = budapest_kerulet(telepules)

    bp = csoport.lower() == "budapest" or eredeti_telepules.lower().startswith("budapest")

    helyek = []
    if bp:
        if ker:
            roman = next((r for r, n in BUDAPEST_ROMAI.items() if n == ker), str(ker))
            helyek += [
                f"Budapest {roman}. kerület",
                f"Budapest {ker}. kerület",
                f"Budapest, {roman}. kerület",
                f"Budapest, {ker}. kerület",
            ]
        if eredeti_telepules:
            helyek.append(eredeti_telepules)
        helyek.append("Budapest")
    else:
        if eredeti_telepules:
            helyek.append(eredeti_telepules)
        if csoport and csoport not in helyek:
            helyek.append(csoport)

    # Duplikált helyek ki.
    tmp = []
    seen_hely = set()
    for h in helyek:
        if h and h.lower() not in seen_hely:
            seen_hely.add(h.lower())
            tmp.append(h)
    helyek = tmp

    street_candidates = []
    if utca and haz:
        for u in utca_variaciok(utca):
            for hsz in hazszam_variaciok(haz):
                street_candidates.append(f"{u} {hsz}")
    if cim_full:
        street_candidates.append(cim_full)
    if utca:
        for u in utca_variaciok(utca):
            street_candidates.append(u)

    # Duplikált címek ki.
    tmp = []
    seen_street = set()
    for s in street_candidates:
        s = re.sub(r"\s+", " ", tisztit_szoveg(s)).strip(" .,")
        if s and s.lower() not in seen_street:
            seen_street.add(s.lower())
            tmp.append(s)
    street_candidates = tmp

    probak = []

    def add_query(q, note=""):
        q = tisztit_szoveg(q)
        if q:
            probak.append({"query": q, "kwargs": {"country_codes": "hu", "exactly_one": True}, "note": note or q})

    def add_struct(street, city, postalcode=""):
        street = tisztit_szoveg(street)
        city = tisztit_szoveg(city)
        if not street or not city:
            return
        q = {"street": street, "city": city, "country": "Hungary"}
        if postalcode:
            q["postalcode"] = postalcode
        probak.append({"query": q, "kwargs": {"country_codes": "hu", "exactly_one": True}, "note": f"structured: {q}"})

    # Strukturált query-k előre.
    for street in street_candidates:
        if bp:
            add_struct(street, "Budapest", pir)
            add_struct(street, "Budapest", "")
        else:
            add_struct(street, csoport or eredeti_telepules, pir)
            add_struct(street, csoport or eredeti_telepules, "")

    # Szöveges query-k.
    for street in street_candidates:
        for h in helyek:
            if pir:
                add_query(f"{pir} {h}, {street}, Magyarország", "pir+hely+cím")
            add_query(f"{h}, {street}, Magyarország", "hely+cím")
        if bp and pir:
            add_query(f"{street}, {pir} Budapest, Magyarország", "cím+pir+bp")
        elif pir:
            add_query(f"{street}, {pir} {csoport or eredeti_telepules}, Magyarország", "cím+pir+város")

    # Intézmény fallback.
    for inst in intezmeny_nevek(cim):
        for h in helyek:
            if pir:
                add_query(f"{pir} {h}, {inst}, Magyarország", "intézmény fallback")
            add_query(f"{h}, {inst}, Magyarország", "intézmény fallback")
        if bp:
            add_query(f"Budapest, {inst}, Magyarország", "intézmény fallback")
        elif csoport or eredeti_telepules:
            add_query(f"{csoport or eredeti_telepules}, {inst}, Magyarország", "intézmény fallback")

    # Duplikátumok ki.
    seen = set()
    out = []
    for p in probak:
        key = json.dumps(p["query"], ensure_ascii=False, sort_keys=True).lower() if isinstance(p["query"], dict) else str(p["query"]).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out

def geocode_probalkozas(geocode, proba: dict):
    #Egyetlen geokód próba.
    try:
        return geocode(proba["query"], **proba.get("kwargs", {}))
    except TypeError:
        return geocode(proba["query"])
    except Exception:
        return None


def olvas_manual_geocode(path: Path) -> dict[str, tuple[float, float]]:
    """
    Opcionális kézi javító fájl:
        cache/manual_geocode.csv
    oszlopok:
        cache_key,latitude,longitude
    """
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str)
    if not {"cache_key", "latitude", "longitude"}.issubset(df.columns):
        return {}
    out = {}
    for r in df.itertuples(index=False):
        try:
            out[str(r.cache_key)] = (float(r.latitude), float(r.longitude))
        except Exception:
            pass
    return out


def geocode_szavazokorok(df: pd.DataFrame, cache_path: Path, no_geocode: bool, sleep_sec: float) -> pd.DataFrame:
    #Csak a 9 kijelölt város
    out = df.copy()
    out["telepules_csoport"] = out["telepules"].map(norm_varos)
    if "pir" not in out.columns:
        out["pir"] = out["iranyitoszam"] if "iranyitoszam" in out.columns else ""
    if "iranyitoszam" not in out.columns:
        out["iranyitoszam"] = out["pir"]
    if "telepules_kod" not in out.columns:
        out["telepules_kod"] = ""

    out["cache_key"] = (
        out["telepules"].map(tisztit_szoveg) + "|" +
        out["telepules_kod"].map(lambda x: kod(x, 3)) + "|" +
        out["telepules_csoport"].map(tisztit_szoveg) + "|" +
        out["pir"].map(lambda x: kod(x, 4)) + "|" +
        out["szavazokor_cim"].map(tisztit_szoveg)
    )

    cache = olvas_cache(cache_path)
    cache_map = {r.cache_key: r for r in cache.itertuples(index=False)}
    manual = olvas_manual_geocode(cache_path.parent / "manual_geocode.csv")

    kell = out[out["telepules_csoport"].map(kell_voronoi)].drop_duplicates("cache_key").copy()
    print(f"Geokódolandó szavazóköri cím a 9 helyen: {len(kell):,}")

    if no_geocode:
        print("  --no-geocode be van kapcsolva, csak cache-t használok.")
    else:
        from geopy.extra.rate_limiter import RateLimiter
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="valasztas2026_basic_pipeline_budapest_fix", timeout=15)
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=sleep_sec, swallow_exceptions=True)

        uj = []
        for n, row in enumerate(kell.itertuples(index=False), start=1):
            key = row.cache_key

            if key in manual:
                lat, lon = manual[key]
                uj.append({"cache_key": key, "latitude": lat, "longitude": lon, "talalat": "manual"})
                continue

            if key in cache_map and pd.notna(getattr(cache_map[key], "latitude", None)):
                continue

            lat = lon = None
            talalat = ""
            pir = getattr(row, "pir", "")

            for proba in cim_variaciok(row.telepules, row.telepules_csoport, row.szavazokor_cim, pir=pir):
                loc = geocode_probalkozas(geocode, proba)
                if loc:
                    lat, lon = loc.latitude, loc.longitude
                    talalat = proba.get("note", str(proba.get("query", "")))
                    break

            uj.append({
                "cache_key": key,
                "latitude": lat if lat is not None else "",
                "longitude": lon if lon is not None else "",
                "talalat": talalat,
            })

            if n % 20 == 0:
                cache_tmp = pd.concat([cache, pd.DataFrame(uj)], ignore_index=True)
                ment_cache(cache_tmp, cache_path)
                print(f"  {n:,}/{len(kell):,} cím feldolgozva")

        if uj:
            cache = pd.concat([cache, pd.DataFrame(uj)], ignore_index=True)
            ment_cache(cache, cache_path)

    cache = olvas_cache(cache_path)
    out = out.merge(cache[["cache_key", "latitude", "longitude", "talalat"]], on="cache_key", how="left")

    hiany = out[out["telepules_csoport"].map(kell_voronoi) & (out["latitude"].isna() | (out["latitude"].astype(str) == ""))].copy()
    if not hiany.empty:
        hibak_path = cache_path.parent / "geocode_hianyzo_szavazokorok.csv"
        hiany[["cache_key", "telepules", "pir", "szavazokor_cim"]].drop_duplicates().to_csv(hibak_path, index=False, encoding="utf-8-sig")
        print(f"  Hiányzó címek külön mentve: {hibak_path}")
        print("  Ezeket kézzel javíthatod a cache/manual_geocode.csv fájlban.")

    return out


def geocode_telepulesek(telep_df: pd.DataFrame, cache_path: Path, no_geocode: bool, sleep_sec: float) -> pd.DataFrame:
    inp = telep_df[["telepules_key", "telepules_csoport", "varmegye"]].drop_duplicates().copy()
    inp["cache_key"] = inp["telepules_key"].astype(str)

    cache = olvas_cache(cache_path)
    cache_map = {r.cache_key: r for r in cache.itertuples(index=False)}

    print(f"Geokódolandó településközpont: {len(inp):,}")

    if no_geocode:
        print("  --no-geocode be van kapcsolva, csak település-cache-t használok.")
    else:
        from geopy.extra.rate_limiter import RateLimiter
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="valasztas2026_basic_telepulesek", timeout=12)
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=sleep_sec, swallow_exceptions=True)

        uj = []
        for n, row in enumerate(inp.itertuples(index=False), start=1):
            key = row.cache_key
            if key in cache_map and pd.notna(getattr(cache_map[key], "latitude", None)):
                continue

            q1 = f"{row.telepules_csoport}, {row.varmegye}, Magyarország"
            q2 = f"{row.telepules_csoport}, Magyarország"
            lat = lon = None
            talalat = ""

            for q in [q1, q2]:
                loc = geocode(q)
                if loc:
                    lat, lon, talalat = loc.latitude, loc.longitude, q
                    break

            uj.append({
                "cache_key": key,
                "latitude": lat if lat is not None else "",
                "longitude": lon if lon is not None else "",
                "talalat": talalat,
            })

            if n % 50 == 0:
                cache_tmp = pd.concat([cache, pd.DataFrame(uj)], ignore_index=True)
                ment_cache(cache_tmp, cache_path)
                print(f"  {n:,}/{len(inp):,} település feldolgozva")

        if uj:
            cache = pd.concat([cache, pd.DataFrame(uj)], ignore_index=True)
            ment_cache(cache, cache_path)

    cache = olvas_cache(cache_path)
    out = inp.merge(cache, on="cache_key", how="left")
    return out


# Településhatárok és cellák

# Ezeket nem szabad ékezet nélkül ugyanannak venni.
SPECIALIS_TELEPULES_KULCSOK = {
    "komló": "komlo_baranya",
    "kömlő": "komlo_tiszamente",
    "komoró": "komoro_szabolcs",
    "kömörő": "komoro_szabolcs_szatmar",
}


def admin_nev_kulcs(nev) -> str:
    s = tisztit_szoveg(nev)
    if not s:
        return ""

    if s.lower().startswith("budapest"):
        return "budapest"

    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\b(nagyközség|község|város|megyei jogú város|kerület)\b", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,.;:-")

    # Itt még megvan az ékezet.
    special_key = SPECIALIS_TELEPULES_KULCSOK.get(s.lower())
    if special_key:
        return special_key

    return slug(s, 120)


def admin_nev_oszlop(gdf: gpd.GeoDataFrame) -> str | None:
    #Megkeresi, melyik admin8 oszlop lehet a településnév.

    if gdf.empty:
        return None

    biztos_nevek = {
        "name", "name_hu", "nev", "név", "telepules", "település", "telepulesn",
        "localname", "settlement", "municipali", "municipality", "admin_name",
    }

    best_col = None
    best_score = -1
    celok = {admin_nev_kulcs(v) for v in VORONOI_VAROSOK}

    for col in gdf.columns:
        if col == "geometry":
            continue
        ser = gdf[col]
        # A shapefile DBF oszlopnevek néha rövidülnek, ezért slugosítva nézzük.
        col_key = slug(col, 80)

        vals = ser.dropna().astype(str).map(tisztit_szoveg)
        vals = vals[vals != ""]
        if vals.empty:
            continue

        # Kódszerű / szám mezők kizárása.
        alpha_ratio = vals.map(lambda x: bool(re.search(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]", x))).mean()
        if alpha_ratio < 0.6:
            continue

        keys = vals.map(admin_nev_kulcs)
        unique_n = keys.nunique()
        target_hits = len(set(keys) & celok)

        score = unique_n + target_hits * 1000
        if col_key in biztos_nevek or col_key.startswith("name") or "telep" in col_key:
            score += 500

        # Ha túl kevés különböző érték van, az inkább megye/régió, nem település.
        if unique_n < max(20, len(gdf) * 0.1):
            score -= 300

        if score > best_score:
            best_score = score
            best_col = col

    return best_col


def geom_union(geoms):
    """Shapely/geopandas verziófüggetlen union."""
    try:
        return geoms.union_all()
    except Exception:
        return geoms.unary_union


def load_admin8(path: Path) -> gpd.GeoDataFrame:
    os.environ["SHAPE_RESTORE_SHX"] = "YES"
    gdf = gpd.read_file(path)

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=ADMIN8_ALAP_CRS)
    gdf = gdf.to_crs(epsg=METERES_CRS)

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf.geometry.map(lambda geom: make_valid(geom) if geom is not None and not geom.is_valid else geom)
    gdf["geometry"] = gdf.geometry.buffer(0)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    #DFB megoldja a településnevet, de már ki nem veszem a geokódot, fallbacknek jó.
    name_col = admin_nev_oszlop(gdf)
    if name_col:
        print(f"Admin8 névoszlop: {name_col} -> település-poligon kötés geokód nélkül")
        gdf["admin_nev"] = gdf[name_col].map(tisztit_szoveg)
        gdf["_admin_norm"] = gdf["admin_nev"].map(admin_nev_kulcs)
        gdf = gdf[gdf["_admin_norm"] != ""].copy()

        rows = []
        for key, part in gdf.groupby("_admin_norm", dropna=False):
            rows.append({
                "_admin_norm": key,
                "admin_nev": part["admin_nev"].dropna().astype(str).iloc[0],
                "geometry": geom_union(part.geometry),
            })
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{METERES_CRS}")
        gdf["geometry"] = gdf.geometry.map(lambda geom: make_valid(geom) if geom is not None and not geom.is_valid else geom)
        gdf["geometry"] = gdf.geometry.buffer(0)
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
        print(f"Admin8 név alapján összevonva: {len(gdf):,} településpoligon")
    else:
        print("Admin8-ban nem találtam használható településnév oszlopot; település-geokód fallback marad.")

    gdf["poly_id"] = [f"P{str(i).zfill(5)}" for i in range(len(gdf))]
    return gdf[["poly_id", "geometry"] + [c for c in gdf.columns if c not in {"poly_id", "geometry"}]]

def telepules_osszefoglalas(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.copy()
    tmp["telepules_csoport"] = tmp["telepules"].map(norm_varos)

    # Budapest kerületeit egy kulcsra hozzuk.
    tmp["telepules_key"] = tmp["varmegye_kod"].astype(str).str.zfill(2) + "-" + tmp["telepules_kod"].astype(str).str.zfill(3)
    tmp.loc[tmp["telepules_csoport"].map(egyszeru_norm) == "budapest", "telepules_key"] = "01-BUDAPEST"

    sum_cols = osszeg_oszlopok(tmp)
    for c in sum_cols:
        tmp[c] = pd.to_numeric(tmp[c], errors="coerce").fillna(0)

    rows = []
    for key, part in tmp.groupby("telepules_key", dropna=False):
        sor = {}
        sor["telepules_key"] = key
        sor["telepules_csoport"] = part["telepules_csoport"].iloc[0]
        sor["telepules"] = part["telepules_csoport"].iloc[0]
        sor["varmegye"] = part["varmegye"].iloc[0] if "varmegye" in part.columns else ""
        sor["varmegye_kod"] = part["varmegye_kod"].iloc[0] if "varmegye_kod" in part.columns else ""
        sor["oevk_lista"] = ";".join(sorted(part["oevk_id"].dropna().astype(str).unique())) if "oevk_id" in part.columns else ""
        sor["oevk_id"] = part["oevk_id"].dropna().astype(str).mode().iloc[0] if "oevk_id" in part.columns and part["oevk_id"].notna().any() else ""
        sor["szavazokor_ids"] = ";".join(sorted(part["szavazokor_id"].dropna().astype(str).unique()))
        sor["szavazokor_db"] = part["szavazokor_id"].nunique()
        sor["szavazokor_cim"] = "egész település"
        sor["egyseg_tipus"] = "telepules"
        sor["hely_id"] = "telepules|" + slug(str(key) + "_" + sor["telepules_csoport"])
        for c in sum_cols:
            sor[c] = part[c].sum()
        rows.append(sor)

    out = pd.DataFrame(rows)
    out = ujraszamol_szazalekok(out)
    return out


def telepules_polygon_map(telep_df: pd.DataFrame, admin: gpd.GeoDataFrame, cache_dir: Path, no_geocode: bool, sleep_sec: float) -> pd.DataFrame:
    """
    Település -> admin8 polygon.
    Ha az admin8 DBF-ben van településnév, akkor név alapján.
    Geokódolás csak fallback.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    map_path = cache_dir / "telepules_polygon_map.csv"

    #admin8.dbf-ben van név
    if "_admin_norm" in admin.columns:
        print("Település-polygon kapcsolat: admin8 DBF név alapján, település-geokódolás nélkül.")
        base = telep_df[["telepules_key", "telepules_csoport", "varmegye"]].drop_duplicates().copy()
        base["_admin_norm"] = base["telepules_csoport"].map(admin_nev_kulcs)

        lookup = admin[["_admin_norm", "poly_id"]].drop_duplicates("_admin_norm").copy()
        out = base.merge(lookup, on="_admin_norm", how="left")
        out["map_mod"] = "nev"

        hiany = out[out["poly_id"].isna()].copy()
        if not hiany.empty:
            print(f"  Név alapján nem talált település: {len(hiany):,}. Ezekre fallback mehet.")
            (cache_dir / "hianyzo_telepules_nev_alapjan.csv").parent.mkdir(parents=True, exist_ok=True)
            hiany[["telepules_key", "telepules_csoport", "varmegye", "_admin_norm"]].to_csv(
                cache_dir / "hianyzo_telepules_nev_alapjan.csv",
                index=False,
                encoding="utf-8-sig",
            )

            if not no_geocode:
                print("  Csak a hiányzó településeket geokódolom fallbackként.")
                geo = geocode_telepulesek(hiany, cache_dir / "telepules_geocode.csv", no_geocode, sleep_sec)
                geo["latitude"] = pd.to_numeric(geo["latitude"], errors="coerce")
                geo["longitude"] = pd.to_numeric(geo["longitude"], errors="coerce")
                geo = geo.dropna(subset=["latitude", "longitude"]).copy()

                if not geo.empty:
                    pts = gpd.GeoDataFrame(
                        geo,
                        geometry=gpd.points_from_xy(geo["longitude"], geo["latitude"]),
                        crs=f"EPSG:{WGS84}",
                    ).to_crs(epsg=METERES_CRS)
                    joined = gpd.sjoin(pts, admin[["poly_id", "geometry"]], how="left", predicate="within")
                    joined = joined.drop(columns=["geometry", "index_right"], errors="ignore")
                    joined = joined[["telepules_key", "poly_id"]].dropna().drop_duplicates("telepules_key")

                    # A hiányzó poly_id-k pótlása a fallbackből.
                    fill = joined.set_index("telepules_key")["poly_id"].to_dict()
                    mask = out["poly_id"].isna()
                    out.loc[mask, "poly_id"] = out.loc[mask, "telepules_key"].map(fill)
                    out.loc[mask & out["poly_id"].notna(), "map_mod"] = "nev+geocode_fallback"

        out[["telepules_key", "telepules_csoport", "varmegye", "poly_id", "map_mod"]].to_csv(
            map_path,
            index=False,
            encoding="utf-8-sig",
        )
        return out[["telepules_key", "telepules_csoport", "varmegye", "poly_id", "map_mod"]]

    # Régi fallback: ha tényleg nincs DBF/név, akkor cache vagy település-geokód.
    if map_path.exists():
        print("Település-polygon kapcsolat cache-ből.")
        return pd.read_csv(map_path, dtype=str)

    geo = geocode_telepulesek(telep_df, cache_dir / "telepules_geocode.csv", no_geocode, sleep_sec)
    geo["latitude"] = pd.to_numeric(geo["latitude"], errors="coerce")
    geo["longitude"] = pd.to_numeric(geo["longitude"], errors="coerce")
    geo = geo.dropna(subset=["latitude", "longitude"]).copy()

    if geo.empty:
        raise RuntimeError("Nincs geokódolt településközpont. Cache vagy admin8 DBF névmező kell.")

    pts = gpd.GeoDataFrame(
        geo,
        geometry=gpd.points_from_xy(geo["longitude"], geo["latitude"]),
        crs=f"EPSG:{WGS84}",
    ).to_crs(epsg=METERES_CRS)

    joined = gpd.sjoin(pts, admin[["poly_id", "geometry"]], how="left", predicate="within")
    joined = joined.drop(columns=["geometry", "index_right"], errors="ignore")
    joined["map_mod"] = "geocode"
    joined[["telepules_key", "telepules_csoport", "varmegye", "poly_id", "map_mod"]].to_csv(map_path, index=False, encoding="utf-8-sig")
    return joined[["telepules_key", "telepules_csoport", "varmegye", "poly_id", "map_mod"]]

def pontok_voronoihoz(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df[df["telepules"].map(kell_voronoi)].copy()
    tmp["latitude"] = pd.to_numeric(tmp["latitude"], errors="coerce")
    tmp["longitude"] = pd.to_numeric(tmp["longitude"], errors="coerce")
    tmp = tmp.dropna(subset=["latitude", "longitude"]).copy()
    tmp["telepules_csoport"] = tmp["telepules"].map(norm_varos)

    if tmp.empty:
        return pd.DataFrame()

    if "pir" not in tmp.columns:
        tmp["pir"] = ""
    tmp["cim_key"] = (
        tmp["telepules"].map(tisztit_szoveg) + "|" +
        tmp["telepules_csoport"].map(tisztit_szoveg) + "|" +
        tmp["pir"].map(tisztit_szoveg) + "|" +
        tmp["szavazokor_cim"].map(tisztit_szoveg)
    )
    sum_cols = osszeg_oszlopok(tmp)
    for c in sum_cols:
        tmp[c] = pd.to_numeric(tmp[c], errors="coerce").fillna(0)

    rows = []
    for key, part in tmp.groupby("cim_key", dropna=False):
        sor = {}
        sor["hely_id"] = "hely|" + slug(key, 120)
        sor["telepules_csoport"] = part["telepules_csoport"].iloc[0]
        sor["telepules"] = part["telepules_csoport"].iloc[0]
        sor["varmegye"] = part["varmegye"].iloc[0]
        sor["varmegye_kod"] = part["varmegye_kod"].iloc[0]
        sor["oevk_lista"] = ";".join(sorted(part["oevk_id"].dropna().astype(str).unique())) if "oevk_id" in part.columns else ""
        sor["oevk_id"] = part["oevk_id"].dropna().astype(str).mode().iloc[0] if "oevk_id" in part.columns and part["oevk_id"].notna().any() else ""
        sor["szavazokor_ids"] = ";".join(sorted(part["szavazokor_id"].dropna().astype(str).unique()))
        sor["szavazokor_db"] = part["szavazokor_id"].nunique()
        sor["szavazokor_cim"] = part["szavazokor_cim"].iloc[0]
        sor["pir"] = part["pir"].iloc[0] if "pir" in part.columns else ""
        sor["latitude"] = pd.to_numeric(part["latitude"], errors="coerce").mean()
        sor["longitude"] = pd.to_numeric(part["longitude"], errors="coerce").mean()
        sor["egyseg_tipus"] = "voronoi"
        for c in sum_cols:
            sor[c] = part[c].sum()
        rows.append(sor)

    out = pd.DataFrame(rows)
    out = ujraszamol_szazalekok(out)
    return out


def make_voronoi_cells(points: gpd.GeoDataFrame, boundary_geom) -> gpd.GeoDataFrame | None:
    if points.empty:
        return None

    if len(points) == 1:
        one = points.drop(columns="geometry").iloc[[0]].copy()
        return gpd.GeoDataFrame(one, geometry=[boundary_geom], crs=points.crs)

    multi = MultiPoint(list(points.geometry))
    regions = voronoi_diagram(multi, envelope=boundary_geom.envelope.buffer(5000), edges=False)

    cells = gpd.GeoDataFrame(
        {"tmp_id": range(len(regions.geoms)), "geometry": list(regions.geoms)},
        crs=points.crs,
    )
    cells["geometry"] = cells.geometry.buffer(0)
    cells = cells[cells.geometry.notna() & ~cells.geometry.is_empty].copy()

    clipper = gpd.GeoDataFrame({"geometry": [boundary_geom]}, crs=points.crs)
    clipped = gpd.overlay(cells, clipper, how="intersection", keep_geom_type=True)
    clipped["geometry"] = clipped.geometry.buffer(0)
    clipped = clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty].copy()

    if clipped.empty:
        return None

    #amelyik pont a legközelebb van a cella belsejéhez.
    helyek = []
    for geom in clipped.geometry:
        rp = geom.representative_point()
        idx = points.distance(rp).idxmin()
        helyek.append(points.loc[idx, "hely_id"])
    clipped["hely_id"] = helyek

    # Ha egy cella több darabra szakadt.
    clipped = clipped.dissolve(by="hely_id", as_index=False)
    attrs = points.drop(columns="geometry")
    out = clipped.merge(attrs, on="hely_id", how="left")
    return out


def keszit_elemzesi_egysegek(merged: pd.DataFrame, admin: gpd.GeoDataFrame, cache_dir: Path, no_geocode: bool, sleep_sec: float) -> gpd.GeoDataFrame:
    print("Települési összesítés...")
    telep = telepules_osszefoglalas(merged)

    print("Települések polygonhoz kötése...")
    tmap = telepules_polygon_map(telep, admin, cache_dir, no_geocode, sleep_sec)
    telep = telep.merge(tmap[["telepules_key", "poly_id"]], on="telepules_key", how="left")

    hiany = telep[telep["poly_id"].isna()]
    if not hiany.empty:
        print(f"Figyelem: {len(hiany)} településhez nincs polygon. Ezek kimaradnak.")
        hiany.to_csv(cache_dir / "hianyzo_telepules_polygon.csv", index=False, encoding="utf-8-sig")

    telep = telep.dropna(subset=["poly_id"]).copy()

    # Nem Voronoi
    sima = telep[~telep["telepules_csoport"].map(kell_voronoi)].copy()
    sima_gdf = sima.merge(admin[["poly_id", "geometry"]], on="poly_id", how="left")
    sima_gdf = gpd.GeoDataFrame(sima_gdf, geometry="geometry", crs=admin.crs)
    sima_gdf = sima_gdf[sima_gdf.geometry.notna() & ~sima_gdf.geometry.is_empty].copy()

    # Voronoi
    pont_df = pontok_voronoihoz(merged)
    if pont_df.empty:
        pont_gdf = gpd.GeoDataFrame(columns=["hely_id", "telepules_csoport", "geometry"], geometry="geometry", crs=admin.crs)
    else:
        pont_gdf = gpd.GeoDataFrame(
            pont_df,
            geometry=gpd.points_from_xy(pont_df["longitude"], pont_df["latitude"]),
            crs=f"EPSG:{WGS84}",
        ).to_crs(epsg=METERES_CRS)

    voro_parts = []
    special = telep[telep["telepules_csoport"].map(kell_voronoi)].copy()

    for row in special.itertuples(index=False):
        varos = row.telepules_csoport
        hatar_df = admin[admin["poly_id"] == row.poly_id]
        if hatar_df.empty:
            continue

        hatar = hatar_df.geometry.iloc[0]
        pts = pont_gdf[pont_gdf["telepules_csoport"] == varos].copy()
        print(f"Voronoi: {varos} - {len(pts)} pont")

        cells = make_voronoi_cells(pts, hatar)
        if cells is None or cells.empty:
            # Ha nincs pont.
            fallback = pd.DataFrame([row._asdict()])
            fallback["egyseg_tipus"] = "telepules_fallback"
            cells = gpd.GeoDataFrame(fallback, geometry=[hatar], crs=admin.crs)

        cells["poly_id"] = row.poly_id
        cells["telepules_csoport"] = varos
        voro_parts.append(cells)

    pieces = []
    if not sima_gdf.empty:
        pieces.append(sima_gdf)
    for g in voro_parts:
        if g is not None and not g.empty:
            pieces.append(g)

    if not pieces:
        raise RuntimeError("Nem készült egyetlen cella sem.")

    out = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), geometry="geometry", crs=admin.crs)
    out["geometry"] = out.geometry.map(lambda geom: make_valid(geom) if geom is not None and not geom.is_valid else geom)
    out["geometry"] = out.geometry.buffer(0)
    out = out[out.geometry.notna() & ~out.geometry.is_empty].copy()
    out = ujraszamol_szazalekok(pd.DataFrame(out))
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=admin.crs)

    out["terulet_m2"] = out.geometry.area.round(1)
    out["kerulet_m"] = out.geometry.length.round(1)
    out["node_id"] = [f"N{str(i).zfill(6)}" for i in range(len(out))]

    return out


# Térképek

def color_for_party(party: str) -> str:
    p = (party or "").lower()
    if "fidesz" in p or "kdnp" in p:
        return "#f28e2b"
    if "tisza" in p:
        return "#4e79a7"
    if "mi haz" in p or "mi_haz" in p:
        return "#e15759"
    if "dk" in p:
        return "#9467bd"
    if "mkkp" in p or "kutya" in p:
        return "#59a14f"
    return "#9c755f"


def tooltip_cols(gdf: gpd.GeoDataFrame) -> list[str]:
    cols = [
        "telepules", "egyseg_tipus", "szavazokor_cim", "szavazokor_db",
        "gyoztes_lista", "gyoztes_arany_pct", "margin_pct",
        "reszvetel_pct", "fidesz_pct", "tisza_pct", "oevk_lista",
    ]
    return [c for c in cols if c in gdf.columns]


def pct_szoveg(x) -> str:
    #magyar vessző
    try:
        if pd.isna(x):
            return ""
        return f"{float(x):.1f}%".replace(".", ",")
    except Exception:
        return ""


def egesz_szoveg(x) -> str:
    try:
        if pd.isna(x):
            return ""
        return f"{int(round(float(x))):,}".replace(",", " ")
    except Exception:
        return ""


def part_nev_szepen(x) -> str:
    s = tisztit_szoveg(x)
    s = s.replace("lista_", "")
    s = s.replace("_", " ")
    return s.upper()


def szep_oevk_tooltip_oszlopok(oevk: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = oevk.copy()

    if "gyoztes_lista" in out.columns:
        out["gyoztes_lista_szep"] = out["gyoztes_lista"].map(part_nev_szepen)
    if "gyoztes_arany_pct" in out.columns:
        out["gyoztes_arany"] = out["gyoztes_arany_pct"].map(pct_szoveg)
    if "margin_pct" in out.columns:
        out["gyoztes_elony"] = out["margin_pct"].map(pct_szoveg)
    if "fidesz_pct" in out.columns:
        out["fidesz_arany"] = out["fidesz_pct"].map(pct_szoveg)
    if "tisza_pct" in out.columns:
        out["tisza_arany"] = out["tisza_pct"].map(pct_szoveg)
    if "fidesz_tisza_margin_pct" in out.columns:
        out["fidesz_tisza_margin"] = out["fidesz_tisza_margin_pct"].map(pct_szoveg)
    if "reszvetel_pct" in out.columns:
        out["reszvetel"] = out["reszvetel_pct"].map(pct_szoveg)

    for c in ["valasztopolgar", "megjelent", "ervenyes"]:
        if c in out.columns:
            out[c + "_szep"] = out[c].map(egesz_szoveg)

    return out



def make_oevk_boundaries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if "oevk_id" not in gdf.columns or gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs=gdf.crs)

    work = gdf.to_crs(epsg=METERES_CRS).copy()
    work = work[work["oevk_id"].notna() & (work["oevk_id"].astype(str) != "")].copy()
    if work.empty:
        return gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{METERES_CRS}")

    alap_sum_cols = [
        "valasztopolgar", "megjelent", "ervenytelen", "ervenyes",
        "fidesz_szavazat", "tisza_szavazat", "nem_fidesz_szavazat", "egyeb_szavazat",
        "osszes_partlista_szavazat",
    ]

    lista_cols = [
        c for c in work.columns
        if c.startswith("lista_") and not c.endswith("_pct") and c != "lista_sorszam"
    ]

    sum_cols = []
    for c in alap_sum_cols + lista_cols:
        if c in work.columns and c not in sum_cols:
            sum_cols.append(c)
            work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0)

    agg = {}
    for c in ["varmegye", "oevk_lista"]:
        if c in work.columns:
            agg[c] = "first"
    for c in sum_cols:
        agg[c] = "sum"

    oevk = work.dissolve(by="oevk_id", aggfunc=agg).reset_index()
    oevk["geometry"] = oevk.geometry.map(lambda geom: make_valid(geom) if geom is not None and not geom.is_valid else geom)
    oevk["geometry"] = oevk.geometry.buffer(0)
    oevk = oevk[oevk.geometry.notna() & ~oevk.geometry.is_empty].copy()

    # Pártlistás győztes OEVK-szinten.
    lista_cols_oevk = [c for c in lista_cols if c in oevk.columns]
    if lista_cols_oevk:
        mat = oevk[lista_cols_oevk].fillna(0)
        winner_col = mat.idxmax(axis=1)
        oevk["gyoztes_lista"] = winner_col.str.replace("lista_", "", regex=False)
        oevk["gyoztes_lista_szavazat"] = mat.max(axis=1).astype(int)
        sorted_votes = mat.apply(lambda r: sorted(r.tolist(), reverse=True), axis=1)
        oevk["masodik_lista_szavazat"] = sorted_votes.map(lambda x: int(x[1]) if len(x) > 1 else 0)
        oevk["gyoztes_margin_szavazat"] = oevk["gyoztes_lista_szavazat"] - oevk["masodik_lista_szavazat"]

    if "ervenyes" in oevk.columns:
        denom = pd.to_numeric(oevk["ervenyes"], errors="coerce").replace(0, pd.NA)
        if "gyoztes_lista_szavazat" in oevk.columns:
            oevk["gyoztes_arany_pct"] = (pd.to_numeric(oevk["gyoztes_lista_szavazat"], errors="coerce") / denom * 100).fillna(0).round(2)
            oevk["margin_pct"] = (pd.to_numeric(oevk["gyoztes_margin_szavazat"], errors="coerce") / denom * 100).fillna(0).round(2)

        if {"fidesz_szavazat", "tisza_szavazat"}.issubset(oevk.columns):
            oevk["fidesz_pct"] = (pd.to_numeric(oevk["fidesz_szavazat"], errors="coerce") / denom * 100).fillna(0).round(2)
            oevk["tisza_pct"] = (pd.to_numeric(oevk["tisza_szavazat"], errors="coerce") / denom * 100).fillna(0).round(2)
            oevk["fidesz_tisza_margin_pct"] = (oevk["fidesz_pct"] - oevk["tisza_pct"]).round(2)

    if {"megjelent", "valasztopolgar"}.issubset(oevk.columns):
        denom_pop = pd.to_numeric(oevk["valasztopolgar"], errors="coerce").replace(0, pd.NA)
        oevk["reszvetel_pct"] = (pd.to_numeric(oevk["megjelent"], errors="coerce") / denom_pop * 100).fillna(0).round(2)

    return gpd.GeoDataFrame(oevk, geometry="geometry", crs=f"EPSG:{METERES_CRS}")


def add_oevk_overlay(m: folium.Map, oevk: gpd.GeoDataFrame) -> None:
    #OEVK-határok rárajzolása egy meglévő folium térképre.
    if oevk is None or oevk.empty:
        return

    fields = [c for c in ["oevk_id", "varmegye", "valasztopolgar", "ervenyes", "fidesz_tisza_margin_pct"] if c in oevk.columns]

    folium.GeoJson(
        oevk.to_crs(epsg=WGS84),
        name="OEVK-határok",
        style_function=lambda feature: {
            "fillColor": "transparent",
            "color": "#111111",
            "weight": 1.8,
            "fillOpacity": 0.0,
            "opacity": 0.95,
        },
        tooltip=folium.GeoJsonTooltip(fields=fields, localize=True, sticky=False) if fields else None,
        overlay=True,
        control=True,
    ).add_to(m)


def save_winner_map(gdf: gpd.GeoDataFrame, out: Path, oevk: gpd.GeoDataFrame | None = None) -> None:
    m = folium.Map(location=[47.16, 19.5], zoom_start=7, tiles="CartoDB positron")

    def style(feature):
        party = feature["properties"].get("gyoztes_lista", "")
        return {
            "fillColor": color_for_party(party),
            "color": "#333333",
            "weight": 0.25,
            "fillOpacity": 0.75,
        }

    folium.GeoJson(
        gdf,
        name="Győztes lista",
        style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=tooltip_cols(gdf), localize=True, sticky=False),
    ).add_to(m)
    add_oevk_overlay(m, oevk)
    folium.LayerControl().add_to(m)
    m.save(out)


def save_numeric_map(gdf: gpd.GeoDataFrame, column: str, title: str, out: Path, colors=None, oevk: gpd.GeoDataFrame | None = None) -> None:
    if column not in gdf.columns:
        return

    vals = pd.to_numeric(gdf[column], errors="coerce").dropna()
    if vals.empty:
        return

    vmin = float(vals.quantile(0.02))
    vmax = float(vals.quantile(0.98))
    if vmin == vmax:
        vmax = vmin + 1

    if colors is None:
        colors = ["#f7f7f7", "#08306b"]

    cmap = LinearColormap(colors, vmin=vmin, vmax=vmax)
    cmap.caption = title

    m = folium.Map(location=[47.16, 19.5], zoom_start=7, tiles="CartoDB positron")

    def style(feature):
        v = feature["properties"].get(column)
        try:
            v = float(v)
        except Exception:
            v = vmin
        return {
            "fillColor": cmap(v),
            "color": "#333333",
            "weight": 0.25,
            "fillOpacity": 0.75,
        }

    folium.GeoJson(
        gdf,
        name=title,
        style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=tooltip_cols(gdf), localize=True, sticky=False),
    ).add_to(m)
    cmap.add_to(m)
    add_oevk_overlay(m, oevk)
    folium.LayerControl().add_to(m)
    m.save(out)


def save_oevk_szazalekos_terkep(oevk: gpd.GeoDataFrame, out: Path) -> None:

    if oevk is None or oevk.empty:
        return

    web = szep_oevk_tooltip_oszlopok(oevk.to_crs(epsg=WGS84))
    m = folium.Map(location=[47.16, 19.5], zoom_start=7, tiles="CartoDB positron")

    fields = [c for c in [
        "oevk_id", "varmegye", "gyoztes_lista_szep", "gyoztes_arany", "gyoztes_elony",
        "fidesz_arany", "tisza_arany", "fidesz_tisza_margin", "reszvetel",
        "valasztopolgar_szep", "megjelent_szep", "ervenyes_szep",
    ] if c in web.columns]

    aliases = {
        "oevk_id": "OEVK:",
        "varmegye": "Vármegye:",
        "gyoztes_lista_szep": "Győztes:",
        "gyoztes_arany": "Győztes aránya:",
        "gyoztes_elony": "Győztes előnye:",
        "fidesz_arany": "FIDESZ-KDNP:",
        "tisza_arany": "TISZA:",
        "fidesz_tisza_margin": "FIDESZ - TISZA:",
        "reszvetel": "Részvétel:",
        "valasztopolgar_szep": "Választópolgár:",
        "megjelent_szep": "Megjelent:",
        "ervenyes_szep": "Érvényes:",
    }
    tooltip_aliases = [aliases.get(c, c + ":") for c in fields]

    def style(feature):
        party = feature["properties"].get("gyoztes_lista", "")
        return {
            "fillColor": color_for_party(party),
            "color": "#111111",
            "weight": 2.0,
            "fillOpacity": 0.72,
            "opacity": 1.0,
        }

    folium.GeoJson(
        web,
        name="OEVK eredmények - győztes szerint színezve",
        style_function=style,
        tooltip=folium.GeoJsonTooltip(
            fields=fields,
            aliases=tooltip_aliases,
            localize=True,
            sticky=False,
        ) if fields else None,
    ).add_to(m)

    labels = web.to_crs(epsg=METERES_CRS).copy()
    labels["label_point"] = labels.geometry.representative_point()
    labels = labels.set_geometry("label_point").to_crs(epsg=WGS84)

    for _, row in labels.iterrows():
        oevk_id = tisztit_szoveg(row.get("oevk_id", ""))
        gyoztes = tisztit_szoveg(row.get("gyoztes_lista_szep", row.get("gyoztes_lista", "")))
        arany = tisztit_szoveg(row.get("gyoztes_arany", ""))
        txt_label = f"{oevk_id}<br>{gyoztes} {arany}".strip()
        if not oevk_id:
            continue

        pt = row.get("label_point", None)
        if pt is None or getattr(pt, "is_empty", True):
            continue

        folium.Marker(
            location=[pt.y, pt.x],
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    font-size: 10px;
                    font-weight: 700;
                    color: #111;
                    text-align: center;
                    text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff;
                    line-height: 1.1;
                    white-space: nowrap;">
                    {txt_label}
                </div>
                """
            ),
        ).add_to(m)

    folium.LayerControl().add_to(m)
    m.save(out)


def save_oevk_margin_terkep(oevk: gpd.GeoDataFrame, out: Path) -> None:
    if oevk is None or oevk.empty:
        return

    web = szep_oevk_tooltip_oszlopok(oevk.to_crs(epsg=WGS84))
    m = folium.Map(location=[47.16, 19.5], zoom_start=7, tiles="CartoDB positron")

    fields = [c for c in [
        "oevk_id", "varmegye", "gyoztes_lista_szep", "gyoztes_arany",
        "fidesz_arany", "tisza_arany", "fidesz_tisza_margin", "reszvetel",
    ] if c in web.columns]

    if "fidesz_tisza_margin_pct" not in web.columns:
        save_oevk_szazalekos_terkep(web, out)
        return

    vals = pd.to_numeric(web["fidesz_tisza_margin_pct"], errors="coerce").fillna(0)
    vmax = max(5.0, min(60.0, float(vals.abs().quantile(0.98))))
    cmap = LinearColormap(["#2166ac", "#f7f7f7", "#f28e2b"], vmin=-vmax, vmax=vmax)
    cmap.caption = "OEVK Fidesz - Tisza különbség (%)"

    def style(feature):
        v = feature["properties"].get("fidesz_tisza_margin_pct")
        try:
            v = float(v)
        except Exception:
            v = 0.0
        return {
            "fillColor": cmap(v),
            "color": "#111111",
            "weight": 2.0,
            "fillOpacity": 0.74,
            "opacity": 1.0,
        }

    folium.GeoJson(
        web,
        name="OEVK Fidesz-Tisza margin",
        style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=fields, localize=True, sticky=False) if fields else None,
    ).add_to(m)

    cmap.add_to(m)
    folium.LayerControl().add_to(m)
    m.save(out)


def save_regi_cellaszintu_terkep(gdf: gpd.GeoDataFrame, oevk: gpd.GeoDataFrame, out: Path) -> None:
    if gdf is None or gdf.empty:
        return

    web = gdf.to_crs(epsg=METERES_CRS).copy()
    web["geometry"] = web.geometry.simplify(35, preserve_topology=True)
    web = web.to_crs(epsg=WGS84)

    m = folium.Map(location=[47.16, 19.5], zoom_start=7, tiles="CartoDB positron")

    def winner_style(feature):
        party = feature["properties"].get("gyoztes_lista", "")
        return {
            "fillColor": color_for_party(party),
            "color": "#333333",
            "weight": 0.25,
            "fillOpacity": 0.72,
        }

    folium.GeoJson(
        web,
        name="Cellaszintű győztes lista",
        style_function=winner_style,
        tooltip=folium.GeoJsonTooltip(fields=tooltip_cols(web), localize=True, sticky=False),
        show=True,
    ).add_to(m)

    if "fidesz_tisza_margin_pct" in web.columns:
        vals = pd.to_numeric(web["fidesz_tisza_margin_pct"], errors="coerce").fillna(0)
        vmax = max(5.0, min(60.0, float(vals.abs().quantile(0.98))))
        cmap_margin = LinearColormap(["#2166ac", "#f7f7f7", "#f28e2b"], vmin=-vmax, vmax=vmax)
        cmap_margin.caption = "Cellaszintű Fidesz - Tisza különbség (%)"

        def margin_style(feature):
            v = feature["properties"].get("fidesz_tisza_margin_pct")
            try:
                v = float(v)
            except Exception:
                v = 0.0
            return {
                "fillColor": cmap_margin(v),
                "color": "#333333",
                "weight": 0.2,
                "fillOpacity": 0.70,
            }

        folium.GeoJson(
            web,
            name="Cellaszintű Fidesz-Tisza margin",
            style_function=margin_style,
            tooltip=folium.GeoJsonTooltip(fields=tooltip_cols(web), localize=True, sticky=False),
            show=False,
        ).add_to(m)
        cmap_margin.add_to(m)

    if "reszvetel_pct" in web.columns:
        vals = pd.to_numeric(web["reszvetel_pct"], errors="coerce").dropna()
        if not vals.empty:
            cmap_reszv = LinearColormap(["#f7f7f7", "#08306b"], vmin=float(vals.quantile(0.02)), vmax=float(vals.quantile(0.98)))
            cmap_reszv.caption = "Cellaszintű részvétel (%)"

            def reszvetel_style(feature):
                v = feature["properties"].get("reszvetel_pct")
                try:
                    v = float(v)
                except Exception:
                    v = 0.0
                return {
                    "fillColor": cmap_reszv(v),
                    "color": "#333333",
                    "weight": 0.2,
                    "fillOpacity": 0.70,
                }

            folium.GeoJson(
                web,
                name="Cellaszintű részvétel",
                style_function=reszvetel_style,
                tooltip=folium.GeoJsonTooltip(fields=tooltip_cols(web), localize=True, sticky=False),
                show=False,
            ).add_to(m)
            cmap_reszv.add_to(m)

    add_oevk_overlay(m, oevk)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(out)


def save_oevk_boundary_map(oevk: gpd.GeoDataFrame, out: Path) -> None:
    save_oevk_szazalekos_terkep(oevk, out)


def save_maps(gdf: gpd.GeoDataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    oevk_boundaries = make_oevk_boundaries(gdf)
    if not oevk_boundaries.empty:
        oevk_boundaries.to_crs(epsg=WGS84).to_file(out_dir / "oevk_hatarok_2026.geojson", driver="GeoJSON")
        oevk_boundaries.drop(columns="geometry").to_csv(out_dir / "oevk_hatarok_2026.csv", index=False, encoding="utf-8-sig")

        save_oevk_szazalekos_terkep(oevk_boundaries, out_dir / "05_oevk_szazalekok_egy_szin.html")
        save_oevk_margin_terkep(oevk_boundaries, out_dir / "05_oevk_fidesz_tisza_margin.html")

        save_oevk_szazalekos_terkep(oevk_boundaries, out_dir / "05_oevk_eredmenyek.html")
        save_oevk_szazalekos_terkep(oevk_boundaries, out_dir / "05_oevk_hatarok.html")


    web = gdf.to_crs(epsg=METERES_CRS).copy()
    web["geometry"] = web.geometry.simplify(35, preserve_topology=True)
    web = web.to_crs(epsg=WGS84)

    save_winner_map(web, out_dir / "01_gyoztes_lista.html", oevk_boundaries)
    save_numeric_map(web, "margin_pct", "Győztes előnye (%)", out_dir / "02_margin.html", oevk=oevk_boundaries)
    save_numeric_map(web, "reszvetel_pct", "Részvétel (%)", out_dir / "03_reszvetel.html", oevk=oevk_boundaries)
    save_numeric_map(
        web,
        "fidesz_tisza_margin_pct",
        "Fidesz - Tisza különbség (%)",
        out_dir / "04_fidesz_tisza_margin.html",
        colors=["#2166ac", "#f7f7f7", "#f28e2b"],
        oevk=oevk_boundaries,
    )

    save_regi_cellaszintu_terkep(gdf, oevk_boundaries, out_dir / "06_regi_cellaszintu_szavazataranyok.html")

    # pár egyszerű összesítő tábla
    for group_col in ["varmegye", "oevk_id", "telepules"]:
        if group_col not in gdf.columns:
            continue
        nums = [c for c in ["valasztopolgar", "megjelent", "ervenyes", "fidesz_szavazat", "tisza_szavazat"] if c in gdf.columns]
        if not nums:
            continue
        tab = gdf.groupby(group_col)[nums].sum(numeric_only=True).reset_index()
        tab.to_csv(out_dir / f"osszesito_{group_col}.csv", index=False, encoding="utf-8-sig")


# Gráf

def primitive(x):
    if pd.isna(x):
        return ""
    if isinstance(x, (str, int, float, bool)):
        return x
    return str(x)


def build_graph(gdf: gpd.GeoDataFrame, min_border_m: float = 10.0) -> nx.Graph:
    g = gdf.to_crs(epsg=METERES_CRS).copy()
    g["geometry"] = g.geometry.buffer(0)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()

    graph = nx.Graph()

    attr_cols = [
        c for c in g.columns
        if c != "geometry" and not c.startswith("pct_")
    ]

    for _, row in g.iterrows():
        node = str(row["node_id"])
        attrs = {c: primitive(row[c]) for c in attr_cols if c != "node_id"}
        cent = row.geometry.centroid
        attrs["x"] = float(cent.x)
        attrs["y"] = float(cent.y)
        graph.add_node(node, **attrs)

    sindex = g.sindex
    geoms = list(g.geometry)
    ids = list(g["node_id"].astype(str))

    for i, geom in enumerate(geoms):
        cand = sindex.query(geom, predicate="intersects")
        for j in cand:
            j = int(j)
            if j <= i:
                continue
            other = geoms[j]
            inter = geom.boundary.intersection(other.boundary)
            kozos = float(inter.length) if not inter.is_empty else 0.0
            if kozos >= min_border_m:
                graph.add_edge(ids[i], ids[j], kozos_hatar_m=round(kozos, 3))

    return graph


def save_graph(gdf: gpd.GeoDataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = build_graph(gdf)

    nx.write_graphml(graph, out_dir / "gerry_graph_2026.graphml")

    nodes = []
    for n, attrs in graph.nodes(data=True):
        nodes.append({"node_id": n, **attrs})
    pd.DataFrame(nodes).to_csv(out_dir / "gerry_nodes_2026.csv", index=False, encoding="utf-8-sig")

    edges = []
    for a, b, attrs in graph.edges(data=True):
        edges.append({"source": a, "target": b, **attrs})
    pd.DataFrame(edges).to_csv(out_dir / "gerry_edges_2026.csv", index=False, encoding="utf-8-sig")

    data = nx.node_link_data(graph)
    (out_dir / "gerry_graph_2026.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    gdf.to_crs(epsg=WGS84).to_file(out_dir / "gerry_units_2026.geojson", driver="GeoJSON")

    meta = {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "megjegyzes": "9 helyen Voronoi, máshol települési cella",
    }
    (out_dir / "metadata_2026.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Gráf: {graph.number_of_nodes():,} csúcs, {graph.number_of_edges():,} él")


# Fő futás

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data", help="Ide rakod a bemeneti fájlokat.")
    ap.add_argument("--out", default="output", help="Ide ment a program.")
    ap.add_argument("--cache", default="cache", help="Geokód cache.")
    ap.add_argument("--no-geocode", action="store_true", help="Ne kérdezzen le új koordinátát, csak cache-ből dolgozzon.")
    ap.add_argument("--sleep", type=float, default=1.15, help="Nominatim várakozás másodpercben.")
    args = ap.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    cache_dir = Path(args.cache)

    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    lista_dir = data_dir / "lista"
    korzet_file = keres_fajlt(data_dir, ["korzet"], (".csv", ".xls", ".xlsx"))
    if korzet_file is None:
        korzet_file = keres_fajlt(data_dir, ["levalogatas"], (".csv", ".xls", ".xlsx"))

    admin8 = keres_fajlt(data_dir, ["admin8"], (".shp",))

    lista_files = excel_fajlok(lista_dir)

    print("\nBemenetek:")
    print(f"  lista mappa: {lista_dir}")
    print(f"  listás fájl db: {len(lista_files)}")
    print(f"  körzetállomány: {korzet_file if korzet_file else 'NINCS'}")
    print(f"  admin8 shapefile: {admin8 if admin8 else 'NINCS'}")

    if not lista_files:
        raise SystemExit("Nincs listás XLS/XLSX a data/lista mappában. A ZIP-eket csomagold ki oda.")
    if korzet_file is None:
        raise SystemExit("Nincs körzetállomány. Tedd be a data mappába: Korzet_levalogatas20260116_ORSZAGOS.csv")
    if admin8 is None:
        raise SystemExit("Nincs admin8.shp. Tedd be például ide: data/teruletek/admin8.shp")

    # 1. körzetek
    print("\n1. Körzetállomány olvasása")
    szk = normalizal_korzet(korzet_file, cache_dir)
    szk.to_csv(out_dir / "szavazokorok_2026.csv", index=False, encoding="utf-8-sig")
    print(f"  szavazókör sor: {len(szk):,}")

    # 2. listás eredmények
    print("\n2. Listás eredmények olvasása")
    wide_parts = []
    long_parts = []
    for f in lista_files:
        print(f"  {f.name}")
        wide, long = parse_lista_file(f, cache_dir)
        if not wide.empty:
            wide_parts.append(wide)
        if not long.empty:
            long_parts.append(long)

    if not wide_parts:
        raise RuntimeError("Nem sikerült listás eredményt olvasni.")

    lista_wide = pd.concat(wide_parts, ignore_index=True)
    lista_long = pd.concat(long_parts, ignore_index=True) if long_parts else pd.DataFrame()

    lista_wide.to_csv(out_dir / "eredmeny_lista_szeles_2026.csv", index=False, encoding="utf-8-sig")
    if not lista_long.empty:
        lista_long.to_csv(out_dir / "eredmeny_lista_hosszu_2026.csv", index=False, encoding="utf-8-sig")

    print(f"  listás szavazókör sor: {len(lista_wide):,}")

    # 3. összefűzés
    print("\n3. Körzet + eredmény összefűzése")
    merged = szk.merge(lista_wide, on="szavazokor_id", how="left", suffixes=("", "_eredm"))

    for c in ["varmegye", "telepules", "varmegye_kod", "telepules_kod", "szavazokor"]:
        c2 = c + "_eredm"
        if c2 in merged.columns:
            merged = merged.drop(columns=[c2])

    # Szám mezők nullázása, ahol nincs adat.
    for c in osszeg_oszlopok(merged):
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)

    merged = ujraszamol_szazalekok(merged)
    merged.to_csv(out_dir / "szavazokor_eredmeny_2026.csv", index=False, encoding="utf-8-sig")

    # 4. geokódolás a 9 helyen
    print("\n4. Szavazóköri geokódolás a 9 kijelölt helyen")
    geokodolt = geocode_szavazokorok(
        merged,
        cache_dir / "szavazokor_geocode.csv",
        no_geocode=args.no_geocode,
        sleep_sec=args.sleep,
    )
    geokodolt.to_csv(out_dir / "szavazokor_eredmeny_geokodolt_2026.csv", index=False, encoding="utf-8-sig")

    # 5. településhatárok + Voronoi / települési cellák
    print("\n5. Admin8 és elemzési cellák")
    admin = load_admin8(admin8)
    units = keszit_elemzesi_egysegek(
        geokodolt,
        admin,
        cache_dir,
        no_geocode=args.no_geocode,
        sleep_sec=args.sleep,
    )

    units_wgs = units.to_crs(epsg=WGS84)
    units_wgs.to_file(out_dir / "egysegek_2026.geojson", driver="GeoJSON")
    units_wgs.drop(columns="geometry").to_csv(out_dir / "egysegek_2026.csv", index=False, encoding="utf-8-sig")
    print(f"  egység db: {len(units):,}")

    # 6. térképek
    print("\n6. Térképek")
    save_maps(units, out_dir / "terkepek")
    print(f"  térképek: {out_dir / 'terkepek'}")

    # 7. gráf
    print("\n7. Gerrymandering gráf")
    save_graph(units, out_dir / "gerrymandering_graf")

    print("\nKész.")
    print(f"Fő kimenet: {out_dir / 'egysegek_2026.geojson'}")
    print(f"Gráf:       {out_dir / 'gerrymandering_graf' / 'gerry_graph_2026.graphml'}")
    print(f"Térképek:   {out_dir / 'terkepek'}")


if __name__ == "__main__":
    main()
