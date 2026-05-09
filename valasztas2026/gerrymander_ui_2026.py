
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from branca.colormap import LinearColormap
from shapely.ops import unary_union

try:
    import gerrymander_2026 as algo
except ImportError as e:
    raise SystemExit(
        "Nem találom a gerrymander_26.py fájlt.\n"
        "Tedd ezt a UI scriptet ugyanabba a mappába, ahol az algoritmus fájl van."
    ) from e


# Alapértékek.

DEFAULT_INPUT = "output/egysegek_2026.geojson"
DEFAULT_OUTPUT_ROOT = "output/gerry_recom_lite_runs"
DEFAULT_RUN_NAME = "tisza_recom_run"

PARTY_PRESETS = {
    "TISZA javára": ("tisza_szavazat", "fidesz_szavazat"),
    "FIDESZ javára": ("fidesz_szavazat", "tisza_szavazat"),
    "Egyéni / kézi oszlopnév": ("tisza_szavazat", "fidesz_szavazat"),
}


@dataclass
class RunConfig:
    input_geojson: Path = Path(DEFAULT_INPUT)
    output_root: Path = Path(DEFAULT_OUTPUT_ROOT)
    run_name: str = DEFAULT_RUN_NAME
    target_col: str = "tisza_szavazat"
    opponent_col: str = "fidesz_szavazat"
    pop_col: str = "valasztopolgar"
    counties: list[str] | None = None

    epsilon: float = 0.12
    restarts: int = 4
    steps_per_restart: int = 3500
    recom_probability: float = 0.78
    random_seed: int = 20260508

    # A motorban ez a CUT_LENGTH_WEIGHT.
    compactness_weight: float = 0.055

    seat_weight: float = 350_000
    pop_penalty_weight: float = 220_000
    hard_pop_violation_weight: float = 1_000_000
    bp_kerulet_split_weight: float = 70_000
    duna_mixed_weight: float = 35_000
    duna_edge_weight: float = 6_000
    ideal_target_win_margin: float = 0.06

    use_current_oevk_as_start: bool = True

    @property
    def output_dir(self) -> Path:
        safe = self.run_name.strip().replace(" ", "_") or "gerry_run"
        return self.output_root / safe


# UI

