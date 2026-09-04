"""The demo reset must be repeatable, and its delete order must stay valid.

Step 1 of the demonstration script is ``make reseed``. It broke once already,
and it broke in the worst available way: adding ``MemberAdjustment`` low in the
delete order left ``--reset`` working on a database that had no adjustments in
it and failing on the *next* run. A defect that only appears the second time is
one you meet during the demo rather than before it.

So this checks the order against the schema itself rather than against a list
someone has to remember to update.
"""

from __future__ import annotations

import scripts.seed_demo as seed
from core.db.models import Base


def reset_order() -> list[str]:
    """The table names ``reset()`` deletes from, in the order it deletes them.

    Read out of the function's own bytecode constants rather than duplicated
    here, so the test cannot drift from the code it is checking.
    """
    order = []
    for model in seed.RESET_ORDER:
        order.append(model.__tablename__)
    return order


def test_every_table_is_deleted_before_anything_it_points_at() -> None:
    """A child row must go before its parent, or SQLite refuses the delete.

    ``sorted_tables`` is SQLAlchemy's own dependency order, parents first. The
    reset must therefore be its reverse, for every pair that has a dependency.
    """
    dependency_order = [table.name for table in Base.metadata.sorted_tables]
    position = {name: i for i, name in enumerate(dependency_order)}

    deletes = reset_order()
    offenders = []

    for i, child in enumerate(deletes):
        for parent in deletes[i + 1 :]:
            # A table deleted later must not be a *dependent* of this one.
            if position.get(parent, -1) > position.get(child, -1):
                table = Base.metadata.tables[parent]
                refers = any(
                    fk.column.table.name == child
                    for column in table.columns
                    for fk in column.foreign_keys
                )
                if refers:
                    offenders.append(f"{parent} is deleted after {child} it references")

    assert not offenders, (
        "reset() would raise a FOREIGN KEY error: " + "; ".join(offenders)
    )


def test_every_table_with_seeded_rows_is_in_the_reset() -> None:
    """A table the seed writes but the reset misses leaves rows behind.

    ``alembic_version`` is excluded because it is migration bookkeeping, not
    demo data, and deleting it would strand the database mid-history.
    """
    known = set(reset_order()) | {"users", "alembic_version"}
    missing = sorted(set(Base.metadata.tables) - known)

    assert not missing, (
        f"tables not cleared by reset(): {missing}. Add them in an order that "
        "deletes children before parents."
    )


def test_the_order_names_real_tables() -> None:
    """Guards against a stale entry surviving a model rename."""
    unknown = [name for name in reset_order() if name not in Base.metadata.tables]

    assert not unknown, f"reset() names tables that no longer exist: {unknown}"
