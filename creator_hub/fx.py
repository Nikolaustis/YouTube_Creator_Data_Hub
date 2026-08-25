"""Legacy compatibility marker for the retired GMV FX subsystem.

 defines UgPhone backend GMV as a native USD cumulative snapshot.  The
Dashboard, server, importer and service layers no longer perform currency
conversion or make FX network requests.  This file intentionally contains no
resolver so an overlay install also replaces the former online-FX module.
"""

FX_DISABLED = True
GMV_CURRENCY = "USD"
