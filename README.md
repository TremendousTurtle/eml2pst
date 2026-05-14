# eml2pst

Pure-Python library for writing Microsoft PST (Personal Storage Table)
files. Hard fork of [`igrbtn/EDB_Explorer`](https://github.com/igrbtn/EDB_Explorer)'s
`eml2pst` package at upstream commit `7a67d6033e303e704c59ab2a74848d38c4ed43fb`.

## Status

Early — `0.y.z` while the API stabilizes. Active development driven by
real Outlook validation of generated PSTs.

## Install

```toml
# pyproject.toml
[project]
dependencies = [
    "eml2pst @ git+https://github.com/TremendousTurtle/eml2pst.git@v0.1.0",
]
```

```bash
uv sync
```

## Usage

```python
from eml2pst.eml_parser import parse_eml_bytes
from eml2pst.pst_file import PSTFileBuilder

builder = PSTFileBuilder(display_name="My Mailbox")
# ... add folders and messages ...
builder.write("output.pst")
```

## Spec fixes vs upstream (v0.1.0)

Three [MS-PST] spec violations were fixed in this fork's initial release.
See CHANGELOG.md for details and spec citations.

## License

MIT. See LICENSE; upstream attribution in NOTICE.
