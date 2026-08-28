# Retrieval Benchmark Report (Phase 2B)

All metrics are **measured** from the real engine (not fabricated).

| Scenario | Mode | Precision@k | Coverage | Irrelevant | Latency ms | Orig tokens | Prepared tokens |
|----------|------|-------------|----------|------------|------------|-------------|-----------------|
| paraphrase_websocket | keyword | 100.0% | 75.0% | 0 | 0.3 | 46 | 16 |
| paraphrase_websocket | hybrid | 100.0% | 100.0% | 0 | 1485.87 | 46 | 26 |
| paraphrase_auth | keyword | 0.0% | 0.0% | 0 | 0.22 | 34 | 0 |
| paraphrase_auth | hybrid | 100.0% | 100.0% | 0 | 1514.19 | 34 | 37 |
| paraphrase_database | keyword | 0.0% | 0.0% | 0 | 0.17 | 24 | 0 |
| paraphrase_database | hybrid | 100.0% | 100.0% | 0 | 1432.24 | 24 | 10 |

## Methodology

- **Precision@k**: relevant expected substrings found in top-k results / k
- **Coverage**: fraction of expected_important items found in top-k
- **Latency**: mean of 3 search calls (ms), includes embed-on-demand for hybrid
- **Tokens**: tiktoken estimates (not provider billing)

## Notes

- Keyword-only: `OVERHAUST_EMBEDDINGS=0`
- Hybrid: `OVERHAUST_EMBEDDINGS=1` with fastembed
- Paraphrase queries intentionally differ from stored memory wording