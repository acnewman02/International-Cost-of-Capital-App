"""International Cost of Capital: self-contained Streamlit application.

Only app.py, requirements.txt, and README.md are needed in the GitHub repo.
All calculations use decimal yields/rates (0.065 = 6.5%).
Source failures produce clearly labelled dated reference values; manual overrides
remain available. Run with: streamlit run app.py
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO, StringIO
import re

import pandas as pd
import pycountry
import requests
import streamlit as st
from bs4 import BeautifulSoup

# -----------------------------------------------------------------------------
# 1. Pure financial calculations
# -----------------------------------------------------------------------------

def currency_convert_rate(rate_usd: float, rf_usd: float, rf_foreign: float) -> float:
    """Class formula: (1 + R*) = (1 + R) (1 + Rf*) / (1 + Rf)."""
    if rf_usd <= -1 or rf_foreign <= -1 or rate_usd <= -1:
        raise ValueError("Gross rates must be positive (rate > -100%).")
    return (1.0 + rate_usd) * (1.0 + rf_foreign) / (1.0 + rf_usd) - 1.0


def relever_beta(beta_unlevered: float, tax_rate: float, debt_share: float) -> float:
    """Hamada equation, with debt_share = D/(D+E) rather than D/E."""
    if not 0 <= debt_share < 1:
        raise ValueError("Debt share must be at least 0% and less than 100%.")
    if not 0 <= tax_rate <= 1:
        raise ValueError("Tax rate must be between 0% and 100%.")
    if beta_unlevered < 0:
        raise ValueError("Unlevered beta must not be negative.")
    debt_equity = debt_share / (1.0 - debt_share)
    return beta_unlevered * (1 + (1 - tax_rate) * debt_equity)


def calculate_cost_of_capital(
    beta_unlevered: float,
    tax_rate: float,
    debt_share: float,
    equity_risk_premium: float,
    rf_usd: float,
    rf_foreign: float,
    bbb_spread_usd: float,
    bbb_spread_foreign_override: float | None = None,
) -> dict[str, float]:
    """Calculate two currency-denominated discount rates for the *same* project.

    USD equity: US 10y + relevered beta * ERP.
    USD debt: US 10y + BBB spread.
    Foreign equity: class multiplicative conversion of USD equity.
    Foreign debt: same conversion of USD debt by default; a manually overridden
      foreign BBB spread instead defines local debt = local 10y + local spread.
    Each currency's WACC uses its own component rates, with one common tax rate.
    """
    if bbb_spread_usd < 0 or (bbb_spread_foreign_override is not None and bbb_spread_foreign_override < 0):
        raise ValueError("BBB borrowing spreads must be nonnegative.")
    beta_levered = relever_beta(beta_unlevered, tax_rate, debt_share)
    equity_share = 1.0 - debt_share

    ke_usd = rf_usd + beta_levered * equity_risk_premium
    kd_usd = rf_usd + bbb_spread_usd

    ke_foreign = currency_convert_rate(ke_usd, rf_usd, rf_foreign)
    kd_foreign_automatic = currency_convert_rate(kd_usd, rf_usd, rf_foreign)
    spread_foreign_automatic = kd_foreign_automatic - rf_foreign
    if bbb_spread_foreign_override is None:
        spread_foreign = spread_foreign_automatic
        kd_foreign = kd_foreign_automatic
    else:
        spread_foreign = bbb_spread_foreign_override
        kd_foreign = rf_foreign + spread_foreign

    wacc_usd = equity_share * ke_usd + debt_share * kd_usd * (1 - tax_rate)
    wacc_foreign = equity_share * ke_foreign + debt_share * kd_foreign * (1 - tax_rate)

    return {
        "beta_unlevered": beta_unlevered,
        "beta_levered": beta_levered,
        "tax_rate": tax_rate,
        "equity_share": equity_share,
        "debt_share": debt_share,
        "debt_equity": debt_share / equity_share,
        "rf_usd": rf_usd,
        "rf_foreign": rf_foreign,
        "equity_risk_premium": equity_risk_premium,
        "bbb_spread_usd": bbb_spread_usd,
        "bbb_spread_foreign_auto": spread_foreign_automatic,
        "bbb_spread_foreign": spread_foreign,
        "ke_usd": ke_usd,
        "ke_foreign": ke_foreign,
        "kd_usd": kd_usd,
        "kd_foreign": kd_foreign,
        "wacc_usd": wacc_usd,
        "wacc_foreign": wacc_foreign,
        "wacc_foreign_direct_conversion": currency_convert_rate(wacc_usd, rf_usd, rf_foreign),
    }


# -----------------------------------------------------------------------------
# 2. Public data sources and parsers
# -----------------------------------------------------------------------------

DAMODARAN_XLS = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
DAMODARAN_HTML = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html"
DAMODARAN_RATINGS = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html"
# This public workbook is the Excel Statlink attached to Figure 2.1 of
# OECD Corporate Tax Statistics 2026; it is a public download, not an API.
OECD_SOURCE = "https://www.oecd.org/en/publications/corporate-tax-statistics-2026_73af6222-en/full-report/statutory-corporate-income-tax-rates_ce84abb9.html"
OECD_SOURCE_2024 = "https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html"
OECD_EXCEL = "https://stat.link/mstq82"
# The /bonds page is browser/JavaScript rendered; the site also publishes
# an ordinary HTML table with the same government's 10-year yield series.
BONDS_SOURCE = "https://tradingeconomics.com/country-list/government-bond-10y"
BONDS_LANDING = "https://tradingeconomics.com/bonds"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StudentCostOfCapital/1.0; educational analysis)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,*/*;q=0.8",
}
DEFAULT_INDUSTRY = "Software (System & Application)"

# Source-verified 2026 references; NEVER represented as live observations.
FALLBACK_BETAS = {
    "Advertising": 0.93,
    "Aerospace/Defense": 0.85,
    "Computer Services": 0.92,
    "Environmental & Waste Services": 0.81,
    "Restaurant/Dining": 0.77,
    "Retail (General)": 0.76,
    "Semiconductor": 1.49,
    "Software (Entertainment)": 1.01,
    "Software (Internet)": 1.55,
    DEFAULT_INDUSTRY: 1.23,
    "Utility (General)": 0.15,
    "Utility (Water)": 0.28,
}
# Values below are a dated illustrative reference snapshot from TE (not live).
FALLBACK_BONDS_NOV_13_2026 = {
    "United States": 5.1590,
    "United Kingdom": 5.3529,
    "Japan": 2.8620,
    "Australia": 5.1480,
    "Germany": 3.3876,
    "Brazil": 15.4400,
    "India": 7.3120,
    "Canada": 3.8460,
    "Italy": 4.4440,
    "France": 4.9140,
    "South Africa": 8.7150,
    "China": 1.6181,
    "Switzerland": 0.5790,
    "Mexico": 9.2780,
    "Singapore": 2.3296,
    "South Korea": 4.0040,
    "Thailand": 1.9950,
    "Vietnam": 4.5726,
    "Indonesia": 7.6070,
}
# The US rate is explicitly available in OECD 2026 series; other entries are
# selected 2026 references from the OECD-linked compiled table / OECD-based
# secondary publications, and are ONLY offered when API is unavailable.
FALLBACK_TAX_2026 = {
    "United States": 25.53,
    "Australia": 30.0,
    "Germany": 30.1,
    "United Kingdom": 25.0,
    "Ireland": 12.5,
    "Italy": 27.8,
    "Mexico": 30.0,
    "Switzerland": 19.6,
}

COUNTRY_ALIASES = {
    "KOR": "South Korea", "TWN": "Taiwan", "HKG": "Hong Kong",
    "USA": "United States", "GBR": "United Kingdom", "VNM": "Vietnam",
    "CZE": "Czechia", "TUR": "Turkey", "RUS": "Russia",
    "SVK": "Slovakia", "IRN": "Iran", "LAO": "Laos",
    "BOL": "Bolivia", "VEN": "Venezuela", "MDA": "Moldova",
    "TZA": "Tanzania", "BRN": "Brunei", "EGY": "Egypt",
}
NAME_ALIASES = {
    "korea": "South Korea", "republic of korea": "South Korea", "south korea": "South Korea",
    "viet nam": "Vietnam", "vietnam": "Vietnam",
    "turkiye": "Turkey", "türkiye": "Turkey", "turkey": "Turkey",
    "russian federation": "Russia", "china, people's republic of": "China",
    "united states of america": "United States", "czech republic": "Czechia",
    "hong kong sar": "Hong Kong", "chinese taipei": "Taiwan",
}


def fetched_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=18)
    r.raise_for_status()
    return r.text


def canonical_country(name_or_code: str) -> str:
    text = str(name_or_code).strip()
    if text.upper() in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text.upper()]
    if text.lower() in NAME_ALIASES:
        return NAME_ALIASES[text.lower()]
    try:
        item = pycountry.countries.lookup(text)
        return COUNTRY_ALIASES.get(item.alpha_3, item.name)
    except LookupError:
        return text


def _header_label(value) -> str:
    """Collapse NBSPs, line breaks and formatting in spreadsheet/HTML headings."""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip().casefold()


def _extract_beta_rows(rows: list[list]) -> dict[str, float]:
    """Read a named table regardless of column order or introductory rows."""
    for header_idx, row in enumerate(rows[:150]):
        columns = [_header_label(v) for v in row]
        name_idx = next((i for i, value in enumerate(columns) if "industry name" in value), None)
        beta_idx = next((i for i, value in enumerate(columns)
                         if "unlevered beta" in value and "correct" not in value), None)
        if name_idx is None or beta_idx is None:
            continue
        results = {}
        for entry in rows[header_idx + 1:]:
            if max(name_idx, beta_idx) >= len(entry):
                continue
            industry = str(entry[name_idx]).strip()
            try:
                beta = float(str(entry[beta_idx]).replace(",", "").strip())
            except (ValueError, TypeError):
                continue
            if (industry and industry.casefold() not in ("nan", "none")
                    and "total market" not in industry.casefold() and 0 <= beta < 20):
                results[industry] = beta
        if len(results) >= 30:
            return results
    raise ValueError("Could not find a complete unlevered-beta industry table")


def parse_betas_excel(contents: bytes) -> dict[str, float]:
    """Damodaran files may have a title and multiple sheets before the actual table."""
    book = pd.ExcelFile(BytesIO(contents), engine="xlrd")
    problems = []
    for sheet in book.sheet_names:
        try:
            frame = pd.read_excel(book, sheet_name=sheet, header=None)
            result = _extract_beta_rows(frame.where(pd.notna(frame), None).values.tolist())
            if result:
                return result
        except (ValueError, KeyError, TypeError) as exc:
            problems.append(f"{sheet}: {exc}")
    raise ValueError("Damodaran workbook has no recognizable unlevered-beta table: " + "; ".join(problems)[:180])


def parse_betas_html(html: str) -> dict[str, float]:
    """Parse the official NYU 'Betas by Sector (US)' table, including NBSP headings."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = [[cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
                for tr in table.find_all("tr")]
        try:
            return _extract_beta_rows(rows)
        except ValueError:
            pass
    # Older Damodaran pages occasionally have inconsistent table markup.
    for frame in pd.read_html(StringIO(html), header=None):
        try:
            return _extract_beta_rows(frame.where(pd.notna(frame), None).values.tolist())
        except ValueError:
            pass
    raise ValueError("Damodaran HTML had no complete industry-beta table")