def ask_config_with_tkinter() -> RunConfig:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception:
        print("Tkinter nem elérhető, alapbeállításokkal futok.")
        return RunConfig(counties=[])

    root = tk.Tk()
    root.title("2026 ReCom gerrymandering beállítások")
    root.geometry("660x720")

    values: dict[str, Any] = {}

    frm = ttk.Frame(root, padding=14)
    frm.pack(fill="both", expand=True)

    row = 0

    def label(text: str):
        nonlocal row
        ttk.Label(frm, text=text).grid(row=row, column=0, sticky="w", pady=4)

    def entry(default: str, width: int = 42) -> tk.StringVar:
        var = tk.StringVar(value=default)
        ttk.Entry(frm, textvariable=var, width=width).grid(row=row, column=1, sticky="ew", pady=4)
        return var

    frm.columnconfigure(1, weight=1)

    ttk.Label(
        frm,
        text="ReCom-lite futás paraméterei",
        font=("Arial", 14, "bold"),
    ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 12))
    row += 1

    label("Bemeneti GeoJSON")
    input_var = entry(DEFAULT_INPUT)

    def browse_input():
        p = filedialog.askopenfilename(
            title="Válaszd ki az egységek GeoJSON fájlt",
            filetypes=[("GeoJSON", "*.geojson"), ("JSON", "*.json"), ("Minden fájl", "*.*")],
        )
        if p:
            input_var.set(p)

    ttk.Button(frm, text="Tallózás", command=browse_input).grid(row=row, column=2, padx=6)
    row += 1

    label("Kimeneti gyökérmappa")
    output_root_var = entry(DEFAULT_OUTPUT_ROOT)

    def browse_output():
        p = filedialog.askdirectory(title="Válaszd ki a kimeneti gyökérmappát")
        if p:
            output_root_var.set(p)

    ttk.Button(frm, text="Tallózás", command=browse_output).grid(row=row, column=2, padx=6)
    row += 1

    label("Futás / mentés neve")
    run_name_var = entry(DEFAULT_RUN_NAME)
    row += 1

    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
    row += 1

    label("Kinek kedvezzen?")
    preset_var = tk.StringVar(value="TISZA javára")
    preset_box = ttk.Combobox(frm, textvariable=preset_var, values=list(PARTY_PRESETS.keys()), state="readonly")
    preset_box.grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    label("Célpárt szavazat oszlop")
    target_var = entry("tisza_szavazat")
    row += 1

    label("Ellenfél szavazat oszlop")
    opp_var = entry("fidesz_szavazat")
    row += 1

    def preset_changed(_event=None):
        t, o = PARTY_PRESETS.get(preset_var.get(), (target_var.get(), opp_var.get()))
        if preset_var.get() != "Egyéni / kézi oszlopnév":
            target_var.set(t)
            opp_var.set(o)

    preset_box.bind("<<ComboboxSelected>>", preset_changed)

    label("Népesség / választópolgár oszlop")
    pop_var = entry("valasztopolgar")
    row += 1

    label("Csak ezek a megyék, vesszővel")
    counties_var = entry("")
    ttk.Label(frm, text="Üresen: minden megye", foreground="#666666").grid(row=row, column=2, sticky="w")
    row += 1

    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
    row += 1

    label("Népességeltérés epsilon")
    epsilon_var = entry("0.12", width=14)
    ttk.Label(frm, text="0.10 = ±10%", foreground="#666666").grid(row=row, column=2, sticky="w")
    row += 1

    label("Restarts")
    restarts_var = entry("4", width=14)
    row += 1

    label("Lépés / restart")
    steps_var = entry("3500", width=14)
    row += 1

    label("ReCom valószínűség")
    recom_var = entry("0.78", width=14)
    ttk.Label(frm, text="0.80 körül jó", foreground="#666666").grid(row=row, column=2, sticky="w")
    row += 1

    label("Random seed")
    seed_var = entry("20260508", width=14)
    row += 1

    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
    row += 1

    label("Alak szabályosság súlya")
    compact_var = entry("0.055", width=14)
    ttk.Label(frm, text="nagyobb = kompaktabb", foreground="#666666").grid(row=row, column=2, sticky="w")
    row += 1

    label("Mandátum súly")
    seat_var = entry("350000", width=14)
    row += 1

    label("Népességbüntetés")
    pop_pen_var = entry("220000", width=14)
    row += 1

    label("Budapest kerület split büntetés")
    bp_split_var = entry("70000", width=14)
    row += 1

    label("Duna keverés büntetés")
    duna_mix_var = entry("35000", width=14)
    row += 1

    label("Duna belső él büntetés")
    duna_edge_var = entry("6000", width=14)
    row += 1

    start_current_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        frm,
        text="Jelenlegi OEVK-kból induljon, ha lehet",
        variable=start_current_var,
    ).grid(row=row, column=0, columnspan=3, sticky="w", pady=8)
    row += 1

    ttk.Label(
        frm,
        text=(
            "Tipp: gyors próba = 1 restart, 500-1000 lépés.\n"
            "Komolyabb futás = 4-8 restart, 5000+ lépés."
        ),
        foreground="#555555",
    ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 10))
    row += 1

    def parse_float(var: tk.StringVar, name: str) -> float:
        try:
            return float(var.get().replace(",", "."))
        except Exception:
            raise ValueError(f"Nem jó szám: {name} = {var.get()}")

    def parse_int(var: tk.StringVar, name: str) -> int:
        try:
            return int(float(var.get().replace(",", ".")))
        except Exception:
            raise ValueError(f"Nem jó egész szám: {name} = {var.get()}")

    def start_run():
        try:
            counties = [x.strip() for x in counties_var.get().split(",") if x.strip()]
            cfg = RunConfig(
                input_geojson=Path(input_var.get()),
                output_root=Path(output_root_var.get()),
                run_name=run_name_var.get().strip() or "gerry_run",
                target_col=target_var.get().strip(),
                opponent_col=opp_var.get().strip(),
                pop_col=pop_var.get().strip(),
                counties=counties,
                epsilon=parse_float(epsilon_var, "epsilon"),
                restarts=parse_int(restarts_var, "restarts"),
                steps_per_restart=parse_int(steps_var, "steps"),
                recom_probability=parse_float(recom_var, "recom probability"),
                random_seed=parse_int(seed_var, "seed"),
                compactness_weight=parse_float(compact_var, "alak szabályosság"),
                seat_weight=parse_float(seat_var, "mandátum súly"),
                pop_penalty_weight=parse_float(pop_pen_var, "népességbüntetés"),
                bp_kerulet_split_weight=parse_float(bp_split_var, "kerület split"),
                duna_mixed_weight=parse_float(duna_mix_var, "Duna mix"),
                duna_edge_weight=parse_float(duna_edge_var, "Duna edge"),
                use_current_oevk_as_start=bool(start_current_var.get()),
            )
        except Exception as e:
            messagebox.showerror("Hibás paraméter", str(e))
            return

        values["config"] = cfg
        root.destroy()

    def cancel():
        values["config"] = None
        root.destroy()

    buttons = ttk.Frame(frm)
    buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=12)
    ttk.Button(buttons, text="Mégse", command=cancel).pack(side="left", padx=5)
    ttk.Button(buttons, text="Futtatás", command=start_run).pack(side="left", padx=5)

    root.mainloop()
    cfg = values.get("config")
    if cfg is None:
        raise SystemExit("Futtatás megszakítva.")
    return cfg



