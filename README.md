# International Cost of Capital — Streamlit app

This repository contains **exactly three required files**, with all application code in
`app.py`. It compares the **cost of equity, pre-tax cost of debt, and WACC** for
one project in USD and the local currency of a selected country.

The app uses the class formula:

```text
(1 + R_foreign) = (1 + R_USD) × (1 + Rf_foreign) / (1 + Rf_USD)
```

There is **no API key** and no need for a separate `finance.py` or
`data_sources.py` file. Note: Trading Economics and OECD may enforce access
restrictions or temporarily return errors; a public website's being readable in a
browser does **not** guarantee that automated server-to-server requests work.
When an official source fails, the app labels fallbacks rather than pretending
that dated values are live.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit interface, web data-fetching/parsing, financial math, charts, and CSV downloads |
| `requirements.txt` | Dependencies for installation on Streamlit Community Cloud |
| `README.md` | Instructions, formulas, data sources, assumptions, and verification |

## Run locally

Use Python 3.11 or later:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Visit the local URL printed by Streamlit.

## Deploy to Streamlit Community Cloud

1. Create a new GitHub repository (for example, `international-cost-of-capital`).
2. At the **top level** of the repository, add these three files **without**
   nesting them in a folder.
3. Open https://share.streamlit.io and choose **Create app**.
4. Choose your GitHub repository and branch; set **Main file path** to `app.py`.
5. Select **Deploy**. No API secrets are required.
6. In the running app, press **Refresh all source data**. Verify the data
   provenance table and ensure all necessary values are live or explicitly
   supported by dated references/manual inputs.
7. Complete the three built-in verification checks and independently recalculate
   one numerical case. Submit the repository URL, deployed URL, screenshots of
   your real AI conversations, and a note describing your independent check.

## Features and startup defaults

- **Industry:** Software (System & Application)
- **Country:** United States
- **Project tax basis:** U.S. combined statutory corporate income tax rate
- **Equity risk premium:** 6.5%
- **Target debt financing:** 30% of total capital
- **Live sourcing:** Damodaran U.S. industry unlevered betas and BBB credit spread;
  OECD combined statutory corporate tax rates; Trading Economics 10-year
  government yields
- **Manual overrides:** unlevered beta, U.S. and target-country corporate tax
  rates, USD BBB spread, U.S. and target-country 10-year yields, and foreign BBB spread
- **Results:** USD and foreign cost of equity, pre-tax debt cost and WACC; source
  dates and links; all-industry table/chart; downloadable CSVs

The foreign BBB spread field is auto-calculated until its override is enabled.
The app also permits entry of a country not present in the retrieved lists.

## Financial model

All rates are **decimal fractions** internally (e.g., 6.5% is `0.065`).
`D/V` is the debt-to-total-capital weight; `T` is **one project tax rate** used
in both currencies.

```text
D/E = (D/V) / (1 - D/V)
Levered beta = Unlevered beta × [1 + (1 - T) × D/E]
Cost of equity (USD) = 10Y U.S. government yield + Levered beta × USD ERP
Cost of debt (USD) = 10Y U.S. government yield + USD BBB borrowing spread

Cost of equity (foreign) = (1 + Cost of equity USD)
                           × (1 + 10Y foreign yield) / (1 + 10Y U.S. yield) - 1
Cost of debt (foreign, automatic) = (1 + Cost of debt USD)
                                    × (1 + 10Y foreign yield) / (1 + 10Y U.S. yield) - 1
Foreign BBB spread (automatic) = Cost of debt (foreign, automatic) - 10Y foreign yield

If foreign spread is overridden:
    Cost of debt (foreign) = 10Y foreign yield + Foreign BBB spread (manual)

WACC in each currency = (E/V) × Cost of equity
                        + (D/V) × Cost of debt × (1 - T)
```

The headline **foreign WACC is built from separately converted equity and debt
components**, not by directly converting USD WACC. The app shows that alternative
for comparison because the results can differ due to the interest tax shield.
Confirm that component-based treatment matches the intended convention from class.

### Class assumptions

- **Constant amount of perpetual debt:** the Hamada equity beta equation reflects
  a fixed-debt, perpetual-tax-shield convention. The app provides a
  **point-in-time** cost-of-capital snapshot at a target debt share; it does **not**
  forecast dollar debt balances over time. Constant-dollar debt does not mean
  the debt-to-value ratio remains constant when enterprise value changes.
- **Constant project tax rate:** one selected rate applies to the leverage
  adjustment and both currency WACCs.
- **Full immediate usability of interest deductions:** after-tax debt cost
  is `Kd × (1-T)` without restrictions or carryforward adjustments.
- **Debt beta and tax-shield beta of zero:** debt/tax-shield betas do not
  enter the equity beta relevering formula. Following the assignment, the
  required BBB borrowing yield spread is included in `Kd`; it is not treated
  as debt systematic beta. A zero beta for debt under strict CAPM implies zero
  systematic *expected-return* premium, so this is an explicit classroom
  borrowing-yield convention.

**Scope limits:** U.S. industry betas and a USD ERP are used for all countries.
10-year sovereign yields are proxies for currency risk-free rates; some include
sovereign credit premia. The model does not separately add country risk premia,
model cross-border tax treatment or forecast FX rates.

## Input data and update dates (no API or API keys)

The app **retrieves publicly posted datasets and HTML tables directly**. It does
not use the OECD SDMX API, a Trading Economics API, or API credentials.

