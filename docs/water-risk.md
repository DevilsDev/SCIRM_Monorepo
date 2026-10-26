# Water risk by site

SCIRM shows water-related risk for the places your suppliers operate, using the
[WRI Aqueduct 4.0](https://www.wri.org/aqueduct) water risk indicators. Use it to see
which plants sit in water-stressed, drought-prone or flood-prone areas, and to scope
environmental due diligence.

Open **Supply Chain → Water risk** for all sites, or **Suppliers**, then a supplier, then
**Water risk** for one supplier.

## What is shown

Aqueduct divides the world into about 68,500 areas. Each is the overlap of a river basin
(HydroBASINS level 6), a province and a groundwater aquifer. For the area a site lies in,
SCIRM shows each of these indicators separately, with WRI's own category and label (for
example "Extremely High (>80%)"):

| Group | Indicators |
|---|---|
| Physical risk: quantity | Baseline water stress, baseline water depletion, interannual variability, seasonal variability, groundwater table decline, riverine flood risk, coastal flood risk, drought risk |
| Physical risk: quality | Untreated connected wastewater, coastal eutrophication potential |
| Regulatory and reputational | Unimproved or no drinking water, unimproved or no sanitation |

WRI also publishes projected water stress for each river basin. SCIRM shows it for 2030
and 2050 under three scenarios: optimistic (SSP1 RCP2.6), business as usual (SSP3 RCP7.0)
and pessimistic (SSP5 RCP8.5).

The baseline covers 1979–2019. Four indicators were recalculated for Aqueduct 4.0; the
others are carried over from Aqueduct 3.0.

**What is left out, on purpose:**

- **There is no SCIRM water score.** Indicators are never combined. WRI's weighted "overall
  water risk" composites are left out too, because the weights encode choices your own
  analysis should make.
- **The RepRisk country ESG index** that Aqueduct also includes is left out, because it is a
  third party's index.

Categories run from 0 (low) to 4 (extremely high). There are also two special values:

- **-1:** a special class such as "Arid and Low Water Use" or "No Risk"
- **No data**

## How a site is placed

A site needs coordinates: either entered exactly, or a city looked up in the offline
gazetteer (see [Disaster exposure by site](site-exposure.md)).

SCIRM finds the site's Aqueduct area in an offline grid of about 2 km, built from WRI's
area outlines. No coordinates or addresses leave SCIRM, and nothing is stored: the lookup
runs each time a page is opened.

A note appears next to a site when:

- **It is placed at a city centre.** A city-level site can lie in a different river basin
  from the actual plant. Enter coordinates to be sure.
- **No area lies at the exact point.** This happens on some coastlines. The nearest area
  within 15 km is used, and its distance is shown.
- **It is close to a boundary with different values.** At an area's edge, the 2 km grid
  can pick the neighbouring area. Check the location in the WRI Water Risk Atlas.

**How accurate the lookup is.** It was checked against WRI's own outlines with an exact
point-in-polygon test, using 3,000 random points (944 of them inside an area):

- 97% got the same area.
- 98% got the same categories for every indicator.
- 18 of the 19 points with different categories were flagged as near a boundary.

**Suppliers without a located site** are listed separately. Their water risk is
**unknown**, not low.

## Download

**Download CSV** exports one row per site. Each row has the supplier, the site, how it
was placed, the Aqueduct area, every indicator's label and raw value, the projections, and
the source. The download is recorded in the audit log as "Downloaded the water risk CSV".

## Caveats from WRI

- Aqueduct's indicators are modelled. They cannot be measured directly, and WRI notes
  that they have not been validated.
- Aqueduct does not model water moved between basins, such as by canals or pipelines.
- WRI advises caution when comparing Aqueduct 4.0 values with earlier versions.

Use the indicators to decide where to look more closely, for example with a supplier
questionnaire or a site visit. They are not findings about a supplier.

## Data and licence

Aqueduct 4.0 is published by the World Resources Institute under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). SCIRM names the source on every
screen and in the CSV, and does not change WRI's values or categories.

Citation: Kuzma, S., M.F.P. Bierkens, S. Lakshman, T. Luo, L. Saccoccia, E. H. Sutanudjaja,
and R. Van Beek. 2023. "Aqueduct 4.0: Updated decision-relevant global water risk
indicators." Technical Note. Washington, DC: World Resources Institute.
[doi.org/10.46830/writn.23.00061](https://doi.org/10.46830/writn.23.00061).

The lookup files in `libs/intel/data` (`water_risk_units.tsv.gz` and
`water_risk_grid.bin.gz`) are built from WRI's download with
`scripts/build_water_risk.py`. Rebuild them when WRI publishes a new version.