def get_betas() -> dict:
    errors = []
    # Primary source: the official downloadable NYU workbook provided in class.
    for url in (DAMODARAN_XLS, DAMODARAN_XLS.replace("pages.stern.nyu.edu", "www.stern.nyu.edu")):
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            betas = parse_betas_excel(response.content)
            return {"data": betas, "url": url, "vintage": "January 2026",
                    "fetched": fetched_at(), "status": "live",
                    "note": f"Official Damodaran Excel workbook, {len(betas)} unlevered industry betas"}
        except Exception as exc:
            errors.append(f"XLS: {str(exc)[:95]}")
    # Secondary source: same publisher, same U.S. industry-beta dataset in HTML.
    try:
        betas = parse_betas_html(get_html(DAMODARAN_HTML))
        return {"data": betas, "url": DAMODARAN_HTML, "vintage": "January 2026",
                "fetched": fetched_at(), "status": "live",
                "note": f"Official Damodaran HTML, {len(betas)} industry betas (Excel unavailable)"}
    except Exception as exc:
        errors.append(f"HTML: {str(exc)[:95]}")
    return {"data": FALLBACK_BETAS.copy(), "url": DAMODARAN_XLS,
            "vintage": "January 2026 dated reference SUBSET", "fetched": fetched_at(), "status": "reference",
            "note": "Full Damodaran data could not be fetched: all-industry comparison is incomplete. "
                    + "; ".join(errors)[:280]}