def apply_config_to_algo(cfg: RunConfig) -> None:
    algo.INPUT_GEOJSON = Path(cfg.input_geojson)
    algo.OUTPUT_DIR = Path(cfg.output_dir)
    algo.TARGET_COL = cfg.target_col
    algo.OPPONENT_COL = cfg.opponent_col
    algo.POP_COL = cfg.pop_col
    algo.RUN_COUNTIES = cfg.counties or []

    algo.EPSILON = float(cfg.epsilon)
    algo.RESTARTS = int(cfg.restarts)
    algo.STEPS_PER_RESTART = int(cfg.steps_per_restart)
    algo.RECOM_PROBABILITY = float(cfg.recom_probability)
    algo.RANDOM_SEED = int(cfg.random_seed)
    algo.USE_CURRENT_OEVK_AS_START = bool(cfg.use_current_oevk_as_start)

    algo.CUT_LENGTH_WEIGHT = float(cfg.compactness_weight)
    algo.SEAT_WEIGHT = float(cfg.seat_weight)
    algo.POP_PENALTY_WEIGHT = float(cfg.pop_penalty_weight)
    algo.HARD_POP_VIOLATION_WEIGHT = float(cfg.hard_pop_violation_weight)
    algo.BP_KERULET_SPLIT_WEIGHT = float(cfg.bp_kerulet_split_weight)
    algo.DUNA_MIXED_SIDE_WEIGHT = float(cfg.duna_mixed_weight)
    algo.DUNA_INTERNAL_EDGE_WEIGHT = float(cfg.duna_edge_weight)
    algo.IDEAL_TARGET_WIN_MARGIN = float(cfg.ideal_target_win_margin)



# Összesítések

def polsby_popper(geom) -> float:
    if geom is None or geom.is_empty:
        return 0.0
    area = float(geom.area)
    perim = float(geom.length)
    if perim <= 0:
        return 0.0
    return float(4 * math.pi * area / (perim * perim))


def safe_mode(series: pd.Series, default: str = "") -> str:
    s = series.dropna().astype(str)
    if s.empty:
        return default
    return s.mode().iloc[0]


def ideal_pop_by_county(units: gpd.GeoDataFrame) -> dict[str, float]:
    ideals = {}
    for county_slug, part in units.groupby("_county_slug"):
        k = algo.county_quota(part, "_county", "_county_code")
        if k <= 0:
            continue
        ideals[county_slug] = float(part["_pop"].sum()) / k
    return ideals


