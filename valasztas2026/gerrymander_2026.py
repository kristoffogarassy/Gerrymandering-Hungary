
from __future__ import annotations

import json
import math
import random
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import folium
import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from branca.colormap import LinearColormap
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from shapely.validation import make_valid



INPUT_GEOJSON = Path("output/egysegek_2026.geojson")

OUTPUT_DIR = Path("output/gerry_recom_lite")


TARGET_COL = "tisza_szavazat"
OPPONENT_COL = "fidesz_szavazat"

POP_COL = "valasztopolgar"


RUN_COUNTIES: list[str] = []


EPSILON = 0.12


RESTARTS = 4


STEPS_PER_RESTART = 3500

RECOM_PROBABILITY = 0.78

RECOM_CUT_TRIES = 120

RECOM_PAIR_TRIES = 35

FLIP_TRIES = 80

RANDOM_SEED = 20260508


USE_CURRENT_OEVK_AS_START = True


DUNA_ONLY_BUDAPEST = True

MAP_SIMPLIFY_M = 45


# CÉLFÜGGVÉNY SÚLYAI


SEAT_WEIGHT = 350_000

POP_PENALTY_WEIGHT = 220_000

HARD_POP_VIOLATION_WEIGHT = 1_000_000

CUT_LENGTH_WEIGHT = 0.055

IDEAL_TARGET_WIN_MARGIN = 0.06
WASTED_WIN_MARGIN_WEIGHT = 45_000

OPPONENT_PACKING_BONUS = 20_000

BP_KERULET_SPLIT_WEIGHT = 70_000

DUNA_MIXED_SIDE_WEIGHT = 35_000

DUNA_INTERNAL_EDGE_WEIGHT = 6_000


# 2026-os OEVK-kvóták

COUNTY_DISTRICTS = {
    "budapest": 16,
    "baranya": 4,
    "bacs_kiskun": 6,
    "bekes": 4,
    "borsod_abauj_zemplen": 7,
    "csongrad_csanad": 4,
    "csongrad": 4,
    "fejer": 5,
    "gyor_moson_sopron": 5,
    "hajdu_bihar": 6,
    "heves": 3,
    "jasz_nagykun_szolnok": 4,
    "komarom_esztergom": 3,
    "nograd": 2,
    "pest": 14,
    "somogy": 4,
    "szabolcs_szatmar_bereg": 6,
    "tolna": 3,
    "vas": 3,
    "veszprem": 4,
    "zala": 3,
}

COUNTY_DISTRICTS_BY_CODE = {
    "01": 16,
    "02": 4,
    "03": 6,
    "04": 4,
    "05": 7,
    "06": 4,
    "07": 5,
    "08": 5,
    "09": 6,
    "10": 3,
    "11": 4,
    "12": 3,
    "13": 2,
    "14": 14,
    "15": 4,
    "16": 6,
    "17": 3,
    "18": 3,
    "19": 4,
    "20": 3,
}


DUNA_BUDAPEST_LONLAT = [
    (19.070, 47.705),
    (19.085, 47.640),
    (19.066, 47.585),
    (19.045, 47.535),
    (19.044, 47.495),
    (19.064, 47.445),
    (19.078, 47.380),
]


WGS84 = 4326
METERES_CRS = 23700
MIN_COMMON_BORDER_M = 8.0


# segédfüggvények