def parse_bbb_spread(html: str) -> float:
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        for i, cell in enumerate(cells):
            if re.search(r"\bBaa2\s*/\s*BBB\b", cell, re.I):
                for following in cells[i + 1:]:
                    found = re.search(r"(\d+(?:\.\d+)?)\s*%", following)
                    if found:
                        return float(found.group(1)) / 100.0
    # Fallback regex on stripped rendered document text for simple HTML variations.
    text = soup.get_text(" ", strip=True)
    found = re.search(r"Baa2\s*/\s*BBB\s+(\d+(?:\.\d+)?)\s*%", text, re.I)
    if found:
        return float(found.group(1)) / 100.0
    raise ValueError("Baa2/BBB spread could not be identified")


def get_bbb_spread() -> dict:
    try:
        val = parse_bbb_spread(get_html(DAMODARAN_RATINGS))
        return {"value": val, "url": DAMODARAN_RATINGS, "vintage": "January 2026", "fetched": fetched_at(), "status": "live", "note": "Baa2/BBB, LARGE nonfinancial service firms (left table)"}
    except Exception as err:
        return {"value": 0.0111, "url": DAMODARAN_RATINGS, "vintage": "January 2026 reference", "fetched": fetched_at(), "status": "reference", "note": "Live fetch failed: dated reference, not a live quote. " + str(err)[:140]}


def parse_oecd_csv(text: str) -> tuple[dict[str, float], dict[str, int]]:
    """OECD combined statutory corporate tax rates, general government.

    Expected filter selected by OECD's Data Explorer:
      FREQ = A; TARGETING = ST; INSTITUTIONAL_SECTOR = S13; measure = CIT_C
    Combined rates are percentage of taxable income (percentage points).
    """
    df = pd.read_csv(StringIO(text), low_memory=False)
    cols = {re.sub(r"\s+", "_", str(x).strip().upper()): x for x in df.columns}
    def col(name: str) -> str | None:
        return cols.get(name)
    needed = ("REF_AREA", "OBS_VALUE", "TIME_PERIOD")
    if any(col(x) is None for x in needed):
        raise ValueError("OECD CSV missing REF_AREA, OBS_VALUE or TIME_PERIOD")
    # Use identifiers rather than labels so we never confuse a central tax
    # rate with the requested combined (central+subcentral) statutory rate.
    for name, code in (("FREQ", "A"), ("TARGETING", "ST"), ("INSTITUTIONAL_SECTOR", "S13")):
        if col(name):
            df = df[df[col(name)].astype(str).str.upper().str.strip() == code]
    if col("MEASURE"):
        df = df[df[col("MEASURE")].astype(str).str.upper().str.strip() == "CIT_C"]
    if col("UNIT_MEASURE"):
        df = df[df[col("UNIT_MEASURE")].astype(str).str.upper().str.strip().isin(("PT_INC_TAX", "PT", "PERCENT"))]
    df = df.copy()
    df["_year"] = pd.to_numeric(df[col("TIME_PERIOD")], errors="coerce")
    df["_value"] = pd.to_numeric(df[col("OBS_VALUE")], errors="coerce")
    df = df.dropna(subset=["_year", "_value"])
    df = df[(df["_year"] >= 2025) & (df["_year"] <= 2100) & (df["_value"] >= 0) & (df["_value"] <= 70)]
    df = df.sort_values("_year").drop_duplicates(subset=[col("REF_AREA")], keep="last")
    values, years = {}, {}
    for _, row in df.iterrows():
        country = canonical_country(str(row[col("REF_AREA")]))
        values[country] = float(row["_value"])
        years[country] = int(row["_year"])
    if len(values) < 10 or "United States" not in values:
        raise ValueError(f"Expected 10+ OECD combined corporate tax rates incl. US; got {len(values)}")
    return values, years


def parse_oecd_excel(contents: bytes) -> dict[str, float]:
    """Parse the official OECD 2026 Figure 2.1 Statlink Excel export.

    The workbook is chart support data, rather than SDMX. Accept ISO3 codes or
    full country names and rates as percent-point figures, in any side-by-side
    table, with headings/title rows and extra metadata. Do not silently infer
    a central-government rate when the combined statutory series is absent.
    """
    book = pd.ExcelFile(BytesIO(contents))
    valid: dict[str, float] = {}
    for sheet in book.sheet_names:
        frame = pd.read_excel(book, sheet_name=sheet, header=None)
        # The 2026 Figure 2.1 publication has one point per jurisdiction.
        # Scan every column for recognized countries, with a numeric rate in
        # its adjoining column; this works with multi-column figure layouts.
        for line in frame.itertuples(index=False, name=None):
            for i in range(len(line) - 1):
                raw = line[i]
                if pd.isna(raw) or not isinstance(raw, str):
                    continue
                name = raw.strip()
                if not name or len(name) > 65:
                    continue
                country = canonical_country(name)
                try:
                    pycountry.countries.lookup(country)
                except LookupError:
                    if country not in ("South Korea", "Taiwan", "Hong Kong"):
                        continue
                raw_value = line[i + 1]
                if pd.isna(raw_value) or isinstance(raw_value, bool):
                    continue
                try:
                    if isinstance(raw_value, str):
                        raw_value = raw_value.replace("%", "").replace(",", "").strip()
                    rate = float(raw_value)
                except (ValueError, TypeError):
                    continue
                if 0 <= rate <= 70:
                    valid[country] = rate
    # Sometimes Excel stores all percentage rates as fractions 0.2553.
    if valid and sum(v <= 1 for v in valid.values()) / len(valid) > 0.9:
        valid = {k: 100 * v for k, v in valid.items()}
    if len(valid) < 15 or "United States" not in valid:
        raise ValueError(f"Official OECD workbook has only {len(valid)} recognizable country/rate pairs; expected 15+ incl. US")
    return valid


