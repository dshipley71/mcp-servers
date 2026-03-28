# GDELT MCP Server Colab Notebook — What the Notebook Covers

| Section | What it tests |
|---------|---------------|
| **Setup** | Clones the repo, installs `mcp-gdelt`, imports `GDELTClient` directly |
| **Basic article search** | Single keyword, default params |
| **Boolean operators** | `AND`, `OR`, exact phrase (`"..."`) |
| **Date ranges** | Timespan shorthands (`15min`→`1month`) and absolute `YYYYMMDDHHMMSS` windows |
| **Sort orders** | All five modes: `DateDesc`, `DateAsc`, `ToneAsc`, `ToneDesc`, `HybridRel` |
| **Image search — imagetag** | AI-visual content tags; renders images inline |
| **Image search — imagewebtag** | Caption/alt-text matching |
| **Image search — imageocrmeta** | OCR text extraction matching |
| **Multi-query comparison** | `asyncio.gather` for concurrent queries + bar chart |
| **Data analysis** | Language, country & domain distributions; volume-over-time time series |
| **Quick reference** | Parameter tables and useful links |