def summarize_plan(
    units: gpd.GeoDataFrame,
    assignment_col: str,
    plan_name: str,
    graph=None,
) -> gpd.GeoDataFrame:
    rows = []
    ideals = ideal_pop_by_county(units)

    tmp = units.copy()
    tmp["_assignment_tmp"] = tmp[assignment_col].astype(str)
    tmp = tmp[tmp["_assignment_tmp"].notna() & (tmp["_assignment_tmp"] != "")].copy()

    for did, part in tmp.groupby("_assignment_tmp"):
        geom = unary_union(list(part.geometry))
        pop = float(part["_pop"].sum())
        target = float(part["_target_votes"].sum())
        opp = float(part["_opponent_votes"].sum())
        votes2 = max(target + opp, 1)
        county_slug = safe_mode(part["_county_slug"])
        ideal = ideals.get(county_slug, max(pop, 1))
        dev_pct = (pop - ideal) / max(ideal, 1) * 100

        # Budapest/Duna diagnosztika.
        sides = set()
        if graph is not None:
            for n in part["_node"].astype(str):
                if n in graph.nodes:
                    side = graph.nodes[n].get("duna_side", "")
                    if side:
                        sides.add(side)

        bp_kers = []
        if "_bp_kerulet" in part.columns:
            bp_kers = sorted([x for x in part["_bp_kerulet"].dropna().astype(str).unique() if x])

        rows.append({
            "plan": plan_name,
            "district_id": str(did),
            "megye": safe_mode(part["_county"]),
            "megye_slug": county_slug,
            "valasztopolgar": round(pop, 1),
            "ideal_pop": round(ideal, 1),
            "pop_deviation_pct": round(dev_pct, 3),
            "target_votes": round(target, 1),
            "opponent_votes": round(opp, 1),
            "target_pct": round(target / votes2 * 100, 3),
            "opponent_pct": round(opp / votes2 * 100, 3),
            "target_margin_pct": round((target - opp) / votes2 * 100, 3),
            "target_wins": bool(target > opp),
            "egyseg_db": int(len(part)),
            "terulet_m2": round(float(geom.area), 1),
            "kerulet_m": round(float(geom.length), 1),
            "polsby_popper": round(polsby_popper(geom), 4),
            "bp_keruletek": ";".join(bp_kers),
            "bp_kerulet_db": len(bp_kers),
            "duna_sides": ";".join(sorted(sides)),
            "duna_mixed": bool("buda" in sides and "pest" in sides),
            "geometry": geom,
        })

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=units.crs)


def national_summary(original: gpd.GeoDataFrame | None, simulated: gpd.GeoDataFrame, cfg: RunConfig) -> pd.DataFrame:
    rows = []

    def one(plan: str, df: gpd.GeoDataFrame):
        target_votes = float(df["target_votes"].sum())
        opponent_votes = float(df["opponent_votes"].sum())
        denom = max(target_votes + opponent_votes, 1)
        return {
            "plan": plan,
            "target_col": cfg.target_col,
            "opponent_col": cfg.opponent_col,
            "districts": int(len(df)),
            "target_seats": int(df["target_wins"].sum()),
            "opponent_seats": int((~df["target_wins"].astype(bool)).sum()),
            "target_vote_share_pct": round(target_votes / denom * 100, 3),
            "opponent_vote_share_pct": round(opponent_votes / denom * 100, 3),
            "avg_margin_pct": round(float(df["target_margin_pct"].mean()), 3),
            "median_margin_pct": round(float(df["target_margin_pct"].median()), 3),
            "avg_abs_margin_pct": round(float(df["target_margin_pct"].abs().mean()), 3),
            "avg_polsby_popper": round(float(df["polsby_popper"].mean()), 4),
            "avg_pop_deviation_abs_pct": round(float(df["pop_deviation_pct"].abs().mean()), 3),
        }

    if original is not None and not original.empty:
        rows.append(one("eredeti_oevk", original))
    rows.append(one("szimulalt_recom", simulated))

    out = pd.DataFrame(rows)
    if len(out) == 2:
        out["target_seat_delta_vs_original"] = out["target_seats"] - int(out.iloc[0]["target_seats"])
    else:
        out["target_seat_delta_vs_original"] = 0
    return out


