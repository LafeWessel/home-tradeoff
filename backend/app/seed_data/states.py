"""Hardcoded US states + DC: FIPS, abbreviation, name, lat/lon centroid.

Centroids are population-weighted approximations from US Census Gazetteer
files (computed once and embedded for portability)."""

from __future__ import annotations

STATES: list[dict] = [
    {"fips": "01", "abbr": "AL", "name": "Alabama",        "lat": 32.7794, "lon":  -86.8287},
    {"fips": "02", "abbr": "AK", "name": "Alaska",         "lat": 64.0685, "lon": -152.2782},
    {"fips": "04", "abbr": "AZ", "name": "Arizona",        "lat": 34.2744, "lon": -111.6602},
    {"fips": "05", "abbr": "AR", "name": "Arkansas",       "lat": 34.8938, "lon":  -92.4426},
    {"fips": "06", "abbr": "CA", "name": "California",     "lat": 37.1841, "lon": -119.4696},
    {"fips": "08", "abbr": "CO", "name": "Colorado",       "lat": 38.9972, "lon": -105.5478},
    {"fips": "09", "abbr": "CT", "name": "Connecticut",    "lat": 41.6219, "lon":  -72.7273},
    {"fips": "10", "abbr": "DE", "name": "Delaware",       "lat": 38.9896, "lon":  -75.5050},
    {"fips": "11", "abbr": "DC", "name": "District of Columbia", "lat": 38.9101, "lon": -77.0147},
    {"fips": "12", "abbr": "FL", "name": "Florida",        "lat": 28.6305, "lon":  -82.4497},
    {"fips": "13", "abbr": "GA", "name": "Georgia",        "lat": 32.6415, "lon":  -83.4426},
    {"fips": "15", "abbr": "HI", "name": "Hawaii",         "lat": 20.2927, "lon": -156.3737},
    {"fips": "16", "abbr": "ID", "name": "Idaho",          "lat": 44.3509, "lon": -114.6130},
    {"fips": "17", "abbr": "IL", "name": "Illinois",       "lat": 40.0417, "lon":  -89.1965},
    {"fips": "18", "abbr": "IN", "name": "Indiana",        "lat": 39.8942, "lon":  -86.2816},
    {"fips": "19", "abbr": "IA", "name": "Iowa",           "lat": 42.0751, "lon":  -93.4960},
    {"fips": "20", "abbr": "KS", "name": "Kansas",         "lat": 38.4937, "lon":  -98.3804},
    {"fips": "21", "abbr": "KY", "name": "Kentucky",       "lat": 37.5347, "lon":  -85.3021},
    {"fips": "22", "abbr": "LA", "name": "Louisiana",      "lat": 31.0689, "lon":  -91.9968},
    {"fips": "23", "abbr": "ME", "name": "Maine",          "lat": 45.3695, "lon":  -69.2428},
    {"fips": "24", "abbr": "MD", "name": "Maryland",       "lat": 39.0550, "lon":  -76.7909},
    {"fips": "25", "abbr": "MA", "name": "Massachusetts",  "lat": 42.2596, "lon":  -71.8083},
    {"fips": "26", "abbr": "MI", "name": "Michigan",       "lat": 44.3467, "lon":  -85.4102},
    {"fips": "27", "abbr": "MN", "name": "Minnesota",      "lat": 46.2807, "lon":  -94.3053},
    {"fips": "28", "abbr": "MS", "name": "Mississippi",    "lat": 32.7364, "lon":  -89.6678},
    {"fips": "29", "abbr": "MO", "name": "Missouri",       "lat": 38.3568, "lon":  -92.4580},
    {"fips": "30", "abbr": "MT", "name": "Montana",        "lat": 47.0527, "lon": -109.6333},
    {"fips": "31", "abbr": "NE", "name": "Nebraska",       "lat": 41.5378, "lon":  -99.7951},
    {"fips": "32", "abbr": "NV", "name": "Nevada",         "lat": 39.3289, "lon": -116.6312},
    {"fips": "33", "abbr": "NH", "name": "New Hampshire",  "lat": 43.6805, "lon":  -71.5811},
    {"fips": "34", "abbr": "NJ", "name": "New Jersey",     "lat": 40.1907, "lon":  -74.6728},
    {"fips": "35", "abbr": "NM", "name": "New Mexico",     "lat": 34.4071, "lon": -106.1126},
    {"fips": "36", "abbr": "NY", "name": "New York",       "lat": 42.9538, "lon":  -75.5269},
    {"fips": "37", "abbr": "NC", "name": "North Carolina", "lat": 35.5557, "lon":  -79.3877},
    {"fips": "38", "abbr": "ND", "name": "North Dakota",   "lat": 47.4501, "lon": -100.4659},
    {"fips": "39", "abbr": "OH", "name": "Ohio",           "lat": 40.2862, "lon":  -82.7937},
    {"fips": "40", "abbr": "OK", "name": "Oklahoma",       "lat": 35.5889, "lon":  -97.4943},
    {"fips": "41", "abbr": "OR", "name": "Oregon",         "lat": 43.9336, "lon": -120.5583},
    {"fips": "42", "abbr": "PA", "name": "Pennsylvania",   "lat": 40.8781, "lon":  -77.7996},
    {"fips": "44", "abbr": "RI", "name": "Rhode Island",   "lat": 41.6772, "lon":  -71.5101},
    {"fips": "45", "abbr": "SC", "name": "South Carolina", "lat": 33.9169, "lon":  -80.8964},
    {"fips": "46", "abbr": "SD", "name": "South Dakota",   "lat": 44.4443, "lon": -100.2263},
    {"fips": "47", "abbr": "TN", "name": "Tennessee",      "lat": 35.8580, "lon":  -86.3505},
    {"fips": "48", "abbr": "TX", "name": "Texas",          "lat": 31.4757, "lon":  -99.3312},
    {"fips": "49", "abbr": "UT", "name": "Utah",           "lat": 39.3055, "lon": -111.6703},
    {"fips": "50", "abbr": "VT", "name": "Vermont",        "lat": 44.0687, "lon":  -72.6658},
    {"fips": "51", "abbr": "VA", "name": "Virginia",       "lat": 37.5215, "lon":  -78.8537},
    {"fips": "53", "abbr": "WA", "name": "Washington",     "lat": 47.3826, "lon": -120.4472},
    {"fips": "54", "abbr": "WV", "name": "West Virginia",  "lat": 38.6409, "lon":  -80.6227},
    {"fips": "55", "abbr": "WI", "name": "Wisconsin",      "lat": 44.6243, "lon":  -89.9941},
    {"fips": "56", "abbr": "WY", "name": "Wyoming",        "lat": 42.9957, "lon": -107.5512},
]

ABBR_BY_FIPS: dict[str, str] = {s["fips"]: s["abbr"] for s in STATES}
FIPS_BY_ABBR: dict[str, str] = {s["abbr"]: s["fips"] for s in STATES}
