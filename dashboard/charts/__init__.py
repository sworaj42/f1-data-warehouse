"""One module per figure.

No module here issues SQL, and none of them aggregates: every number on screen was computed by a
view in sql/analytics/001_views.sql. A chart module filters, reshapes for the plotting grammar
(melt, sort, head) and draws. That boundary is the reason the warehouse is worth having -- if the
dashboard did the arithmetic, the star schema would be decoration.
"""
