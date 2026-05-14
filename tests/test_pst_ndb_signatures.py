"""Regression tests for PST NDB-layer PAGETRAILER fields.

Two Outlook "Outlook Data File Corruption" incidents revealed separate
violations of MS-PST §2.2.2.7.1 (PAGETRAILER):

1. 2026-05-11: an NBT page (ptype=0x81) at offset 0x18F800 with bid=0x15
   had wSig=0 instead of ComputeSig(ib, bid) = 0xF80D. A latent bug in
   `block_signature` was also XOR-cancelling its `bid` argument. Both
   fixed; tests below pin them.

2. 2026-05-13: an AMap page (ptype=0x84) at offset 0xAC36400 had
   bid=0x35D5 in its trailer instead of bid=0xAC36400 (its own file
   offset). For AMap/PMap/FMap/FPMap pages, the trailer's `bid` field
   must equal `ib`, not a logical page-BID. Fixed in amap.py.

MS-PST §5.5 ComputeSig:

    DWORD ComputeSig(DWORD dwIB, DWORD dwBID) {
        dwIB ^= dwBID;
        return WORD(WORD(dwIB >> 16) ^ WORD(dwIB));
    }
"""

import struct

import pytest

from eml2pst.ndb.block import block_signature
from eml2pst.ndb.btree import (
    PTTYPE_BBT,
    PTTYPE_NBT,
    build_btree_pages,
    pack_bbt_entry,
    pack_nbt_entry,
)


def _spec_compute_sig(ib: int, bid: int) -> int:
    """Reference implementation of MS-PST §5.5 ComputeSig."""
    x = (ib ^ bid) & 0xFFFFFFFF
    return ((x >> 16) ^ (x & 0xFFFF)) & 0xFFFF


def _unpack_trailer(page: bytes) -> tuple[int, int, int, int, int]:
    """Return (ptype, ptype_repeat, wSig, dwCRC, bid) from a 512-byte page."""
    assert len(page) == 512
    return struct.unpack("<BB H I Q", page[-16:])


class TestBlockSignature:
    def test_matches_outlook_dialog_values(self):
        """The exact (ib, bid, wSig) triple from the Outlook corruption dialog."""
        assert block_signature(0x18F800, 0x15) == 0xF80D

    @pytest.mark.parametrize(
        "ib,bid",
        [
            (0x18F800, 0x15),
            (0x0000_4000, 0x04),
            (0x1234_5678, 0xABCD),
            (0xFFFF_0000, 0x0001),
            (0x0001_0000, 0xFFFF),
            (0xDEAD_BEEF, 0xCAFE_BABE),
        ],
    )
    def test_matches_msPst_5_5_spec(self, ib, bid):
        assert block_signature(ib, bid) == _spec_compute_sig(ib, bid)


class TestPageTrailerWsig:
    """build_btree_pages must stamp wSig = ComputeSig(ib, bid) on NBT/BBT pages."""

    def _run(self, entries, ptype):
        """Build pages with deterministic bid/offset allocators and return them.

        Offsets and bids are chosen so that the spec ComputeSig is non-zero —
        otherwise a buggy implementation that emits wSig=0 would coincidentally
        match the spec.
        """
        next_bid = [0x14]
        next_offset = [0x18_F800]
        offsets: dict[int, int] = {}

        def alloc_bid():
            bid = next_bid[0]
            next_bid[0] += 4  # bids step by 4 (low bits are reserved tag bits)
            return bid

        def alloc_offset(bid):
            offset = next_offset[0]
            next_offset[0] += 512
            offsets[bid] = offset
            return offset

        pages = build_btree_pages(entries, ptype, alloc_bid, alloc_offset)
        return pages, offsets

    def test_nbt_leaf_page_wSig_matches_spec(self):
        entries = [pack_nbt_entry(nid=i, bid_data=i + 0x100) for i in range(1, 6)]
        pages, offsets = self._run(entries, PTTYPE_NBT)

        assert len(pages) == 1
        bid, offset, page = pages[0]
        ptype, ptype_rep, wsig, _crc, trailer_bid = _unpack_trailer(page)

        assert ptype == PTTYPE_NBT
        assert ptype_rep == PTTYPE_NBT
        assert trailer_bid == bid
        assert wsig == _spec_compute_sig(offset, bid), (
            f"NBT page wSig {wsig:#06x} != spec {_spec_compute_sig(offset, bid):#06x} "
            f"for ib={offset:#x} bid={bid:#x}"
        )

    def test_bbt_leaf_page_wSig_matches_spec(self):
        entries = [pack_bbt_entry(bid=i * 4, ib=i * 0x40, cb=64) for i in range(1, 6)]
        pages, offsets = self._run(entries, PTTYPE_BBT)

        assert len(pages) == 1
        bid, offset, page = pages[0]
        ptype, ptype_rep, wsig, _crc, trailer_bid = _unpack_trailer(page)

        assert ptype == PTTYPE_BBT
        assert ptype_rep == PTTYPE_BBT
        assert trailer_bid == bid
        assert wsig == _spec_compute_sig(offset, bid), (
            f"BBT page wSig {wsig:#06x} != spec {_spec_compute_sig(offset, bid):#06x} "
            f"for ib={offset:#x} bid={bid:#x}"
        )

    def test_multi_level_nbt_each_page_has_correct_wSig(self):
        """Force a split: more leaf entries than fit in one page (>15 NBT leaves)."""
        entries = [pack_nbt_entry(nid=i, bid_data=i + 0x100) for i in range(1, 50)]
        pages, _ = self._run(entries, PTTYPE_NBT)

        assert len(pages) > 1, "expected multi-page split for this many entries"
        for bid, offset, page in pages:
            _, _, wsig, _, trailer_bid = _unpack_trailer(page)
            assert trailer_bid == bid
            assert wsig == _spec_compute_sig(offset, bid), (
                f"page wSig {wsig:#06x} != spec {_spec_compute_sig(offset, bid):#06x} "
                f"for ib={offset:#x} bid={bid:#x}"
            )


