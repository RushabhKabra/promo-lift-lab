# From a pile of files to a number I would defend

```mermaid
flowchart LR
  subgraph raw [Files]
    tx[Receipts]
    pr[Displays and mailers]
    cp[Campaigns and coupons]
  end
  subgraph stage [Staging]
    clean[Typed columns and quarantine]
  end
  subgraph star [Star schema]
    dims[Dates, products, stores, households, campaigns]
    facts[Receipt lines, placements, redemptions]
  end
  subgraph check [Checks]
    sql[Grain, keys, sales identity]
    py[Hand-computed metric tests]
  end
  subgraph mart [Marts]
    lift[Feature lift and campaign gaps]
    fc[Forecast scores]
    seg[Segments and baskets]
  end
  subgraph out [What I open]
    app[Streamlit]
    xl[Excel briefing]
    ask[Ask page]
  end
  tx --> clean
  pr --> clean
  cp --> clean
  clean --> dims
  clean --> facts
  facts --> sql
  sql --> lift
  sql --> fc
  sql --> seg
  py --> lift
  lift --> app
  fc --> app
  seg --> app
  lift --> xl
  lift --> ask
```

The rule in the middle is the one I care about. Nothing on the right is allowed to recompute a metric that the checks have not already seen. The app reads views. The ask page reads the snapshot those views were written to.