def get_oecd_taxes() -> dict:
    """Retrieve OECD statutory tax rates from its public 2026 figure workbook.

    No OECD API, API key, SDMX endpoint, or authentication is used.
    """
    try:
        r = requests.get(OECD_EXCEL, headers=HEADERS, timeout=25,
                         allow_redirects=True)
        r.raise_for_status()
        # A challenge page instead of Excel must not masquerade as source data.
        if r.content[:100].lstrip().lower().startswith((b"<!doctype", b"<html")):
            raise ValueError("OECD workbook link returned HTML instead of an Excel file")
        values = parse_oecd_excel(r.content)
        return {"data": values, "years": {k: 2026 for k in values},
                "url": OECD_EXCEL, "vintage": "OECD Corporate Tax Statistics 2026 (21 July 2026)",
                "fetched": fetched_at(), "status": "live",
                "note": "OECD 2026 Figure 2.1 Excel Statlink: combined central + sub-central statutory corporate tax rates; no API."}
    except Exception as exc:
        return {"data": FALLBACK_TAX_2026.copy(),
                "years": {k: 2026 for k in FALLBACK_TAX_2026}, "url": OECD_SOURCE,
                "vintage": "2026 partial REFERENCE, not a successful fetch",
                "fetched": fetched_at(), "status": "reference",
                "note": "OECD public workbook could not be retrieved or read; limited reference values only. "
                        "Use an official OECD Excel export in the upload control or override the rate. "
                        + str(exc)[:200]}