class TestAmapTrailerStaysZero:
    """AMap pages legitimately keep wSig=0 per MS-PST §2.2.2.7.2.1.
    Guards against an over-eager fix that would also touch amap.py.
    """

    def test_amap_page_wSig_is_zero(self):
        from eml2pst.ndb.amap import build_amap_page

        page = build_amap_page(
            allocated_ranges=[(0x4400, 512)],
            amap_offset=0x4400,
            file_base_offset=0x4400,
        )
        _, _, wsig, _, _ = _unpack_trailer(page)
        assert wsig == 0, "AMap pages must have wSig=0 per MS-PST §2.2.2.7.2.1"


class TestAmapTrailerBidEqualsOffset:
    """MS-PST §2.2.2.7.1: AMap PAGETRAILER bid == ib (file offset).

    2026-05-13 incident — AMap page at offset 0xAC36400 had bid=0x35D5 in
    its trailer (a logical page-BID from the writer's _alloc_page_bid
    counter), not the page's own file offset. Outlook rejected the PST.
    The fix writes amap_offset into the trailer's bid slot directly.
    """

    def test_amap_trailer_bid_matches_incident_value(self):
        """Reproduces the offset from the 2026-05-13 Outlook dialog exactly."""
        from eml2pst.ndb.amap import build_amap_page

        page = build_amap_page(
            allocated_ranges=[],
            amap_offset=0xAC36400,
            file_base_offset=0xAC36400,
        )
        _, _, _, _, trailer_bid = _unpack_trailer(page)
        assert trailer_bid == 0xAC36400, (
            f"AMap trailer bid {trailer_bid:#x} != amap_offset 0xAC36400 — "
            f"violates MS-PST §2.2.2.7.1 (bid must equal ib for AMap pages)"
        )

    def test_amap_trailer_bid_matches_first_amap_offset(self):
        """First AMap page lives at 0x4400; trailer bid must echo that."""
        from eml2pst.ndb.amap import build_amap_page

        page = build_amap_page(
            allocated_ranges=[],
            amap_offset=0x4400,
            file_base_offset=0x4400,
        )
        _, _, _, _, trailer_bid = _unpack_trailer(page)
        assert trailer_bid == 0x4400


class TestPtypeConstantsMatchSpec:
    """Pin the seven PAGETRAILER ptype values from MS-PST §2.2.2.7.

    Spec enumeration:
        ptypeBBT   = 0x80   Block B-Tree page
        ptypeNBT   = 0x81   Node B-Tree page
        ptypeFMap  = 0x82   Free Map page
        ptypePMap  = 0x83   Page Map page
        ptypeAMap  = 0x84   Allocation Map page
        ptypeFPMap = 0x85   Free Page Map page
        ptypeDL    = 0x86   Density List page (DList)
    """

    @pytest.mark.parametrize(
        "name,value",
        [
            ("PTTYPE_BBT", 0x80),
            ("PTTYPE_NBT", 0x81),
            ("PTTYPE_FMAP", 0x82),
            ("PTTYPE_PMAP", 0x83),
            ("PTTYPE_AMAP", 0x84),
            ("PTTYPE_FPMAP", 0x85),
            ("PTTYPE_DLIST", 0x86),
        ],
    )
    def test_constant(self, name, value):
        from eml2pst.ndb import btree

        actual = getattr(btree, name, None)
        assert actual == value, (
            f"btree.{name} should be {value:#04x} per MS-PST §2.2.2.7 (got {actual!r})"
        )
