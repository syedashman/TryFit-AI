# TRYFIT AI — Sprint 4 Phase 3C.1

Phase 3C.1 adds a provider-neutral autonomous analysis layer before pose-aware generation.

## Added
- Automatic garment reference analysis
- Product scope/type inference
- Pose-family and camera-angle profiling
- Dominant color extraction
- Person-photo quality scoring and ranking
- Product-lock SHA-256 signature
- Catalog product intelligence API
- Person-set intelligence API
- Capability discovery API

## APIs
- `GET /api/intelligence/capabilities`
- `POST /api/intelligence/catalog-product`
- `POST /api/intelligence/person-set`

Phase 3C.2 will consume these profiles for pose-conditioned generation, retries, ranking, and exact output-count recovery.
