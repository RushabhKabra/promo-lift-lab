# Reading the lab as a trade-spend post-evaluation

The lab is built from the retailer's side of the till: receipts, loyalty discounts, manufacturer coupons and the retailer's match. A brand's commercial finance team sits on the other side of the same promotion. It funds part of the deal, accrues for it, and later has to decide whether to buy that feature again. This page is how I would read the same numbers through that lens. It adds no new figures. Every number below is already in [`exports/app/certified_kpis.json`](../exports/app/certified_kpis.json) and the [executive brief](executive-brief.md).

## Gross to net, the short version

| Line | Study year |
| --- | ---: |
| Pre-discount ring (gross) | $5,418,592.77 |
| Loyalty, coupon and match discounts | −$822,553.19 |
| Cash received (net) | $4,596,039.58 |
| Discounts as a share of gross | 15.18% |

This is not a manufacturer P&L. There is no list price, no off-invoice allowance, no slotting and no cost of goods. It is the closest thing a public receipt panel has to a gross-to-net bridge, and it is reconciled: the build fails if fact sales drift from staging by more than $1 or 0.01%.

## The three questions a promo post-evaluation asks

1. **Did the event add volume that would not have happened anyway?** Against each product-store's own quiet weeks, feature weeks added $133,971.26 of net sales, a 60.97% lift on 27,555 matched pairs. On weeks that actually rang up, the lift was 10.50%. I quote both, because the larger number is mostly "a sale happened at all."
2. **Did the extra cash cover what the deal cost?** The ROI proxy on those feature weeks is $0.78 of incremental net sales per discount dollar. Deli meats is one of the few categories above 1 (2.10).
3. **Which events should not be repeated?** 11 of 21 scored mailer campaigns have incremental net sales below zero (difference-in-differences against unmailed households). Campaign 8 is the clearest miss. I rank on incremental dollars, not on a ratio with a tiny denominator.

## Where the spend actually sits

49.43% of discount dollars sat on lines with no display and no mailer. If a brand only post-evaluates its featured events, about half the discount bill never gets reviewed. That is the line I would bring to a planning meeting first.

## What a brand-side version would need

- Deal rates and terms by customer, so an accrual can be checked against what was actually claimed.
- Cost of goods, so the ROI proxy becomes a margin ROI.
- Shipments alongside scan data, because forward buying moves volume into the deal window.
- A trade promotion management (TPM) export, so the post-event read lands where the next plan is built.

This page is how I would carry the same method across to a brand's own data.