def county_comparison(original: gpd.GeoDataFrame | None, simulated: gpd.GeoDataFrame) -> pd.DataFrame:
    sim = simulated.groupby(["megye", "megye_slug"]).agg(
        szimulalt_korzet=("district_id", "count"),
        szimulalt_target_mandatum=("target_wins", "sum"),
        szimulalt_avg_margin=("target_margin_pct", "mean"),
        szimulalt_avg_polsby=("polsby_popper", "mean"),
        szimulalt_avg_pop_dev=("pop_deviation_pct", lambda x: np.mean(np.abs(x))),
    ).reset_index()

    if original is None or original.empty:
        sim["eredeti_korzet"] = np.nan
        sim["eredeti_target_mandatum"] = np.nan
        sim["mandatum_valtozas"] = np.nan
        return sim

    orig = original.groupby(["megye", "megye_slug"]).agg(
        eredeti_korzet=("district_id", "count"),
        eredeti_target_mandatum=("target_wins", "sum"),
        eredeti_avg_margin=("target_margin_pct", "mean"),
        eredeti_avg_polsby=("polsby_popper", "mean"),
    ).reset_index()

    out = orig.merge(sim, on=["megye", "megye_slug"], how="outer")
    out["mandatum_valtozas"] = out["szimulalt_target_mandatum"] - out["eredeti_target_mandatum"]
    return out


# Térképek

def party_color(col: str, fallback: str) -> str:
    s = col.lower()
    if "fidesz" in s or "kdnp" in s:
        return "#f28e2b"
    if "tisza" in s:
        return "#4e79a7"
    if "mi_haz" in s or "mi haz" in s:
        return "#e15759"
    if "dk" in s:
        return "#9467bd"
    return fallback


def simplify_for_web(gdf: gpd.GeoDataFrame, meters: float = 45) -> gpd.GeoDataFrame:
    web = gdf.to_crs(epsg=algo.METERES_CRS).copy()
    web["geometry"] = web.geometry.simplify(meters, preserve_topology=True)
    return web.to_crs(epsg=algo.WGS84)


def tooltip_fields(gdf: gpd.GeoDataFrame, wanted: list[str]) -> list[str]:
    return [c for c in wanted if c in gdf.columns]


def save_margin_map(districts: gpd.GeoDataFrame, out_html: Path, cfg: RunConfig, title: str) -> None:
    web = simplify_for_web(districts)
    vals = pd.to_numeric(web["target_margin_pct"], errors="coerce").fillna(0)
    vmax = max(8.0, min(60.0, float(vals.abs().quantile(0.98)) if len(vals) else 20.0))

    target_color = party_color(cfg.target_col, "#4e79a7")
    opponent_color = party_color(cfg.opponent_col, "#f28e2b")
    cmap = LinearColormap([opponent_color, "#f7f7f7", target_color], vmin=-vmax, vmax=vmax)
    cmap.caption = title

    m = folium.Map(location=[47.16, 19.5], zoom_start=7, tiles="CartoDB positron")

    def style(feature):
        v = feature["properties"].get("target_margin_pct", 0)
        try:
            v = float(v)
        except Exception:
            v = 0.0
        return {"fillColor": cmap(v), "color": "#222222", "weight": 1.0, "fillOpacity": 0.74}

    fields = tooltip_fields(web, [
        "district_id", "megye", "target_pct", "opponent_pct", "target_margin_pct",
        "target_wins", "valasztopolgar", "pop_deviation_pct", "polsby_popper",
        "bp_keruletek", "duna_sides",
    ])
    folium.GeoJson(web, name=title, style_function=style,
                   tooltip=folium.GeoJsonTooltip(fields=fields, localize=True, sticky=False)).add_to(m)
    cmap.add_to(m)
    folium.LayerControl().add_to(m)
    m.save(out_html)