def tisztit(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def kod2(x) -> str:
    """Megyekódot normalizál: 1, 1.0, "01" -> "01"."""
    s = tisztit(x)
    if not s:
        return ""
    if re.fullmatch(r"\d+(?:\.0)?", s):
        s = str(int(float(s)))
    return s.zfill(2)


def slug(x) -> str:
    #Ékezetmentes
    s = tisztit(x).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^0-9a-z]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def to_num(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def first_existing_col(gdf: gpd.GeoDataFrame, options: list[str], required: bool = True) -> str | None:
    lookup = {slug(c): c for c in gdf.columns}
    for o in options:
        if slug(o) in lookup:
            return lookup[slug(o)]
    if required:
        raise SystemExit(f"Nem találok ilyen oszlopot: {options}\nElérhető oszlopok: {list(gdf.columns)}")
    return None


def polsby_popper(geom) -> float:
    if geom is None or geom.is_empty:
        return 0.0
    area = float(geom.area)
    perim = float(geom.length)
    if perim <= 0:
        return 0.0
    return float(4 * math.pi * area / (perim * perim))


def is_budapest_value(x) -> bool:
    return slug(x) == "budapest"


def county_key_from_row(row, county_col: str, county_code_col: str | None) -> str:
    if county_code_col and tisztit(row.get(county_code_col, "")):
        code = kod2(row.get(county_code_col, ""))
        if code == "01":
            return "budapest"
    return slug(row.get(county_col, ""))


def county_quota(gdf_county: gpd.GeoDataFrame, county_col: str, county_code_col: str | None) -> int:
    if county_code_col and county_code_col in gdf_county.columns:
        codes = gdf_county[county_code_col].dropna().map(kod2)
        if not codes.empty:
            code = codes.mode().iloc[0]
            if code in COUNTY_DISTRICTS_BY_CODE:
                return COUNTY_DISTRICTS_BY_CODE[code]

    names = gdf_county[county_col].dropna().astype(str)
    if not names.empty:
        key = slug(names.mode().iloc[0])
        if key in COUNTY_DISTRICTS:
            return COUNTY_DISTRICTS[key]

    # Végső fallback
    if "oevk_id" in gdf_county.columns:
        n = gdf_county["oevk_id"].dropna().astype(str).nunique()
        if n > 0:
            return int(n)

    return 1


def parse_bp_kerulet_from_ids(szavazokor_ids: object) -> str:
    #A középső három szám a településkód, Budapesten ez a kerület.
    s = tisztit(szavazokor_ids)
    ids = re.findall(r"01-(\d{3})-\d{3}", s)
    if not ids:
        return ""
    vals = pd.Series(ids)
    return "bp_" + vals.mode().iloc[0]


def make_duna_line() -> LineString:
    line = LineString(DUNA_BUDAPEST_LONLAT)
    gs = gpd.GeoSeries([line], crs=f"EPSG:{WGS84}").to_crs(epsg=METERES_CRS)
    return gs.iloc[0]


def duna_side(point: Point, duna_line: LineString) -> str:
    if point is None or point.is_empty:
        return ""
    nearest = duna_line.interpolate(duna_line.project(point))
    return "buda" if point.x < nearest.x else "pest"


def line_between_centroids(g1, g2):
    return LineString([g1.centroid, g2.centroid])


# Adatbetöltés és gráfépítés

def load_units(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        raise SystemExit(f"Nincs bemeneti GeoJSON: {path}\nElőbb futtasd a pipeline_basic_2026.py-t.")

    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=WGS84)
    gdf = gdf.to_crs(epsg=METERES_CRS)

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf.geometry.map(lambda geom: make_valid(geom) if geom is not None and not geom.is_valid else geom)
    gdf["geometry"] = gdf.geometry.buffer(0)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    county_col = first_existing_col(gdf, ["varmegye", "megye", "county"])
    pop_col = first_existing_col(gdf, [POP_COL, "valasztopolgar", "nevjegyzek_szavazokor", "ervenyes"])
    target_col = first_existing_col(gdf, [TARGET_COL])
    opponent_col = first_existing_col(gdf, [OPPONENT_COL])

    if county_col != "_county":
        gdf["_county"] = gdf[county_col].map(tisztit)
    if pop_col != "_pop":
        gdf["_pop"] = to_num(gdf[pop_col])
    if target_col != "_target_votes":
        gdf["_target_votes"] = to_num(gdf[target_col])
    if opponent_col != "_opponent_votes":
        gdf["_opponent_votes"] = to_num(gdf[opponent_col])

    county_code_col = first_existing_col(gdf, ["varmegye_kod", "megye_kod", "county_code"], required=False)
    if county_code_col:
        gdf["_county_code"] = gdf[county_code_col].map(kod2)
    else:
        gdf["_county_code"] = ""

    if "node_id" not in gdf.columns:
        gdf["node_id"] = [f"N{str(i).zfill(6)}" for i in range(len(gdf))]
    gdf["_node"] = gdf["node_id"].astype(str)

    if "szavazokor_ids" in gdf.columns:
        gdf["_bp_kerulet"] = gdf["szavazokor_ids"].map(parse_bp_kerulet_from_ids)
    else:
        gdf["_bp_kerulet"] = ""

    gdf["_county_slug"] = [
        county_key_from_row(row, "_county", "_county_code")
        for _, row in gdf.iterrows()
    ]

    # Fallback.
    bp_mask = gdf["_county"].map(is_budapest_value) | (gdf["_county_code"] == "01")
    gdf.loc[bp_mask, "_county_slug"] = "budapest"

    return gdf.reset_index(drop=True)


def build_graph(gdf: gpd.GeoDataFrame) -> nx.Graph:
    print("Gráf építése közös határok alapján...")
    duna = make_duna_line()

    g = nx.Graph()

    for idx, row in gdf.iterrows():
        node = row["_node"]
        geom = row.geometry
        centroid = geom.centroid

        use_duna = (not DUNA_ONLY_BUDAPEST) or (row["_county_slug"] == "budapest")
        side = duna_side(centroid, duna) if use_duna else ""

        g.add_node(
            node,
            ix=int(idx),
            pop=float(row["_pop"]),
            target=float(row["_target_votes"]),
            opponent=float(row["_opponent_votes"]),
            county=row["_county"],
            county_slug=row["_county_slug"],
            county_code=row["_county_code"],
            bp_kerulet=row["_bp_kerulet"],
            duna_side=side,
            area=float(geom.area),
            x=float(centroid.x),
            y=float(centroid.y),
        )

    geoms = list(gdf.geometry)
    nodes = list(gdf["_node"])
    sindex = gdf.sindex

    for i, geom in enumerate(geoms):
        cand = sindex.query(geom, predicate="intersects")
        for j in cand:
            j = int(j)
            if j <= i:
                continue

            #megyehatár hard constraint
            if gdf.iloc[i]["_county_slug"] != gdf.iloc[j]["_county_slug"]:
                continue

            other = geoms[j]
            inter = geom.boundary.intersection(other.boundary)
            common = float(inter.length) if not inter.is_empty else 0.0

            if common < MIN_COMMON_BORDER_M:
                continue

            u, v = nodes[i], nodes[j]
            side_u = g.nodes[u]["duna_side"]
            side_v = g.nodes[v]["duna_side"]
            same_county = g.nodes[u]["county_slug"] == g.nodes[v]["county_slug"]
            duna_cross = bool(
                same_county
                and g.nodes[u]["county_slug"] == "budapest"
                and side_u
                and side_v
                and side_u != side_v
            )

            if g.nodes[u]["county_slug"] == "budapest":
                try:
                    if line_between_centroids(geom, other).crosses(duna.buffer(35)):
                        duna_cross = True
                except Exception:
                    pass

            g.add_edge(
                u,
                v,
                border_m=round(common, 3),
                duna_cross=duna_cross,
                artificial=False,
            )

    print(f"  csúcs: {g.number_of_nodes():,}, él: {g.number_of_edges():,}")
    return g


def connect_components_inside_counties(graph: nx.Graph, gdf: gpd.GeoDataFrame) -> nx.Graph:
    """
    Néha a shapefile/topológia miatt egy megye gráfja több komponensre szakad.
    Ilyenkor megyén belül a legközelebbi komponensek közé teszünk egy gyenge mű-élet.
    """
    g = graph.copy()

    for county in sorted(gdf["_county_slug"].dropna().unique()):
        nodes = [n for n, d in g.nodes(data=True) if d["county_slug"] == county]
        if not nodes:
            continue

        sub = g.subgraph(nodes)
        comps = [set(c) for c in nx.connected_components(sub)]
        if len(comps) <= 1:
            continue

        print(f"  Figyelem: {county} gráfja {len(comps)} komponens. Gyenge összekötő éleket rakok be.")

        while len(comps) > 1:
            best = None
            for a_idx in range(len(comps)):
                for b_idx in range(a_idx + 1, len(comps)):
                    ca, cb = comps[a_idx], comps[b_idx]
                    sample_a = list(ca)[:80]
                    sample_b = list(cb)[:80]
                    for u in sample_a:
                        ux, uy = g.nodes[u]["x"], g.nodes[u]["y"]
                        for v in sample_b:
                            vx, vy = g.nodes[v]["x"], g.nodes[v]["y"]
                            dist = math.hypot(ux - vx, uy - vy)
                            if best is None or dist < best[0]:
                                best = (dist, u, v, a_idx, b_idx)

            if best is None:
                break

            dist, u, v, a_idx, b_idx = best
            g.add_edge(u, v, border_m=1.0, duna_cross=False, artificial=True, distance_m=round(dist, 1))

            sub = g.subgraph(nodes)
            comps = [set(c) for c in nx.connected_components(sub)]

    return g


# Kiinduló térkép

def district_pop(assign: dict[str, int], graph: nx.Graph, k: int) -> np.ndarray:
    pops = np.zeros(k)
    for n, d in assign.items():
        if 0 <= d < k:
            pops[d] += graph.nodes[n]["pop"]
    return pops


def current_oevk_assignment(gdf: gpd.GeoDataFrame, nodes: list[str], k: int) -> dict[str, int] | None:
    if not USE_CURRENT_OEVK_AS_START or "oevk_id" not in gdf.columns:
        return None

    sub = gdf[gdf["_node"].isin(nodes)].copy()
    vals = sorted([v for v in sub["oevk_id"].dropna().astype(str).unique() if v and v.lower() != "nan"])
    if len(vals) != k:
        return None

    mapping = {v: i for i, v in enumerate(vals)}
    assign = {}
    for _, row in sub.iterrows():
        val = tisztit(row.get("oevk_id", ""))
        if val not in mapping:
            return None
        assign[row["_node"]] = mapping[val]

    if len(assign) != len(nodes):
        return None
    return assign


def farthest_seeds(graph: nx.Graph, nodes: list[str], k: int, rng: random.Random) -> list[str]:
    first = rng.choice(nodes)
    seeds = [first]

    while len(seeds) < k:
        best_node = None
        best_dist = -1.0
        for n in nodes:
            if n in seeds:
                continue
            x, y = graph.nodes[n]["x"], graph.nodes[n]["y"]
            dmin = min(math.hypot(x - graph.nodes[s]["x"], y - graph.nodes[s]["y"]) for s in seeds)
            if dmin > best_dist:
                best_dist = dmin
                best_node = n
        if best_node is None:
            break
        seeds.append(best_node)

    return seeds


def greedy_initial_assignment(graph: nx.Graph, nodes: list[str], k: int, rng: random.Random) -> dict[str, int]:
    #Saját egyszerű kezdőtérkép.
    seeds = farthest_seeds(graph, nodes, k, rng)
    assign: dict[str, int] = {}
    pops = np.zeros(k)

    for d, n in enumerate(seeds):
        assign[n] = d
        pops[d] += graph.nodes[n]["pop"]

    unassigned = set(nodes) - set(seeds)

    while unassigned:
        order = list(range(k))
        order.sort(key=lambda d: pops[d])

        chosen = None
        for d in order:
            district_nodes = [n for n, lab in assign.items() if lab == d]
            frontier = []
            for n in district_nodes:
                for nb in graph.neighbors(n):
                    if nb in unassigned:
                        frontier.append((n, nb))
            if frontier:
                frontier.sort(key=lambda e: graph.edges[e].get("border_m", 0), reverse=True)
                chosen = (d, frontier[0][1])
                break

        if chosen is None:
            # Ha valamiért nincs frontier
            n = unassigned.pop()
            d = int(np.argmin(pops))
            assign[n] = d
            pops[d] += graph.nodes[n]["pop"]
        else:
            d, n = chosen
            unassigned.remove(n)
            assign[n] = d
            pops[d] += graph.nodes[n]["pop"]

    return assign


def make_initial_assignment(gdf: gpd.GeoDataFrame, graph: nx.Graph, nodes: list[str], k: int, rng: random.Random) -> dict[str, int]:
    start = current_oevk_assignment(gdf, nodes, k)
    if start is not None:
        if all_districts_connected(graph.subgraph(nodes), start, k):
            return start
        print("  A jelenlegi oevk_id kezdőtérkép széteső lenne, ezért saját greedy kezdést használok.")
    return greedy_initial_assignment(graph, nodes, k, rng)



# Pontozás

def plan_tallies(graph: nx.Graph, nodes: list[str], assign: dict[str, int], k: int) -> dict:
    pop = np.zeros(k)
    target = np.zeros(k)
    opp = np.zeros(k)
    area = np.zeros(k)

    for n in nodes:
        d = assign[n]
        pop[d] += graph.nodes[n]["pop"]
        target[d] += graph.nodes[n]["target"]
        opp[d] += graph.nodes[n]["opponent"]
        area[d] += graph.nodes[n]["area"]

    return {"pop": pop, "target": target, "opp": opp, "area": area}


def pop_violation_value(pops: np.ndarray, ideal: float) -> tuple[float, int]:
    devs = np.abs(pops - ideal) / max(ideal, 1)
    soft = float(np.sum(devs ** 2))
    hard = int(np.sum(devs > EPSILON))
    return soft, hard


def kerulet_split_count(graph: nx.Graph, nodes: list[str], assign: dict[str, int]) -> int:
    groups: dict[str, set[int]] = defaultdict(set)
    for n in nodes:
        ker = graph.nodes[n].get("bp_kerulet", "")
        if ker:
            groups[ker].add(assign[n])

    total = 0
    for _, labs in groups.items():
        total += max(0, len(labs) - 1)
    return total


def duna_penalty_parts(graph: nx.Graph, nodes: list[str], assign: dict[str, int], k: int) -> tuple[int, int]:
    sides_by_d = [set() for _ in range(k)]
    for n in nodes:
        side = graph.nodes[n].get("duna_side", "")
        if side:
            sides_by_d[assign[n]].add(side)

    mixed = sum(1 for s in sides_by_d if "buda" in s and "pest" in s)

    node_set = set(nodes)
    internal_cross = 0
    for u, v, data in graph.subgraph(nodes).edges(data=True):
        if assign[u] == assign[v] and data.get("duna_cross", False):
            internal_cross += 1

    return mixed, internal_cross


def cut_length(graph: nx.Graph, nodes: list[str], assign: dict[str, int]) -> float:
    total = 0.0
    for u, v, data in graph.subgraph(nodes).edges(data=True):
        if assign[u] != assign[v]:
            total += float(data.get("border_m", 1.0))
    return total


def score_plan(graph: nx.Graph, nodes: list[str], assign: dict[str, int], k: int, ideal_pop: float) -> tuple[float, dict]:
    tall = plan_tallies(graph, nodes, assign, k)
    pop = tall["pop"]
    target = tall["target"]
    opp = tall["opp"]

    votes2 = np.maximum(target + opp, 1)
    margins = (target - opp) / votes2
    wins = int(np.sum(target > opp))

    pop_soft, pop_hard = pop_violation_value(pop, ideal_pop)
    cut_m = cut_length(graph, nodes, assign)

    wasted_win = float(np.sum(np.maximum(0, margins - IDEAL_TARGET_WIN_MARGIN) ** 2 * (target > opp)))

    opponent_pack = float(np.sum(np.minimum(np.maximum(0, -margins), 0.45) * (target <= opp)))

    ksplit = kerulet_split_count(graph, nodes, assign)
    duna_mixed, duna_edges = duna_penalty_parts(graph, nodes, assign, k)

    value = (
        wins * SEAT_WEIGHT
        + opponent_pack * OPPONENT_PACKING_BONUS
        - pop_soft * POP_PENALTY_WEIGHT
        - pop_hard * HARD_POP_VIOLATION_WEIGHT
        - cut_m * CUT_LENGTH_WEIGHT
        - wasted_win * WASTED_WIN_MARGIN_WEIGHT
        - ksplit * BP_KERULET_SPLIT_WEIGHT
        - duna_mixed * DUNA_MIXED_SIDE_WEIGHT
        - duna_edges * DUNA_INTERNAL_EDGE_WEIGHT
    )

    parts = {
        "score": value,
        "wins": wins,
        "pop_soft": pop_soft,
        "pop_hard": pop_hard,
        "cut_m": cut_m,
        "wasted_win": wasted_win,
        "opponent_pack": opponent_pack,
        "bp_kerulet_split": ksplit,
        "duna_mixed": duna_mixed,
        "duna_edges": duna_edges,
        "min_pop": float(np.min(pop)) if len(pop) else 0.0,
        "max_pop": float(np.max(pop)) if len(pop) else 0.0,
    }
    return float(value), parts


# Érvényesség

def is_district_connected(graph: nx.Graph, assign: dict[str, int], district: int) -> bool:
    nodes = [n for n, d in assign.items() if d == district]
    if not nodes:
        return False
    if len(nodes) == 1:
        return True
    return nx.is_connected(graph.subgraph(nodes))


def all_districts_connected(graph: nx.Graph, assign: dict[str, int], k: int) -> bool:
    return all(is_district_connected(graph, assign, d) for d in range(k))


def connected_after_remove(graph: nx.Graph, assign: dict[str, int], node: str, old_d: int) -> bool:
    nodes = [n for n, d in assign.items() if d == old_d and n != node]
    if not nodes:
        return False
    if len(nodes) == 1:
        return True
    return nx.is_connected(graph.subgraph(nodes))


def pop_ok_after_move(graph: nx.Graph, assign: dict[str, int], node: str, old_d: int, new_d: int, k: int, ideal: float) -> bool:
    pops = district_pop(assign, graph, k)
    p = graph.nodes[node]["pop"]
    pops[old_d] -= p
    pops[new_d] += p
    devs = np.abs(pops - ideal) / max(ideal, 1)
    return bool(np.all(devs <= EPSILON))


# Boundary flip

def boundary_flip_proposal(
    graph: nx.Graph,
    nodes: list[str],
    assign: dict[str, int],
    k: int,
    ideal: float,
    rng: random.Random,
) -> dict[str, int] | None:
    sub = graph.subgraph(nodes)
    edges = [(u, v) for u, v in sub.edges() if assign[u] != assign[v]]
    if not edges:
        return None

    for _ in range(FLIP_TRIES):
        u, v = rng.choice(edges)
        if rng.random() < 0.5:
            node, old_d, new_d = u, assign[u], assign[v]
        else:
            node, old_d, new_d = v, assign[v], assign[u]

        if old_d == new_d:
            continue

        if not connected_after_remove(graph, assign, node, old_d):
            continue

        if not pop_ok_after_move(graph, assign, node, old_d, new_d, k, ideal):
            continue

        cand = dict(assign)
        cand[node] = new_d
        return cand

    return None


# ReCom

def district_pairs(graph: nx.Graph, nodes: list[str], assign: dict[str, int]) -> list[tuple[int, int]]:
    pairs = set()
    for u, v in graph.subgraph(nodes).edges():
        a, b = assign[u], assign[v]
        if a != b:
            pairs.add(tuple(sorted((a, b))))
    return list(pairs)


def random_spanning_tree(sub: nx.Graph, rng: random.Random) -> nx.Graph:

    h = nx.Graph()
    h.add_nodes_from(sub.nodes(data=True))

    for u, v, data in sub.edges(data=True):
        w = rng.random()
        if data.get("artificial", False):
            w += 3.0
        if data.get("duna_cross", False):
            w += 1.5
        border = float(data.get("border_m", 1.0))
        w += 1.0 / max(border, 1.0)
        h.add_edge(u, v, weight=w)

    return nx.minimum_spanning_tree(h, weight="weight")


def component_pop(graph: nx.Graph, comp: set[str]) -> float:
    return sum(float(graph.nodes[n]["pop"]) for n in comp)


def recom_proposal(
    graph: nx.Graph,
    nodes: list[str],
    assign: dict[str, int],
    k: int,
    ideal: float,
    rng: random.Random,
) -> dict[str, int] | None:
    pairs = district_pairs(graph, nodes, assign)
    if not pairs:
        return None

    rng.shuffle(pairs)
    pairs = pairs[:RECOM_PAIR_TRIES]

    best_candidate = None
    best_local_score = -float("inf")

    for d1, d2 in pairs:
        pair_nodes = [n for n in nodes if assign[n] == d1 or assign[n] == d2]
        if len(pair_nodes) <= 2:
            continue

        sub = graph.subgraph(pair_nodes).copy()
        if not nx.is_connected(sub):
            continue

        tree = random_spanning_tree(sub, rng)
        tree_edges = list(tree.edges())
        rng.shuffle(tree_edges)

        for cut_edge in tree_edges[:RECOM_CUT_TRIES]:
            t = tree.copy()
            t.remove_edge(*cut_edge)
            comps = [set(c) for c in nx.connected_components(t)]
            if len(comps) != 2:
                continue

            c1, c2 = comps
            p1 = component_pop(graph, c1)
            p2 = component_pop(graph, c2)

            if abs(p1 - ideal) / max(ideal, 1) > EPSILON:
                continue
            if abs(p2 - ideal) / max(ideal, 1) > EPSILON:
                continue


            for flip in [False, True]:
                cand = dict(assign)
                if not flip:
                    for n in c1:
                        cand[n] = d1
                    for n in c2:
                        cand[n] = d2
                else:
                    for n in c1:
                        cand[n] = d2
                    for n in c2:
                        cand[n] = d1


                t1 = sum(graph.nodes[n]["target"] for n in cand if cand[n] == d1)
                o1 = sum(graph.nodes[n]["opponent"] for n in cand if cand[n] == d1)
                t2 = sum(graph.nodes[n]["target"] for n in cand if cand[n] == d2)
                o2 = sum(graph.nodes[n]["opponent"] for n in cand if cand[n] == d2)
                local = int(t1 > o1) + int(t2 > o2)
                local += rng.random() * 0.05

                if local > best_local_score:
                    best_local_score = local
                    best_candidate = cand

    return best_candidate


# Megyei optimalizálás

def accept_move(old_score: float, new_score: float, step: int, total_steps: int, rng: random.Random) -> bool:
    if new_score >= old_score:
        return True

    # Simulated annealing
    t0 = 45_000
    t1 = 800
    if total_steps <= 1:
        temp = t1
    else:
        frac = step / (total_steps - 1)
        temp = t0 * ((t1 / t0) ** frac)

    prob = math.exp((new_score - old_score) / max(temp, 1e-9))
    return rng.random() < prob


def optimize_county(
    gdf_county: gpd.GeoDataFrame,
    graph: nx.Graph,
    county_name: str,
    k: int,
    restart_id: int,
    rng: random.Random,
) -> tuple[dict[str, int], dict]:
    nodes = list(gdf_county["_node"].astype(str))
    total_pop = sum(float(graph.nodes[n]["pop"]) for n in nodes)
    ideal = total_pop / k

    print(f"\n{county_name}: {k} körzet, {len(nodes):,} egység, ideális népesség: {ideal:,.0f}")

    assign = make_initial_assignment(gdf_county, graph, nodes, k, rng)

    if not all_districts_connected(graph.subgraph(nodes), assign, k):
        print("  Figyelem: a kezdőtérkép nem teljesen összefüggő. A ReCom/flip javíthat rajta, de ellenőrizd az outputot.")

    cur_score, cur_parts = score_plan(graph, nodes, assign, k, ideal)
    best_assign = dict(assign)
    best_score = cur_score
    best_parts = dict(cur_parts)


    for step in range(1, STEPS_PER_RESTART + 1):
        if rng.random() < RECOM_PROBABILITY:
            cand = recom_proposal(graph, nodes, assign, k, ideal, rng)
            move_type = "recom"
        else:
            cand = boundary_flip_proposal(graph, nodes, assign, k, ideal, rng)
            move_type = "flip"

        if cand is None:
            continue

        new_score, new_parts = score_plan(graph, nodes, cand, k, ideal)
        if accept_move(cur_score, new_score, step, STEPS_PER_RESTART, rng):
            assign = cand
            cur_score = new_score
            cur_parts = new_parts

        if cur_score > best_score:
            best_score = cur_score
            best_assign = dict(assign)
            best_parts = dict(cur_parts)

        if step % 250 == 0 or step == STEPS_PER_RESTART:
            print(
                f"  restart {restart_id}, step {step:>5}: "
                f"best seats={best_parts['wins']}, "
                f"pop_bad={best_parts['pop_hard']}, "
                f"ker_split={best_parts['bp_kerulet_split']}, "
                f"duna={best_parts['duna_mixed']}"
            )

    return best_assign, best_parts


def optimize_all(gdf: gpd.GeoDataFrame, graph: nx.Graph) -> gpd.GeoDataFrame:
    rng_master = random.Random(RANDOM_SEED)
    out = gdf.copy()
    out["uj_oevk"] = ""
    out["recom_label"] = -1


    run_counties_norm = {slug(c) for c in RUN_COUNTIES}

    for county_slug in sorted(out["_county_slug"].dropna().unique()):
        county_gdf = out[out["_county_slug"] == county_slug].copy()
        if county_gdf.empty:
            continue

        county_name = county_gdf["_county"].dropna().astype(str).mode().iloc[0]
        if run_counties_norm and slug(county_name) not in run_counties_norm and county_slug not in run_counties_norm:
            print(f"\n{county_name}: kihagyva RUN_COUNTIES miatt.")
            continue

        k = county_quota(county_gdf, "_county", "_county_code")

        best_county_assign = None
        best_county_parts = None
        best_county_score = -float("inf")

        for r in range(1, RESTARTS + 1):
            rng = random.Random(rng_master.randint(1, 10**12))
            assign, parts = optimize_county(county_gdf, graph, county_name, k, r, rng)

            if parts["score"] > best_county_score:
                best_county_score = parts["score"]
                best_county_assign = assign
                best_county_parts = parts

        assert best_county_assign is not None

        for n, lab in best_county_assign.items():
            out.loc[out["_node"] == n, "recom_label"] = int(lab)
            out.loc[out["_node"] == n, "uj_oevk"] = f"{county_slug}-{lab + 1:02d}"

        print(
            f"{county_name}: kész. "
            f"target mandátum={best_county_parts['wins']}/{k}, "
            f"score={best_county_parts['score']:,.0f}"
        )

    return out


# Kimenetek

def district_summary(units: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    rows = []
    for did, part in units.groupby("uj_oevk"):
        if not did:
            continue

        geom = unary_union(list(part.geometry))
        pop = float(part["_pop"].sum())
        target = float(part["_target_votes"].sum())
        opp = float(part["_opponent_votes"].sum())
        votes2 = max(target + opp, 1)

        row = {
            "uj_oevk": did,
            "megye": part["_county"].dropna().astype(str).mode().iloc[0] if part["_county"].notna().any() else "",
            "megye_slug": part["_county_slug"].dropna().astype(str).mode().iloc[0] if part["_county_slug"].notna().any() else "",
            "valasztopolgar": round(pop, 1),
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
            "geometry": geom,
        }

        if part["_bp_kerulet"].astype(str).str.len().sum() > 0:
            kers = sorted(k for k in part["_bp_kerulet"].dropna().astype(str).unique() if k)
            row["bp_keruletek"] = ";".join(kers)
            row["bp_kerulet_db"] = len(kers)
        else:
            row["bp_keruletek"] = ""
            row["bp_kerulet_db"] = 0

        rows.append(row)

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=units.crs)


def save_html_map(districts: gpd.GeoDataFrame, out_html: Path) -> None:
    web = districts.to_crs(epsg=METERES_CRS).copy()
    web["geometry"] = web.geometry.simplify(MAP_SIMPLIFY_M, preserve_topology=True)
    web = web.to_crs(epsg=WGS84)

    vals = pd.to_numeric(web["target_margin_pct"], errors="coerce").fillna(0)
    vmax = max(8.0, min(60.0, float(vals.abs().quantile(0.98)) if len(vals) else 20.0))

    cmap = LinearColormap(["#f28e2b", "#f7f7f7", "#4e79a7"], vmin=-vmax, vmax=vmax)
    cmap.caption = f"{TARGET_COL} - {OPPONENT_COL} margin (%)"

    m = folium.Map(location=[47.16, 19.5], zoom_start=7, tiles="CartoDB positron")

    def style(feature):
        v = feature["properties"].get("target_margin_pct", 0)
        try:
            v = float(v)
        except Exception:
            v = 0.0
        return {
            "fillColor": cmap(v),
            "color": "#222222",
            "weight": 1.0,
            "fillOpacity": 0.72,
        }

    tooltip_fields = [
        "uj_oevk",
        "megye",
        "valasztopolgar",
        "target_pct",
        "opponent_pct",
        "target_margin_pct",
        "target_wins",
        "egyseg_db",
        "polsby_popper",
        "bp_keruletek",
    ]
    tooltip_fields = [c for c in tooltip_fields if c in web.columns]

    folium.GeoJson(
        web,
        name="Optimalizált körzetek",
        style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, localize=True, sticky=False),
    ).add_to(m)

    cmap.add_to(m)
    folium.LayerControl().add_to(m)
    m.save(out_html)


