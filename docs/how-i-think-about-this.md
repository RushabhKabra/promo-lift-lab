# How I think about this

I wanted a private lab for a question grocery data keeps asking. When something goes on promotion, how much of the extra volume is real, and how much would have gone through the till anyway?

That is the whole project. Not a platform, not a tour of tools. A year of household receipts, the campaigns those households were mailed, the coupons they redeemed, and the displays and mailers the stores actually ran.

## What I set out to answer

1. For a product in a store, what did a feature week do to cash received, compared with that same product's other weeks?
2. For a campaign, did the households who were mailed it hand over more money than a reasonable comparison group, after the coupon?
3. Which campaigns clearly did not pay?
4. If I had to forecast a department next week, would anything beat the average of the last four weeks?
5. Which households live on discount, and which departments move together?

## In scope

- The Complete Journey public mirrors: receipts, products, promotions, campaigns, coupons, redemptions, demographics.
- A local Postgres warehouse with a star schema, tested grains, and named metrics.
- The analyses above, written back into tables the app is allowed to read.
- A small Streamlit app, an Excel briefing, and CSV extracts a BI tool can load.
- A question page that can only talk about those certified numbers.

## Out of scope

- Any private retailer file. If the public mirrors are down, the fallback is the UCI online retail extract, and the write-up says so.
- Item-level cost, vendor funding, inventory, or waste. The files do not have them.
- A randomized read of these campaigns. They were not randomized.
- A binary Power BI or Tableau file. The extracts are the hand-off.
- Household-level demographics in the optional model call. Aggregates only.

## Assumptions I am willing to defend

- `sales_value` is cash received, and the discount fields in this mirror are positive costs. The glossary records the identity I test.
- A missing promotion row means the product-store-week was not on display and not in the mailer.
- The mailed list is the exposed group for every campaign type.
- Zero-filling a product-store between its first and last observed week is fairer than comparing only the weeks it happened to sell, and it still misses products that barely sell. Coverage is reported so that limit stays visible.
- Four quiet weeks is the minimum before I will quote a baseline.
- The four-week mean is the forecast to beat, not a straw man.

## Risks

- Mailed households may already have been heavier buyers. The difference-in-differences removes a shared time shock and a pre-period level, and it does not remove a difference in trend that started earlier.
- Feature weeks may be the weeks a category was going to be busy anyway. That is why the campaign comparison exists beside the product-store comparison.
- Overlapping campaigns are common. Control households are kept out of any mailing that touches the window, which shrinks the control group and is still better than pretending the mailings were isolated.
- A short year makes a gradient-boosted model look smarter than it is. If it loses, it loses in public.
- The language layer can misread a column. The sources under each answer are there so I can check it without trusting the sentence.

## How I know a number is ready

A figure is ready when I can point to a grain, a formula in `docs/metrics-glossary.md`, a test or a SQL assertion, and the page or the briefing that shows it. The map is in `docs/questions-i-wanted-answered.md`.