def save_winner_map(districts: gpd.GeoDataFrame, out_html: Path, cfg: RunConfig, title: str) -> None:
    web = simplify_for_web(districts)
    target_color = party_color(cfg.target_col, "#4e79a7")
    opponent_color = party_color(cfg.opponent_col, "#f28e2b")

    m = folium.Map(location=[47.16, 19.5], zoom_start=7, tiles="CartoDB positron")

    def style(feature):
        win = bool(feature["properties"].get("target_wins", False))
        return {
            "fillColor": target_color if win else opponent_color,
            "color": "#222222",
            "weight": 1.0,
            "fillOpacity": 0.72,
        }

    fields = tooltip_fields(web, [
        "district_id", "megye", "target_wins", "target_pct", "opponent_pct",
        "target_margin_pct", "valasztopolgar", "polsby_popper",
    ])
    folium.GeoJson(web, name=title, style_function=style,
                   tooltip=folium.GeoJsonTooltip(fields=fields, localize=True, sticky=False)).add_to(m)
    folium.LayerControl().add_to(m)
    m.save(out_html)


def save_placeholder_html(out_html: Path, title: str, message: str) -> None:
    out_html.write_text(
        f"""<!doctype html><html lang='hu'><head><meta charset='utf-8'><title>{title}</title></head>
        <body style='font-family:Arial,sans-serif;margin:32px'>
        <h1>{title}</h1><p>{message}</p>
        </body></html>""",
        encoding="utf-8",
    )


# PNG


def save_png_charts(original: gpd.GeoDataFrame | None, simulated: gpd.GeoDataFrame, county_cmp: pd.DataFrame, out_dir: Path, cfg: RunConfig) -> None:
    png_dir = out_dir / "png_abrak"
    png_dir.mkdir(parents=True, exist_ok=True)

    # 1. Mandátum összehasonlítás.
    plans = []
    seats = []
    if original is not None and not original.empty:
        plans.append("Eredeti OEVK")
        seats.append(int(original["target_wins"].sum()))
    plans.append("Szimulált")
    seats.append(int(simulated["target_wins"].sum()))

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(plans, seats)
    ax.set_ylabel(f"{cfg.target_col} által nyert körzet")
    ax.set_title("Target mandátumok: eredeti vs szimulált")
    for i, v in enumerate(seats):
        ax.text(i, v + 0.2, str(v), ha="center")
    fig.tight_layout()
    fig.savefig(png_dir / "01_mandatum_osszehasonlitas.png", dpi=180)
    plt.close(fig)

    # 2. Megyénkénti változás.
    if "mandatum_valtozas" in county_cmp.columns and county_cmp["mandatum_valtozas"].notna().any():
        tmp = county_cmp.copy().sort_values("mandatum_valtozas")
        fig, ax = plt.subplots(figsize=(10, max(5, len(tmp) * 0.32)))
        ax.barh(tmp["megye"].astype(str), tmp["mandatum_valtozas"].astype(float))
        ax.axvline(0, linewidth=1)
        ax.set_xlabel("Target mandátumváltozás")
        ax.set_title("Megyénkénti target mandátumváltozás")
        fig.tight_layout()
        fig.savefig(png_dir / "02_megyenkenti_mandatum_valtozas.png", dpi=180)
        plt.close(fig)

    # 3. Margin hisztogram.
    fig, ax = plt.subplots(figsize=(8, 5))
    if original is not None and not original.empty:
        ax.hist(original["target_margin_pct"].astype(float), bins=24, alpha=0.55, label="eredeti")
    ax.hist(simulated["target_margin_pct"].astype(float), bins=24, alpha=0.55, label="szimulált")
    ax.axvline(0, linewidth=1)
    ax.set_xlabel("Target margin (%)")
    ax.set_ylabel("Körzet db")
    ax.set_title("Körzetmarginok eloszlása")
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_dir / "03_margin_histogram.png", dpi=180)
    plt.close(fig)

    # 4. Populációeltérés.
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(simulated["pop_deviation_pct"].astype(float), bins=24)
    ax.axvline(0, linewidth=1)
    ax.set_xlabel("Népességeltérés az ideálistól (%)")
    ax.set_ylabel("Körzet db")
    ax.set_title("Szimulált körzetek népességeltérése")
    fig.tight_layout()
    fig.savefig(png_dir / "04_nepesseg_elteres_histogram.png", dpi=180)
    plt.close(fig)

    # 5. Kompaktság.
    fig, ax = plt.subplots(figsize=(8, 5))
    if original is not None and not original.empty:
        ax.hist(original["polsby_popper"].astype(float), bins=20, alpha=0.55, label="eredeti")
    ax.hist(simulated["polsby_popper"].astype(float), bins=20, alpha=0.55, label="szimulált")
    ax.set_xlabel("Polsby-Popper kompaktság")
    ax.set_ylabel("Körzet db")
    ax.set_title("Kompaktság eloszlása")
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_dir / "05_kompaktsag_histogram.png", dpi=180)
    plt.close(fig)

    # 6. Szavazatarány vs mandátumarány.
    nat_target_votes = float(simulated["target_votes"].sum())
    nat_opp_votes = float(simulated["opponent_votes"].sum())
    denom = max(nat_target_votes + nat_opp_votes, 1)
    vote_share = nat_target_votes / denom * 100
    seat_share = simulated["target_wins"].sum() / max(len(simulated), 1) * 100
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(["Szavazatarány", "Mandátumarány"], [vote_share, seat_share])
    ax.set_ylim(0, 100)
    ax.set_ylabel("%")
    ax.set_title(f"{cfg.target_col}: szavazatarány vs szimulált mandátumarány")
    for i, v in enumerate([vote_share, seat_share]):
        ax.text(i, v + 1, f"{v:.1f}%", ha="center")
    fig.tight_layout()
    fig.savefig(png_dir / "06_szavazatarany_vs_mandatumarany.png", dpi=180)
    plt.close(fig)


