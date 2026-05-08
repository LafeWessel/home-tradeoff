"""Data source modules.

Each source module exports one or more `fetch_*` functions that take a list
of `Location` rows and return a list of `(location_id, metric_key, value, source, year)`
tuples that the resolver writes to the cache table.
"""
