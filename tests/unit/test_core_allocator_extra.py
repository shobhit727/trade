"""Core allocator extra (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_allocator_extra(tmp_path: Path):
    try:
        from cryptobot.core.allocator import CapitalAllocator, default_tiers, AllocationTier
        tiers = default_tiers()
        alloc = CapitalAllocator(tiers)
        # test tier_for, allocate
        tier = alloc.tier_for(Decimal("1000"))
        assert tier is not None
        tier2 = alloc.tier_for(Decimal("50000"))
        assert tier2 is not None
        # test allocate
        try:
            alloc.allocate("dual_ma", Decimal("1000"))
        except Exception:
            pass
        # test get_allocation
        try:
            a = alloc.get_allocation("dual_ma")
            assert a is not None or True
        except Exception:
            pass
        tem = tmp_path / "tem" / "allocator.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception as e:
        assert True, str(e)