# mentések

def save_everything(units: gpd.GeoDataFrame, graph, cfg: RunConfig) -> None:
    out_dir = cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Körzet-összesítések.
    active_units = units[units["uj_oevk"].astype(str).str.len() > 0].copy()
    if active_units.empty:
        active_units = units.copy()

    sim_districts = summarize_plan(active_units, "uj_oevk", "szimulalt_recom", graph)
    orig_districts = None
    if "oevk_id" in active_units.columns:
        orig_districts = summarize_plan(active_units, "oevk_id", "eredeti_oevk", graph)

    nat = national_summary(orig_districts, sim_districts, cfg)
    county_cmp = county_comparison(orig_districts, sim_districts)

    # Fontos geometriás kimenetek.
    units.to_crs(epsg=algo.WGS84).to_file(out_dir / "recom_units_2026.geojson", driver="GeoJSON")
    sim_districts.to_crs(epsg=algo.WGS84).to_file(out_dir / "recom_districts_2026.geojson", driver="GeoJSON")

    if orig_districts is not None and not orig_districts.empty:
        orig_districts.to_crs(epsg=algo.WGS84).to_file(out_dir / "eredeti_oevk_2026.geojson", driver="GeoJSON")

    nat.to_csv(out_dir / "00_osszefoglalo.csv", index=False, encoding="utf-8-sig")
    county_cmp.to_csv(out_dir / "01_megyei_mandatumvaltozas.csv", index=False, encoding="utf-8-sig")

    sim_cols = [
        "uj_oevk", "megye", "valasztopolgar", "target_votes", "opponent_votes",
        "target_pct", "opponent_pct", "target_margin_pct", "target_wins",
        "polsby_popper", "pop_deviation_pct", "bp_keruletek",
    ]
    sim_cols = [c for c in sim_cols if c in sim_districts.columns]
    sim_table = sim_districts[sim_cols].copy().rename(columns={"uj_oevk": "district_id"})
    sim_table.insert(0, "plan", "szimulalt_recom")

    if orig_districts is not None and not orig_districts.empty:
        orig_cols = [
            "oevk_id", "megye", "valasztopolgar", "target_votes", "opponent_votes",
            "target_pct", "opponent_pct", "target_margin_pct", "target_wins",
            "polsby_popper", "pop_deviation_pct", "bp_keruletek",
        ]
        orig_cols = [c for c in orig_cols if c in orig_districts.columns]
        orig_table = orig_districts[orig_cols].copy().rename(columns={"oevk_id": "district_id"})
        orig_table.insert(0, "plan", "eredeti_oevk")
        korzet_cmp = pd.concat([orig_table, sim_table], ignore_index=True)
    else:
        korzet_cmp = sim_table

    korzet_cmp.to_csv(out_dir / "02_korzet_osszehasonlitas.csv", index=False, encoding="utf-8-sig")

    if "target_margin_pct" in korzet_cmp.columns:
        close_df = (
            korzet_cmp.assign(abs_margin=pd.to_numeric(korzet_cmp["target_margin_pct"], errors="coerce").abs())
            .sort_values(["plan", "abs_margin"], ascending=[True, True])
            .drop(columns=["abs_margin"])
            .groupby("plan", as_index=False, group_keys=False)
            .head(20)
        )
        close_df.to_csv(out_dir / "03_legszorosabb_korzetek.csv", index=False, encoding="utf-8-sig")

    save_margin_map(sim_districts, out_dir / "01_szimulalt_margin.html", cfg, "Szimulált körzetek - target margin")
    save_winner_map(sim_districts, out_dir / "02_szimulalt_gyoztes.html", cfg, "Szimulált körzetek - győztes")

    if orig_districts is not None and not orig_districts.empty:
        save_margin_map(orig_districts, out_dir / "03_eredeti_margin.html", cfg, "Eredeti OEVK-k - target margin")
    else:
        save_placeholder_html(out_dir / "03_eredeti_margin.html", "Eredeti OEVK térkép", "Nincs oevk_id oszlop, ezért nem készült eredeti OEVK térkép.")


    save_png_charts(orig_districts, sim_districts, county_cmp, out_dir, cfg)

    # Metadata.
    meta = {
        "run_name": cfg.run_name,
        "created_at_unix": time.time(),
        "input_geojson": str(cfg.input_geojson),
        "output_dir": str(out_dir),
        "target_col": cfg.target_col,
        "opponent_col": cfg.opponent_col,
        "pop_col": cfg.pop_col,
        "counties": cfg.counties or [],
        "epsilon": cfg.epsilon,
        "restarts": cfg.restarts,
        "steps_per_restart": cfg.steps_per_restart,
        "recom_probability": cfg.recom_probability,
        "random_seed": cfg.random_seed,
        "compactness_weight_cut_length": cfg.compactness_weight,
        "seat_weight": cfg.seat_weight,
        "pop_penalty_weight": cfg.pop_penalty_weight,
        "bp_kerulet_split_weight": cfg.bp_kerulet_split_weight,
        "duna_mixed_weight": cfg.duna_mixed_weight,
        "duna_edge_weight": cfg.duna_edge_weight,
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "simulated_districts": int(len(sim_districts)),
        "simulated_target_seats": int(sim_districts["target_wins"].sum()),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nKimenetek mentve ide:")
    print(f"  {out_dir}")
    print("\nNyisd meg például ezt:")
    print(f"  {out_dir / '01_szimulalt_margin.html'}")



# Futtatás

def run_with_config(cfg: RunConfig) -> None:
    apply_config_to_algo(cfg)

    print("\nReCom-lite gerrymandering futás UI-ból")
    print(f"Futás neve: {cfg.run_name}")
    print(f"Target:     {cfg.target_col}")
    print(f"Opponent:   {cfg.opponent_col}")
    print(f"Input:      {cfg.input_geojson}")
    print(f"Output:     {cfg.output_dir}")

    units = algo.load_units(cfg.input_geojson)
    graph = algo.build_graph(units)
    graph = algo.connect_components_inside_counties(graph, units)

    units = units[units["_node"].isin(graph.nodes)].copy()

    result_units = algo.optimize_all(units, graph)

    save_everything(result_units, graph, cfg)

    print("\nKész.")


def main() -> None:
    cfg = ask_config_with_tkinter()
    run_with_config(cfg)


if __name__ == "__main__":
    main()