def parse_bonds_html(html: str) -> tuple[dict[str, float], dict[str, str]]:
    """Trading Economics public 'Government Bond 10y - By Country' table.

    Distinguish Last (actual) from Previous and forecasts. Ignore false country
    rows, e.g. 'Report', plus Euro area (not a sovereign country).
    """
    soup = BeautifulSoup(html, "html.parser")
    values, dates = {}, {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for header_row_idx, row in enumerate(rows):
            ths = [c.get_text(" ", strip=True).strip().lower() for c in row.find_all("th")]
            if not ths or not (any("country" in h for h in ths) and any("last" in h for h in ths)):
                continue
            # Header order can vary; match the named columns.
            country_col = next(i for i,h in enumerate(ths) if "country" in h)
            yield_col = next(i for i,h in enumerate(ths) if "last" in h)
            date_col = next((i for i,h in enumerate(ths) if "reference" in h), None)
            for tr in rows[header_row_idx + 1:]:
                tds = tr.find_all("td", recursive=False)
                if len(tds) <= max(country_col, yield_col):
                    continue
                cells = [c.get_text(" ", strip=True) for c in tds]
                original = cells[country_col].strip()
                country = canonical_country(original)
                if original.casefold() in ("report", "country list", "euro area"):
                    continue
                try:
                    pycountry.countries.lookup(country)
                except LookupError:
                    if country not in ("South Korea", "Taiwan", "Hong Kong"):
                        continue
                match = re.search(r"-?\d+(?:[.,]\d+)?", cells[yield_col])
                if not match:
                    continue
                value = float(match.group().replace(",", "."))
                if not (-10 <= value <= 100):
                    continue
                values[country] = value
                dates[country] = cells[date_col] if date_col is not None and date_col < len(cells) else "date not provided"
            if len(values) >= 8 and "United States" in values:
                return values, dates
    raise ValueError(f"Expected 8+ government bond 10y yield rows including US; got {len(values)}")


def get_bonds() -> dict:
    try:
        values, dates = parse_bonds_html(get_html(BONDS_SOURCE))
        return {"data": values, "dates": dates, "url": BONDS_SOURCE, "vintage": "Latest available by country (see reference month)", "fetched": fetched_at(), "status": "live", "note": "Trading Economics actual government 10-year yield (Last); Reference field is month, NOT an intraday quote timestamp"}
    except Exception as err:
        return {"data": FALLBACK_BONDS_NOV_13_2026.copy(), "dates": {k: "Nov/13/2026" if k not in ("Brazil", "Mexico") else "Nov/12/2026" for k in FALLBACK_BONDS_NOV_13_2026}, "url": BONDS_SOURCE, "vintage": "November 12–13, 2026 REFERENCE snapshot", "fetched": fetched_at(), "status": "reference", "note": "Unable to load the public 10-year bond table. These reference values are dated, NOT LIVE. Refresh or override inputs. " + str(err)[:180]}


# -----------------------------------------------------------------------------
# 3. Streamlit user interface
# -----------------------------------------------------------------------------

st.set_page_config(
    page_title="International Cost of Capital",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🌍 International Cost of Capital")
st.caption("Side-by-side project cost of equity, borrowing cost and WACC · U.S. dollars vs. local currency")


@st.cache_data(ttl=86400, show_spinner=False)
def cached_betas() -> dict:
    return get_betas()


@st.cache_data(ttl=86400, show_spinner=False)
def cached_spread() -> dict:
    return get_bbb_spread()


@st.cache_data(ttl=86400, show_spinner=False)
def cached_taxes() -> dict:
    return get_oecd_taxes()


@st.cache_data(ttl=3600, show_spinner=False)
def cached_bonds() -> dict:
    return get_bonds()


with st.sidebar:
    st.header("Project assumptions")
    if st.button("🔄 Refresh all source data", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Checking Damodaran, OECD and Trading Economics data..."):
    betas_source = cached_betas()
    spread_source = cached_spread()
    taxes_source = cached_taxes()
    bonds_source = cached_bonds()

# If an external website blocks automatic retrieval, an official-source export
# can still satisfy the 'latest available data' requirement when its vintage
# is independently verified by the user. Do not mislabel uploads as live feeds.
with st.sidebar:
    with st.expander("Optional: import official source exports"):
        beta_upload = st.file_uploader("Damodaran US betas.xls", type=["xls"], key="beta_upload")
        tax_upload = st.file_uploader("OECD 2026 combined-tax Excel workbook (or OECD CSV)", type=["xlsx", "xls", "csv"], key="tax_upload")
if beta_upload is not None:
    try:
        uploaded_betas = parse_betas_excel(beta_upload.getvalue())
        betas_source = {"data": uploaded_betas, "url": DAMODARAN_XLS,
                        "vintage": "User-uploaded official file (verify publication date)",
                        "fetched": fetched_at(), "status": "upload",
                        "note": f"Loaded {len(uploaded_betas)} industries from file; verify its official vintage."}
    except Exception as exc:
        st.error(f"Could not parse uploaded Damodaran file: {exc}")
if tax_upload is not None:
    try:
        if tax_upload.name.lower().endswith(".csv"):
            uploaded_taxes, uploaded_years = parse_oecd_csv(tax_upload.getvalue().decode("utf-8-sig"))
        else:
            uploaded_taxes = parse_oecd_excel(tax_upload.getvalue())
            uploaded_years = {name: 2026 for name in uploaded_taxes}
        taxes_source = {"data": uploaded_taxes, "years": uploaded_years,
                        "url": OECD_SOURCE, "vintage": f"User-uploaded OECD dataset (marked year {max(uploaded_years.values())}; not verified by app)",
                        "fetched": fetched_at(), "status": "upload",
                        "note": f"OECD source file uploaded for {len(uploaded_taxes)} countries. The file date is not independently authenticated by the app."}
    except Exception as exc:
        st.error(f"Could not parse uploaded OECD CSV: {exc}")

betas = betas_source["data"]
taxes = taxes_source["data"]
bonds = bonds_source["data"]

with st.sidebar:
    industry_options = sorted(betas)
    industry_default = industry_options.index(DEFAULT_INDUSTRY) if DEFAULT_INDUSTRY in industry_options else 0
    industry = st.selectbox("Industry (Damodaran U.S. dataset)", industry_options, index=industry_default)
    country_options = ["United States"] + sorted((set(taxes) | set(bonds)) - {"United States"}) + ["Other (manual country)"]
    country_choice = st.selectbox("Target country", country_options, index=0)
    country = country_choice
    if country_choice == "Other (manual country)":
        country = st.text_input("Enter country name (manual source overrides may be needed)").strip()
        if not country:
            st.info("Enter the name of the country to continue.")
            st.stop()

    st.divider()
    erp_pct = st.slider("Equity risk premium (USD)", min_value=0.0, max_value=20.0, value=6.5, step=0.1, format="%.1f%%")
    debt_pct = st.slider("Target debt / total capital", min_value=0, max_value=95, value=30, step=1, format="%d%%")
    tax_basis = st.segmented_control(
        "One project tax rate for BOTH currencies",
        ["U.S. statutory rate", "Target-country statutory rate"],
        default="U.S. statutory rate", required=True,
    )

    st.divider()
    st.subheader("Live inputs & optional overrides")
    st.caption("All displayed numeric inputs are in percent (%) except unlevered beta.")

    original_beta = float(betas[industry])
    if st.toggle("Manually override unlevered beta", value=False):
        unlevered_beta = st.number_input("Unlevered beta", min_value=0.0, max_value=20.0, value=original_beta, step=0.01, format="%.3f", key=f"manual_beta_{industry}")
    else:
        unlevered_beta = original_beta
        st.caption(f"Auto unlevered beta: **{unlevered_beta:.3f}**")

    us_tax_auto = float(taxes.get("United States", 25.53))
    country_tax_auto = taxes.get(country)
    us_tax_manual = st.toggle("Manually override U.S. tax rate", value=False)
    if us_tax_manual:
        us_tax_pct = st.number_input("U.S. combined corporate tax rate (%)", min_value=0.0,
                                     max_value=100.0, value=us_tax_auto, step=0.1,
                                     format="%.2f", key="us_tax_entry")
    else:
        us_tax_pct = us_tax_auto
        st.caption(f"Auto U.S. corporate tax rate: **{us_tax_pct:.2f}%**")

    country_tax_manual = st.toggle("Manually override target-country tax rate", value=False)
    if country == "United States" and not country_tax_manual:
        country_tax_pct = us_tax_pct
        st.caption(f"Auto {country} corporate tax rate: **{country_tax_pct:.2f}%**")
    elif country_tax_manual:
        country_tax_pct = st.number_input(
            f"{country} corporate tax rate (%)", min_value=0.0, max_value=100.0,
            value=float(country_tax_auto if country_tax_auto is not None else 0.0),
            step=0.1, format="%.2f", key=f"country_tax_entry_{country}",
        )
    elif country_tax_auto is None:
        country_tax_pct = 0.0
        st.warning(f"No OECD tax rate found for {country}. Switch to the U.S. tax basis, upload an official OECD file, or enable a manual rate.")
    else:
        country_tax_pct = float(country_tax_auto)
        st.caption(f"Auto {country} corporate tax rate: **{country_tax_pct:.2f}%**")
    if country_tax_auto is None and country != "United States" and tax_basis == "Target-country statutory rate" and not country_tax_manual:
        st.error("Selected country tax rate is missing. Choose U.S. statutory rate or enable target-country override.")
        st.stop()
    tax_pct = us_tax_pct if tax_basis == "U.S. statutory rate" else country_tax_pct

    bbb_auto_pct = float(spread_source["value"]) * 100
    bbb_us_manual = st.toggle("Manually override USD BBB spread", value=False)
    if bbb_us_manual:
        bbb_us_pct = st.number_input("USD BBB borrowing spread (%)", min_value=0.0,
                                      max_value=50.0, value=bbb_auto_pct,
                                      step=0.05, format="%.3f")
    else:
        bbb_us_pct = bbb_auto_pct
        st.caption(f"Auto USD BBB spread: **{bbb_us_pct:.3f}%**")

    usd_yield_auto = bonds.get("United States")
    target_yield_auto = bonds.get(country)
    usd_yield_manual = st.toggle("Manually override U.S. 10-year yield", value=usd_yield_auto is None)
    if usd_yield_manual:
        rf_us_pct = st.number_input("U.S. 10-year government yield (%)", min_value=-10.0,
                                    max_value=100.0, value=float(usd_yield_auto or 0.0),
                                    step=0.05, format="%.4f")
    elif usd_yield_auto is None:
        st.error("U.S. 10-year yield unavailable. Enable manual override before calculating.")
        st.stop()
    else:
        rf_us_pct = float(usd_yield_auto)
        st.caption(f"Auto U.S. 10-year government yield: **{rf_us_pct:.4f}%**")

    target_yield_manual = st.toggle(f"Manually override {country} 10-year yield", value=target_yield_auto is None)
    if target_yield_manual:
        target_yield_default = rf_us_pct if country == "United States" else float(target_yield_auto or 0.0)
        rf_country_pct = st.number_input(
            f"{country} 10-year government yield (%)", min_value=-10.0, max_value=100.0,
            value=target_yield_default, step=0.05, format="%.4f")
    elif country == "United States":
        rf_country_pct = rf_us_pct
        st.caption(f"Auto {country} 10-year government yield: **{rf_country_pct:.4f}%**")
    elif target_yield_auto is None:
        st.error(f"{country} 10-year yield unavailable. Enable a manual override before calculating.")
        st.stop()
    else:
        rf_country_pct = float(target_yield_auto)
        st.caption(f"Auto {country} 10-year government yield: **{rf_country_pct:.4f}%**")

# Compute automatic local BBB spread before displaying its override field.
auto_result = calculate_cost_of_capital(
    beta_unlevered=unlevered_beta, tax_rate=tax_pct / 100,
    debt_share=debt_pct / 100, equity_risk_premium=erp_pct / 100,
    rf_usd=rf_us_pct / 100, rf_foreign=rf_country_pct / 100,
    bbb_spread_usd=bbb_us_pct / 100,
)
with st.sidebar:
    local_spread_manual = st.toggle("Manually override foreign BBB spread", value=False)
    auto_spread_pct = float(auto_result["bbb_spread_foreign_auto"] * 100)
    if local_spread_manual:
        local_spread_pct = st.number_input(
            f"{country} BBB borrowing spread (%)", min_value=0.0, max_value=50.0,
            value=auto_spread_pct, step=0.05, format="%.4f",
            help="This override changes only the foreign-currency borrowing rate.")
    else:
        local_spread_pct = auto_spread_pct
        st.caption(f"Automatically calculated {country} BBB spread: **{local_spread_pct:.4f}%**")

result = calculate_cost_of_capital(
    beta_unlevered=unlevered_beta, tax_rate=tax_pct / 100,
    debt_share=debt_pct / 100, equity_risk_premium=erp_pct / 100,
    rf_usd=rf_us_pct / 100, rf_foreign=rf_country_pct / 100,
    bbb_spread_usd=bbb_us_pct / 100,
    bbb_spread_foreign_override=local_spread_pct / 100 if local_spread_manual else None,
)

for name, src in (("Industry beta", betas_source), ("BBB spread", spread_source), ("Corporate tax", taxes_source), ("10-year yields", bonds_source)):
    if src["status"] == "reference":
        st.warning(f"{name}: {src['vintage']} **REFERENCE / NOT LIVE**. {src['note']}")
    elif src["status"] == "upload":
        st.info(f"{name}: **OFFICIAL FILE UPLOAD — DATE UNVERIFIED**. {src['note']}")

st.markdown(f"**Industry:** {industry}  ·  **Target country:** {country}  ·  **Tax basis:** {tax_basis}")
st.caption(f"Levered beta {result['beta_levered']:.3f}  ·  Debt/Equity {result['debt_equity']:.2%}  ·  ERP {erp_pct:.2f}%  ·  Project tax rate {tax_pct:.2f}%")

usd_col, local_col = st.columns(2, gap="large")
with usd_col:
    st.subheader("🇺🇸 U.S. dollars (USD)")
    st.metric("Cost of equity", f"{result['ke_usd']:.2%}")
    st.metric("Pre-tax cost of debt", f"{result['kd_usd']:.2%}")
    st.metric("WACC", f"{result['wacc_usd']:.2%}")
with local_col:
    st.subheader(f"🌐 {country} (local currency)")
    st.metric("Cost of equity", f"{result['ke_foreign']:.2%}")
    st.metric("Pre-tax cost of debt", f"{result['kd_foreign']:.2%}")
    st.metric("WACC", f"{result['wacc_foreign']:.2%}", delta=f"{(result['wacc_foreign'] - result['wacc_usd']) * 10000:+.1f} bp vs. USD", delta_color="off")

st.subheader("Calculation breakdown")
comparison = pd.DataFrame([
    {"Component": "10-year government yield", "USD": result["rf_usd"], "Local currency": result["rf_foreign"]},
    {"Component": "Unlevered beta", "USD": result["beta_unlevered"], "Local currency": result["beta_unlevered"]},
    {"Component": "Relevered beta", "USD": result["beta_levered"], "Local currency": result["beta_levered"]},
    {"Component": "BBB borrowing spread", "USD": result["bbb_spread_usd"], "Local currency": result["bbb_spread_foreign"]},
    {"Component": "Pre-tax cost of debt", "USD": result["kd_usd"], "Local currency": result["kd_foreign"]},
    {"Component": "After-tax cost of debt", "USD": result["kd_usd"] * (1-result["tax_rate"]), "Local currency": result["kd_foreign"] * (1-result["tax_rate"])},
    {"Component": "Cost of equity", "USD": result["ke_usd"], "Local currency": result["ke_foreign"]},
    {"Component": "WACC", "USD": result["wacc_usd"], "Local currency": result["wacc_foreign"]},
])
rate_rows = ["10-year government yield", "BBB borrowing spread", "Pre-tax cost of debt", "After-tax cost of debt", "Cost of equity", "WACC"]
comparison_display = comparison.copy()
for c in ("USD", "Local currency"):
    comparison_display[c] = [f"{v:.3%}" if label in rate_rows else f"{v:.3f}" for label, v in zip(comparison["Component"], comparison[c])]
st.dataframe(comparison_display, use_container_width=True, hide_index=True)

with st.expander("Formulas, assumptions and currency-conversion interpretation", expanded=True):
    st.markdown("**1. Relever the industry beta** using the same tax rate and capital structure in both currencies:")
    st.latex(r"\beta_L = \beta_U\left[1+(1-T)\frac{D}{E}\right],\quad \frac{D}{E}=\frac{D/V}{1-D/V}")
    st.markdown("**2. Calculate USD equity and pre-tax borrowing costs:**")
    st.latex(r"R_{e,USD} = R_{f,USD} + \beta_L ERP,\quad R_{d,USD}=R_{f,USD}+s_{BBB,USD}")
    st.markdown("**3. Apply the class's compound-rate currency conversion** separately to equity and pre-tax debt:")
    st.latex(r"R^{*}=\left(1+R\right)\frac{1+R_f^{*}}{1+R_f}-1")
    st.markdown("**4. Automatic foreign BBB spread:** convert the USD borrowing rate and subtract the foreign government yield. A manual foreign-spread override only replaces local debt cost.")
    st.latex(r"s_{BBB,*}^{auto}=\left[(1+R_{d,USD})\frac{1+R_{f,*}}{1+R_{f,USD}}-1\right]-R_{f,*}")
    st.markdown("**5. Recalculate WACC** from local equity and debt components, with the same chosen project tax rate:")
    st.latex(r"WACC_c=\frac{E}{V}R_{e,c}+\frac{D}{V}R_{d,c}(1-T)")
    st.markdown("**Class assumptions underlying the Hamada beta and WACC equations:**")
    st.markdown(
        "- **Fixed amount of perpetual debt:** used to justify Hamada-style beta relevering; "
        "the app displays a *point-in-time* WACC at the selected debt share, not a multi-year debt schedule.\n"
        "- **Constant project corporate tax rate:** the selected tax rate is shared between currencies "
        "and used both for beta relevering and WACC.\n"
        "- **Interest deductions fully usable when incurred:** the whole current-period interest tax "
        "shield is modeled with the `(1-T)` multiplier on the debt contribution to WACC.\n"
        "- **Debt beta and tax-shield beta are zero:** these simplify the relevering equation to "
        "`beta_E = beta_U × [1 + (1−T) × D/E]`. The required BBB borrowing spread is still "
        "included in quoted borrowing costs, but not as an additional debt beta."
    )
    st.caption(
        "Important scope: fixed dollar debt does not imply a fixed debt-to-value ratio as enterprise "
        "value changes over time. This app computes a cost-of-capital snapshot, not an APV or "
        "multi-period valuation. A positive BBB borrowing spread with beta_D = 0 is treated "
        "as a borrowing-yield premium, not systematic CAPM risk compensation."
    )
    st.info(
        "Model choices: 10-year government yields proxy for currency risk-free rates. "
        "USD ERP and U.S. industry beta are held constant; the selected-country risk-free yield is the only automatic currency adjustment. "
        "No extra country-risk premium is added. Government yields in higher-risk countries may contain sovereign credit risk. "
        "Corporate taxes are combined statutory, not company-specific effective tax rates. "
        "The local WACC is built from local components, not obtained by directly converting USD WACC; "
        "the two generally differ slightly because the debt tax shield affects the weighted average."
    )
    st.caption(f"For reference, direct conversion of the **USD WACC as one rate** would be {result['wacc_foreign_direct_conversion']:.3%}, compared with component-based local WACC of {result['wacc_foreign']:.3%}.")

st.subheader("All-industry comparison")
st.caption("All industry betas use the same selected capital structure, rates, ERP and single project tax rate. Only the currently selected industry's beta is affected by its manual override.")
all_rows = []
for industry_name, beta_value in sorted(betas.items()):
    beta_this = unlevered_beta if industry_name == industry else float(beta_value)
    calc = calculate_cost_of_capital(
        beta_unlevered=beta_this, tax_rate=tax_pct / 100,
        debt_share=debt_pct / 100, equity_risk_premium=erp_pct / 100,
        rf_usd=rf_us_pct / 100, rf_foreign=rf_country_pct / 100,
        bbb_spread_usd=bbb_us_pct / 100,
        bbb_spread_foreign_override=local_spread_pct / 100 if local_spread_manual else None,
    )
    all_rows.append({
        "Industry": industry_name,
        "Unlevered beta": beta_this,
        "Levered beta": calc["beta_levered"],
        "USD cost of equity (%)": calc["ke_usd"] * 100,
        "Local cost of equity (%)": calc["ke_foreign"] * 100,
        "USD cost of debt (%)": calc["kd_usd"] * 100,
        "Local cost of debt (%)": calc["kd_foreign"] * 100,
        "USD WACC (%)": calc["wacc_usd"] * 100,
        "Local WACC (%)": calc["wacc_foreign"] * 100,
    })
industry_table = pd.DataFrame(all_rows).sort_values("USD WACC (%)", ascending=False)
comparison_option = st.radio("Sort industries", ["Highest USD WACC first", "Lowest USD WACC first", "Alphabetical"], horizontal=True)
if comparison_option == "Lowest USD WACC first":
    industry_table = industry_table.sort_values("USD WACC (%)")
elif comparison_option == "Alphabetical":
    industry_table = industry_table.sort_values("Industry")
st.dataframe(industry_table.style.format({c: "{:.2f}" for c in industry_table.columns if c != "Industry"}), hide_index=True, use_container_width=True, height=370)
shown = industry_table.head(15).set_index("Industry")[["USD WACC (%)", "Local WACC (%)"]]
st.bar_chart(shown, horizontal=True, x_label="WACC (%)", y_label="Industry")
if betas_source["status"] == "reference":
    st.warning("Full-industry comparison is currently INCOMPLETE (reference subset only). Import an official Damodaran XLS or retry source refresh.")

st.subheader("Source provenance and data dates")
source_rows = []
for label, item in [
    ("U.S. industry unlevered betas", betas_source),
    ("U.S. BBB credit spread", spread_source),
    ("Combined statutory tax rates (OECD 2026)", taxes_source),
    ("10-year government bond yields", bonds_source),
]:
    source_rows.append({"Input": label, "Type": {"live": "SOURCE FETCH", "upload": "FILE UPLOAD — DATE UNVERIFIED", "reference": "DATED REFERENCE"}.get(item["status"], "UNKNOWN"), "Data vintage": item["vintage"], "Retrieved at (UTC)": item["fetched"], "Source URL": item["url"]})
st.dataframe(pd.DataFrame(source_rows), hide_index=True, use_container_width=True)
if bonds_source["status"] == "live":
    observed_month = bonds_source.get("dates", {}).get(country, "")
    st.caption(f"Selected country's Trading Economics 'Reference' period: **{observed_month or 'not supplied'}**. Check the reference period before interpreting it as current.")
st.caption(f"Trading Economics quote dates: United States — {bonds_source['dates'].get('United States', 'not reported')}; {country} — {bonds_source['dates'].get(country, 'not reported')}. OECD tax vintage: United States — {taxes_source['years'].get('United States', 'missing')}; {country} — {taxes_source['years'].get(country, 'missing')}. Source quotes are refreshed at page load up to the data-cache TTL, or immediately via Refresh.")
st.markdown("Official source links: [Damodaran industry betas XLS](%s) · [Damodaran BBB spread](%s) · [OECD 2026 corporate tax report](%s) · [OECD 2026 supporting workbook](%s) · [Trading Economics 10Y yields](%s)" % (DAMODARAN_XLS, DAMODARAN_RATINGS, OECD_SOURCE, OECD_EXCEL, BONDS_SOURCE))

st.subheader("Downloadable results")
inputs = {
    "Industry": industry, "Country": country, "Tax basis": tax_basis,
    "Unlevered beta": unlevered_beta, "Levered beta": result["beta_levered"],
    "Tax rate (%)": tax_pct, "Equity risk premium (%)": erp_pct,
    "Debt financing (%)": debt_pct, "U.S. 10Y yield (%)": rf_us_pct,
    "Foreign 10Y yield (%)": rf_country_pct, "U.S. BBB spread (%)": bbb_us_pct,
    "Auto foreign BBB spread (%)": result["bbb_spread_foreign_auto"] * 100,
    "Applied foreign BBB spread (%)": result["bbb_spread_foreign"] * 100,
    "Foreign BBB override used": local_spread_manual,
    "Model assumptions": "Fixed perpetual debt (beta convention); constant project tax rate; fully usable interest tax shield; debt beta = 0; tax-shield beta = 0; point-in-time target debt share",
    "USD cost of equity (%)": result["ke_usd"] * 100,
    "Foreign cost of equity (%)": result["ke_foreign"] * 100,
    "USD pre-tax cost of debt (%)": result["kd_usd"] * 100,
    "Foreign pre-tax cost of debt (%)": result["kd_foreign"] * 100,
    "USD WACC (%)": result["wacc_usd"] * 100,
    "Foreign WACC (%)": result["wacc_foreign"] * 100,
}
notes = " | ".join(f"{label}: {src['url']} ({src['vintage']}, {src['status']}, fetched {src['fetched']})" for label, src in [
    ("beta", betas_source), ("credit", spread_source), ("tax", taxes_source), ("bonds", bonds_source),
])
inputs["Sources"] = notes
c1, c2 = st.columns(2)
with c1:
    st.download_button("⬇ Download selected project (CSV)", pd.DataFrame([inputs]).to_csv(index=False), "cost_of_capital_selected.csv", "text/csv", use_container_width=True)
with c2:
    st.download_button("⬇ Download all industries (CSV)", industry_table.assign(Country=country, **{"Tax rate (%)": tax_pct, "BBB source status": spread_source['status'], "Beta source status": betas_source['status']}).to_csv(index=False), "cost_of_capital_all_industries.csv", "text/csv", use_container_width=True)

with st.expander("Built-in verification checks"):
    checks = []
    shared = dict(beta_unlevered=1.23, tax_rate=0.2553, debt_share=0.30, equity_risk_premium=0.065, rf_usd=0.05, rf_foreign=0.05, bbb_spread_usd=0.0111)
    equal = calculate_cost_of_capital(**shared)
    checks.append(("Equal risk-free yields ⇒ equal costs and WACC", all(abs(equal[a] - equal[b]) < 1e-12 for a, b in [("ke_usd", "ke_foreign"), ("kd_usd", "kd_foreign"), ("wacc_usd", "wacc_foreign")])) )
    no_debt = calculate_cost_of_capital(**{**shared, "debt_share": 0, "rf_foreign": 0.03})
    checks.append(("Zero debt ⇒ WACC equals equity cost in each currency", abs(no_debt["wacc_usd"] - no_debt["ke_usd"]) < 1e-12 and abs(no_debt["wacc_foreign"] - no_debt["ke_foreign"]) < 1e-12))
    a = calculate_cost_of_capital(**{**shared, "rf_foreign": 0.03})
    b = calculate_cost_of_capital(**{**shared, "rf_foreign": 0.03}, bbb_spread_foreign_override=0.04)
    checks.append(("Foreign BBB override changes local debt/WACC but not USD results", abs(a["wacc_usd"] - b["wacc_usd"]) < 1e-12 and abs(a["kd_usd"] - b["kd_usd"]) < 1e-12 and abs(a["wacc_foreign"] - b["wacc_foreign"]) > 1e-5))
    for label, passed in checks:
        st.write(("✅" if passed else "❌") + " " + label)
    st.caption("These are deterministic checks of financial formulas, NOT tests of live web scraping. Independently compare a numerical example to a calculator before submitting.")
