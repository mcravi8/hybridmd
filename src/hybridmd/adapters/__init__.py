"""Backend adapters: convert third-party extractor output into DocElement.

Each adapter reads its source format purely by *duck typing*, so importing an
adapter never requires its extractor package to be installed. The extractor is
declared as an optional extra (e.g. ``hybridmd[unstructured]``) and is needed
only to *produce* the inputs — never to import or run the adapter, and never for
core CI.
"""

from __future__ import annotations
