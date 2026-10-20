# Disaster exposure by site

SCIRM matches GDACS disaster alerts (earthquakes, tropical cyclones, floods, volcanoes,
wildfires, droughts) to the places your suppliers operate.

## Sites

A supplier can have up to 50 sites, such as plants and warehouses, each with a name and
a country. A site is placed in one of three ways:

- **From SAP:** the supplier master import turns the vendor address (city and country,
  LFA1 ORT01 and LAND1) into a *Registered address (SAP)* site. Re-imports update it;
  sites added by hand are kept.
- **By city:** looked up in an offline gazetteer of cities with more than 15,000
  inhabitants. No address is sent to any outside service. Where several places share a
  name (for example the eight Springfields in the US), the most populous is used and the
  site is marked *ambiguous*; enter coordinates for it.
- **By coordinates:** used exactly as entered.

Add or remove sites in the supplier panel (**Suppliers**, then a supplier, then **Sites**).

## How exposure is judged

| Supplier | An alert counts as possible exposure when… |
|---|---|
| has at least one located site | a site lies within the alert's radius of its reported location |
| has no located site | the alert affects the supplier's country |

**Radius by alert type:**

| Alert type | Orange alert | Red alert |
|---|---|---|
| Earthquake | 150 km | 300 km |
| Tropical cyclone | 300 km | 500 km |
| Flood | 200 km | 300 km |
| Volcano or wildfire | 50 km | 100 km |
| Drought | whole country | whole country |

Each match shows the nearest site, its distance, and the radius used. For a supplier with
sites, alerts elsewhere in its countries are counted under the list, not shown as
exposures. An alert without a usable location, such as a drought, falls back to the country.

**These are approximations, not impact maps.**
- GDACS reports a single point for each alert: an earthquake's epicentre, or a cyclone's
  or flood's reported position.
- Cyclone tracks and flood extents are not used.
- The radii are deliberately generous, so a site near the edge of an event is not missed.
- A match means "look closer", not "this site is affected".

## Data and licence

The gazetteer (`libs/intel/data/cities.tsv.gz`) is built from
[GeoNames](https://www.geonames.org) `cities15000`, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Rebuild it with
`scripts/build_gazetteer.py`. Disaster alerts come from [GDACS](https://www.gdacs.org).
