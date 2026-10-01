"""The Aid builder: dataset -> data.js + packed bakers_aid.html.

Stage 2's product is a single self-contained HTML page. This package
compiles the dataset into the page's data (``web.py``) and inlines the
committed UI source (``web/``) plus the data into the shipped artifact
(``pack.py``). Compile and pack always run together, in one stage-2 run, so
the product can never drift from its data.

The browser owns the geometry: data.js ships raw 5-part shares (straight
from the dataset contract) and the Aid recomputes projections, distances,
violins and class statistics client-side for whatever merge/split partition
the user is in.
"""