def save_outputs(units: gpd.GeoDataFrame, graph: nx.Graph) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    units_wgs = units.to_crs(epsg=WGS84)
    units_wgs.to_file(OUTPUT_DIR / "recom_units_2026.geojson", driver="GeoJSON")

    districts = district_summary(units)
    districts_wgs = districts.to_crs(epsg=WGS84)
    districts_wgs.to_file(OUTPUT_DIR / "recom_districts_2026.geojson", driver="GeoJSON")


    save_html_map(districts, OUTPUT_DIR / "recom_optimalizalt_terkep.html")

    # metadata
    meta = {
        "input": str(INPUT_GEOJSON),
        "target_col": TARGET_COL,
        "opponent_col": OPPONENT_COL,
        "pop_col": POP_COL,
        "epsilon": EPSILON,
        "restarts": RESTARTS,
        "steps_per_restart": STEPS_PER_RESTART,
        "recom_probability": RECOM_PROBABILITY,
        "seat_weight": SEAT_WEIGHT,
        "pop_penalty_weight": POP_PENALTY_WEIGHT,
        "bp_kerulet_split_weight": BP_KERULET_SPLIT_WEIGHT,
        "duna_mixed_side_weight": DUNA_MIXED_SIDE_WEIGHT,
        "duna_internal_edge_weight": DUNA_INTERNAL_EDGE_WEIGHT,
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "districts": int(districts["uj_oevk"].nunique()),
        "target_won_districts": int(districts["target_wins"].sum()),
    }
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\\nKimenetek:")
    print(f"  {OUTPUT_DIR / 'recom_units_2026.geojson'}")
    print(f"  {OUTPUT_DIR / 'recom_districts_2026.geojson'}")
    print(f"  {OUTPUT_DIR / 'recom_optimalizalt_terkep.html'}")
    print(f"  {OUTPUT_DIR / 'metadata.json'}")


# Main

def main() -> None:
    print("ReCom-lite gerrymandering futás")
    print(f"Target:   {TARGET_COL}")
    print(f"Opponent: {OPPONENT_COL}")
    print(f"Input:    {INPUT_GEOJSON}")

    units = load_units(INPUT_GEOJSON)
    graph = build_graph(units)
    graph = connect_components_inside_counties(graph, units)

    units = units[units["_node"].isin(graph.nodes)].copy()

    result_units = optimize_all(units, graph)
    save_outputs(result_units, graph)

    print("\nKész.")


if __name__ == "__main__":
    main()
