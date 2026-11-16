# International Cost of Capital — Streamlit app

This repository contains **exactly three required files**, with all application code in
`app.py`. It compares the **cost of equity, pre-tax cost of debt, and WACC** for
one project in USD and the local currency of a selected country.

The app uses the class formula:

```text
(1 + R_foreign) = (1 + R_USD) × (1 + Rf_foreign) / (1 + Rf_USD)
```

There is **no API key** and no need for a separate `finance.py` or
`data_sources.py` file.

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

## Input data and update dates

| Data | Source | Method and time label |
| --- | --- | --- |
| U.S. industry unlevered beta | [Damodaran betas.xls](https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls), [HTML version](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html) | Current downloaded industry data; reference subset dated Jan 2026 if download fails |
| USD Baa2/BBB borrowing spread for large nonfinancial service companies | [Damodaran synthetic ratings](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html) | Current webpage; fallback 1.11% (Jan 2026) |
| Corporate income tax | [OECD corporate tax database](https://www.oecd.org/en/data/datasets/corporate-income-tax-rates-database.html) | OECD SDMX latest available year by country, from 2020 onward; fallback dated 2026 subset |
| 10-year government yields | [Trading Economics bonds](https://tradingeconomics.com/bonds) | Public HTML table (no API key); quote dates by country; dated Nov 12–13, 2026 reference snapshot if scraping fails |

**Source transparency:** Each source is marked `LIVE FETCH` or `DATED REFERENCE`
and shows a source URL, data vintage, and fetch timestamp. A failed fetch
**does not mean current rates were retrieved**. Source-site HTML structures can
change; check that the resulting figures and dates are plausible, and use manual
overrides if the page or data API cannot be parsed. The fallback industry list
contains a limited subset: the app warns that a truly full all-industry
comparison requires successful Damodaran retrieval.

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
