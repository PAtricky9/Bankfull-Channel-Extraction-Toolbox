# Bankfull Channel Extractor

ArcGIS Pro Python toolbox for deriving bankfull channel candidates from a stream centreline and LiDAR DEM.

The toolbox is designed for step by step QA:

1. Prepare inputs.
2. Generate station points.
3. Generate cross sections.
4. Sample DEM profiles.
5. Detect thalweg and hydraulic metrics.
6. Generate bankfull candidates.
7. Select final candidates with continuity checks.
8. Create bankfull polygons.
9. Optionally smooth bank lines.
10. Generate QA reports.

See the full user guide in `docs/README.md` and method notes in `docs/method_notes.md`.

## Attribution

This implementation was inspired by the Cross-Sections and Dimensions Tool by Joshphar Kunapo and Kathryn Russell:

- https://github.com/jkunapo/Cross-Sections-Dimensions-Tool
- https://doi.org/10.5281/zenodo.18950771

No source code from that repository is included in this initial implementation. See `THIRD_PARTY_NOTICES.md`.
