# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/)
once it reaches 1.0.0 (currently in 0.y.z; minor bumps may break API).

## [0.1.0] — 2026-05-14

### Initial release

Hard fork of `igrbtn/EDB_Explorer` @ `7a67d6033` with three
[MS-PST] spec violations fixed.

### Fixed

- **NBT/BBT page-trailer wSig** ([MS-PST] §2.2.2.7.1). Upstream
  hardcoded `wSig=0` on every B-tree page; Outlook rejected the
  resulting PSTs. Now computed as `ComputeSig(ib, bid)`.
  Surfaced 2026-05-11.
- **`block_signature` algorithm** ([MS-PST] §5.5). Upstream's
  implementation algebraically XOR-cancelled its `bid` argument
  (returning `high16(ib)` for any input). Now folds `(ib^bid)` by
  XOR-ing its high and low 16-bit halves per spec.
- **AMap PAGETRAILER `bid` field** ([MS-PST] §2.2.2.7.1). Upstream
  wrote a logical page-BID into the AMap trailer's `bid` slot; the
  spec requires `bid == ib` for AMap/PMap/FMap/FPMap pages.
  Surfaced 2026-05-13. **API change:** `build_amap_page` no longer
  accepts a `bid` parameter.

### Changed

- `build_btpage(entries, ptype, bid, c_level=0)` →
  `build_btpage(entries, ptype, bid, ib, c_level=0)`. `ib` is required.
- `PTTYPE_*` constants in `ndb/btree.py` renamed to match [MS-PST]
  §2.2.2.7 spec nomenclature (`PTTYPE_FMP` → `PTTYPE_FMAP`, etc.).
  Old names had zero references in upstream so the rename is inert
  in practice.

[MS-PST]: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-pst/