| Data | Official source | Retrieval approach | Publication/reference period |
| --- | --- | --- | --- |
| U.S. industry unlevered beta | [Damodaran betas.xls](https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls) | Download Excel and locate the `Unlevered beta` column; fall back to [Damodaran's U.S. HTML industry table](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html). | Jan 2026 |
| USD BBB spread | [Damodaran synthetic ratings](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html) | Parse Baa2/BBB in the **large non-financial service firms** part of the table. | Jan 2026 |
| Corporate income tax | [OECD Statutory Corporate Income Tax Rates 2026](https://www.oecd.org/en/publications/corporate-tax-statistics-2026_73af6222-en/full-report/statutory-corporate-income-tax-rates_ce84abb9.html), [official Figure 2.1 Excel](https://stat.link/mstq82) | Download the OECD report's Excel chart support data. Parse country/combined-rate pairs; no SDMX/API request. If the workbook is inaccessible, upload that workbook through the sidebar (or manually override). | Report published July 21, 2026; tax data 2026 |
| 10-year government yields | [Trading Economics 10Y Country Table](https://tradingeconomics.com/country-list/government-bond-10y), linked to the assignment's [bond overview](https://tradingeconomics.com/bonds) | Scrape table's **Last** (not Previous/Forecast), country and Reference month; no API key. | Latest posted observations; the reference period varies by country |

The course link to [OECD Corporate Tax Statistics 2024](https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html) is useful for methodology, but the 2026 OECD publication is newer and more appropriate for the requirement to use latest available data.

**Source transparency:** Data status is marked `SOURCE FETCH`, `FILE UPLOAD — DATE UNVERIFIED`, or `DATED REFERENCE`, with its published/reference period and retrieval timestamp. This is not real-time yield streaming: a successfully scraped bond yield is **the most recent value published on that table**, and the country Reference field can be only month/year. Verify it against the original page when preparing the assignment.

**Important:** A public website readable in a browser may still reject Streamlit-hosted requests. The app does not silently call outside services, pretend a fallback is current, or manufacture a missing full-industry list. If any automatic retrieval fails, you can upload the latest official Damodaran XLS or OECD Excel, and use manual input overrides for Treasury yields or spreads. The all-industry comparison is *incomplete* unless the full Damodaran beta data are fetched or uploaded.

## Independent verification example

Use the following **illustrative manual inputs** to verify the math by hand,
separate from live market data:

```text
Unlevered beta = 1.23              Project tax rate = 25.53%
Debt weight = 30.00%                USD equity risk premium = 6.50%
USD 10-year yield = 5.00%          Foreign 10-year yield = 3.00%
USD BBB spread = 1.11%             Foreign BBB spread override = OFF

Debt / equity = 0.30 / 0.70 = 0.428571
Levered beta = 1.23 × [1 + (1 - 0.2553) × (0.30 / 0.70)] = 1.622563
USD equity cost = 5.00% + 1.622563 × 6.50% = 15.5467%
USD debt cost = 5.00% + 1.11% = 6.1100%
USD WACC = 0.70 × 15.5467% + 0.30 × 6.1100% × (1 - 0.2553) = 12.2477%

Foreign equity cost = 1.1554666 × 1.03 / 1.05 - 1 = 13.3458%
Foreign debt cost = 1.0611 × 1.03 / 1.05 - 1 = 4.0889%
Automatic foreign BBB spread = 4.0889% - 3.00% = 1.0889%
Foreign WACC = 0.70 × 13.3458% + 0.30 × 4.0889% × (1 - 0.2553) = 10.2555%
```

This example is a checkable numerical illustration, **not** a statement of the
latest live rates.

The app has built-in checks for the three required invariants:

1. Equal government yields → equal USD and foreign results when all other
   inputs are held constant and foreign BBB override is OFF.
2. Zero debt → WACC equals cost of equity in each currency.
3. Manual foreign BBB spread override → affects foreign debt/WACC but does **not**
   change USD calculations.

## Submission checklist

- [ ] GitHub repository URL and running Streamlit app URL
- [ ] Source-vintage table reviewed; no unacknowledged reference-rate fallbacks
- [ ] Verify one numerical example with a calculator or spreadsheet
- [ ] Confirm the three built-in invariant tests
- [ ] Add screenshots of the real AI conversation(s)
- [ ] Explain one AI-generated result or design choice you independently checked

## Troubleshooting source warnings

1. **Damodaran: Excel headers not found.** The app now scans all Excel sheets for the `Industry Name` and `Unlevered beta` columns and can also scrape Damodaran's full U.S. HTML table. If both fail, download `betas.xls` in a browser and upload the file in the sidebar.
2. **OECD: SDMX 500/403.** The app **no longer calls the SDMX API**. It fetches the public Excel support data for Figure 2.1 of the **2026 OECD report**. If the Excel link cannot be downloaded in Streamlit, download it in your browser and upload it, or manually enter the tax rate from the OECD source. Do not describe reference fallback numbers as fresh data.
3. **Trading Economics: zero bond rows.** The overview at `/bonds` is dynamically rendered. The app instead scrapes the public 10Y government-yield table under `country-list/government-bond-10y` and parses the **Last** column and **Reference** month. If server-side scraping is blocked, use the manual input controls.

The refresh button clears the Streamlit data-fetch cache and re-requests all four source feeds without intentionally resetting your inputs. The app requires no API key. Actual access from Streamlit Community Cloud depends on the source websites, and **an automated local test does not establish that the hosted fetch works**.
