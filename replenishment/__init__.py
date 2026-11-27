"""Store-SKU weekly replenishment on the panel the rest of the lab uses.

Demand is grocery units at product × store × week. The forecast is a
four-week moving average, a 52-week seasonal naive where the history
exists, and a promo-adjusted quiet-week mean. The order quantity is a
periodic-review order-up-to level. There is no on-hand in this dataset.
"""

from replenishment.run import run_replenishment

__all__ = ["run_replenishment"]
