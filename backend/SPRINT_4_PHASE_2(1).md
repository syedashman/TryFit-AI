# TryFit AI — Sprint 4 Phase 2

Phase 2 adds a conservative realism layer without altering the person geometry.

## Included
- Cloth-type-aware realism directives for sleeves, hems, trousers and full outfits
- Explicit fabric drape, fold, texture, edge, lighting and contact-shadow controls
- Post-generation detail refinement that preserves image dimensions and alpha
- Configurable sharpness, contrast and color factors
- Enhancement diagnostics stored in each job's provider metadata
- Regression tests for prompts, settings and non-destructive image processing

## Environment controls
- `VISUAL_ENHANCEMENT_ENABLED=true`
- `VISUAL_ENHANCEMENT_SHARPNESS=1.08`
- `VISUAL_ENHANCEMENT_CONTRAST=1.03`
- `VISUAL_ENHANCEMENT_COLOR=1.01`
