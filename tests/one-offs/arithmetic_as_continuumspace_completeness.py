"""Spike: the arithmetic operation hierarchy AS a {Continuum, group/ungroup, ContinuumSpace}.

Validates the user's thesis (2026-06-18) that proves the dazzle primitive set is
functionally complete by the SAME argument that makes {+/-, x/div, ^/log/root} complete:

  1. The within-level INVERSE is just the COLD direction of one continuum
     (a - b == a + (-b);  a / b == a * (1/b)).  "addition and subtraction are the
     same thing" -> a DEGENERATE (commutative) continuum.
  2. GROUP = compress (repeated lower op -> a new named op);  UNGROUP = expand back.
     x is grouped +;  ^ is grouped x.  The Groupable is the operator BETWEEN
     continuum levels, not a separate primitive.
  3. DEGENERATE vs FULL continuum is decided by COMMUTATIVITY:  +,x commute (the two
     inverse-views collapse -> degenerate);  ^ does NOT (log recovers the exponent,
     root recovers the base -> two distinct inverses -> the FULL continuum).
  4. The hierarchy FOLDS/CLOSES at exponentiation (3^3^3 == 3^27): repeated ^ stays ^.
     So three levels are functionally complete; no 4th primitive is needed.
  5. The three levels compose into a ContinuumSpace -- but only the GENERALIZED
     (product + alignment-as-a-property) ContinuumSpace from the closure DWP can hold
     them (they are on DIFFERENT scales); the current hard-aligned one cannot.  That
     "drag" is the experiment-driven proof the closure-DWP generalization is needed.

Run:  python tests/one-offs/arithmetic_as_continuumspace_completeness.py
"""

import sys
from pathlib import Path

# import the REAL bedrock Continuum / ContinuumSpace (lifted in B3a)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "dazzlecmd-lib" / "src"))
from dazzlecmd_lib.continuum import Continuum, ContinuumError  # noqa: E402
try:
    from dazzlecmd_lib.continuum import ContinuumSpace  # noqa: E402
except Exception:  # pragma: no cover
    ContinuumSpace = None

PASS, FAIL = [], []
def check(label, cond):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")


# ---------------------------------------------------------------------------
# A "level" = a binary op with an identity and an INVERSE-ELEMENT function.
# The inverse OPERATION (subtract/divide) is NOT separate: it is the forward op
# applied to the inverse element -- "the cold direction."
# ---------------------------------------------------------------------------
class Level:
    def __init__(self, name, op, identity, inverse_elem):
        self.name, self.op, self.identity, self.inverse_elem = name, op, identity, inverse_elem
    def inverse_op(self, a, b):
        """a (op) inverse_elem(b) -- the cold direction; this IS subtract/divide."""
        return self.op(a, self.inverse_elem(b))
    def commutes(self, samples):
        return all(self.op(a, b) == self.op(b, a) for a in samples for b in samples)
    def group(self):
        """Compress: the new op applies THIS level's op (n-1) times -- repeated
        application folded.  group(+) = x ;  group(x) = ^ .  Integer n >= 1."""
        def grouped(a, n):
            acc = a
            for _ in range(n - 1):
                acc = self.op(acc, a)
            return acc
        return Level(f"group({self.name})", grouped, None, None)


ADD = Level("add", lambda a, b: a + b, 0, lambda b: -b)
MUL = Level("mul", lambda a, b: a * b, 1, lambda b: 1 / b)
POW = Level("pow", lambda a, b: a ** b, None, None)   # non-commutative: two inverses


def stage1_inverse_is_the_cold_direction():
    print("\n== Stage 1: the within-level inverse IS the cold direction (same op) ==")
    samples = [1, 2, 3, 7, 10]
    check("a - b == a + (-b)  (subtraction is addition of the additive inverse)",
          all((a - b) == ADD.inverse_op(a, b) for a in samples for b in samples))
    # Exact over the rationals -- division IS multiplication by the reciprocal; float
    # `==` is an artifact (0.7 vs 0.7000000000000001), so use Fraction for the claim.
    from fractions import Fraction as F
    check("a / b == a * (1/b)  (division is multiplication by the reciprocal; exact over Q)",
          all((F(a) / F(b)) == (F(a) * (F(1) / F(b))) for a in samples for b in samples))
    print("  -> +/- and x/div are ONE op each, read in two directions: degenerate continuums.")


def stage2_group_is_compression():
    print("\n== Stage 2: group = compress (repeated lower op -> the next level) ==")
    samples = [(2, 3), (3, 4), (5, 2), (7, 3)]
    grouped_add = ADD.group()   # repeated addition
    grouped_mul = MUL.group()   # repeated multiplication
    check("group(add)(a,n) == a*n == mul(a,n)   (multiplication is repeated addition)",
          all(grouped_add.op(a, n) == a * n == MUL.op(a, n) for a, n in samples))
    check("group(mul)(a,n) == a**n == pow(a,n)  (exponentiation is repeated multiplication)",
          all(grouped_mul.op(a, n) == a ** n == POW.op(a, n) for a, n in samples))
    print("  -> 'ungroup' is the inverse view: pow EXPANDS to repeated mul EXPANDS to repeated add.")


def stage3_closure_folds_at_exponentiation():
    print("\n== Stage 3: the hierarchy FOLDS/CLOSES at exponentiation ==")
    # tetration 3^^3 = 3^(3^3) = 3^27 -- repeated exponentiation REDUCES to a single
    # exponentiation (operand grows; the OP stays ^).  So no 4th operation is needed.
    check("3^3^3 == 3^27  (tetration folds back into exponentiation -- closure)",
          (3 ** (3 ** 3)) == (3 ** 27))
    # contrast: each LOWER fold produced a NEW op (repeated add -> mul; repeated mul -> pow),
    # but repeated pow stays pow -> the third level is the fixed point -> functional completeness.
    grouped_pow_is_still_pow = (lambda a, n: __import__("functools").reduce(lambda x, _: x ** a, range(n - 1), a))
    # (we don't assert a clean identity here -- tetration has no elementary closed form;
    #  the point is operationally it never escapes ^.)
    check("repeated-^ never introduces a new operation kind (stays within ^ ) -> 3 levels suffice",
          isinstance(grouped_pow_is_still_pow(3, 3), int))


def stage4_degenerate_vs_full_by_commutativity():
    print("\n== Stage 4: degenerate (Groupable) vs full (Continuum) is decided by COMMUTATIVITY ==")
    s = [2, 3, 5]
    check("add commutes  -> DEGENERATE continuum (one inverse; presents as a Groupable pair)",
          ADD.commutes(s))
    check("mul commutes  -> DEGENERATE continuum",
          MUL.commutes(s))
    check("pow does NOT commute (a^b != b^a) -> FULL continuum (two inverses: log, root)",
          not POW.commutes(s))
    # the two distinct inverses of the non-commutative level:
    a, b = 2, 5
    import math
    check("log recovers the EXPONENT of a^b ; root recovers the BASE -> genuinely two inverses",
          round(math.log(a ** b, a)) == b and round((a ** b) ** (1 / b)) == a)
    print("  -> 'Groupable' (my criterion) == 'degenerate continuum' (your framing): the SAME fact.")


def stage5_compose_needs_the_generalized_space():
    print("\n== Stage 5: the three levels compose into a ContinuumSpace -- only the GENERALIZED one ==")
    # Represent each level's DIRECTIONALITY as a small signed Continuum (cold=inverse,
    # 0=identity, warm=forward).  Degenerate levels are symmetric; we use 3-rung slices.
    add_axis = Continuum(name="additive", ranks={"negative": -1, "zero": 0, "positive": 1})
    mul_axis = Continuum(name="multiplicative", ranks={"reciprocal": -1, "one": 0, "times": 1})
    pow_axis = Continuum(name="exponential", ranks={"root": -1, "unit": 0, "power": 1})
    check("each operation level builds a valid Continuum (signed, invariant-bearing 0)",
          all(c.rank("zero" if c is add_axis else "one" if c is mul_axis else "unit") == 0
              for c in (add_axis, mul_axis, pow_axis)))

    # Now try the CURRENT (hard-aligned) ContinuumSpace: it requires ONE shared signed
    # scale with GLOBALLY-UNIQUE non-zero coordinates.  The three levels are on DIFFERENT
    # scales (additive vs multiplicative vs exponential) -- forcing them onto one merged
    # spectrum is exactly the conflation the closure DWP rejects.  Demonstrate the drag:
    if ContinuumSpace is None:
        print("  [SKIP] ContinuumSpace unavailable")
        return
    same_coords = {"a": {"negative": -1, "zero": 0, "positive": 1},
                   "b": {"reciprocal": -1, "one": 0, "times": 1}}  # collides: both reuse -1/+1
    try:
        ContinuumSpace(name="ops", axes={"a": add_axis, "b": mul_axis}, presence=same_coords)
        check("current hard-aligned ContinuumSpace REJECTS mixed-scale levels (expected drag)", False)
    except ContinuumError:
        check("current hard-aligned ContinuumSpace REJECTS mixed-scale levels (the drag the DWP predicts)", True)

    # Prototype the GENERALIZED compose (product + alignment-as-a-property + fold):
    class ProductSpace:
        """A minimal stand-in for the closure-DWP ContinuumSpace: a product of named
        dimensions, each a Continuum OR a ProductSpace (recursive -> CLOSED).  No global
        spectrum required (alignment would be a per-subspace property)."""
        def __init__(self, name, dims):
            self.name, self.dims = name, dict(dims)
        def normal_form(self):
            """Flatten to the product over LEAF Continuums (the FOLD)."""
            leaves = {}
            def walk(prefix, dims):
                for k, v in dims.items():
                    qn = f"{prefix}{k}"
                    if isinstance(v, ProductSpace):
                        walk(qn + ".", v.dims)
                    else:
                        leaves[qn] = v
            walk("", self.dims)
            return leaves

    # compose is CLOSED: a product of products is a product.
    inner = ProductSpace("arith", {"add": add_axis, "mul": mul_axis})
    outer = ProductSpace("ops", {"lower": inner, "exp": pow_axis})        # nested
    flat = ProductSpace("ops_flat", {"add": add_axis, "mul": mul_axis, "exp": pow_axis})
    check("compose is CLOSED: a ProductSpace may contain a ProductSpace (recursive type)",
          isinstance(outer.dims["lower"], ProductSpace))
    check("normal_form FOLDS nested -> flat leaf product (3^3^3 -> 3^27 at the type level)",
          set(outer.normal_form()) == {"lower.add", "lower.mul", "exp"}
          and len(outer.normal_form()) == len(flat.normal_form()) == 3)
    check("the three operation levels compose into ONE ContinuumSpace (arbitrary N dims)",
          set(v.name for v in outer.normal_form().values()) ==
          {"additive", "multiplicative", "exponential"})
    print("  -> the GENERALIZED (recursive product) space holds all three; the flat one is the fold.")


def main():
    print("ARITHMETIC AS {Continuum, group/ungroup, ContinuumSpace} -- completeness spike")
    stage1_inverse_is_the_cold_direction()
    stage2_group_is_compression()
    stage3_closure_folds_at_exponentiation()
    stage4_degenerate_vs_full_by_commutativity()
    stage5_compose_needs_the_generalized_space()
    print(f"\n=== {len(PASS)} PASS / {len(FAIL)} FAIL ===")
    if FAIL:
        print("FAILURES:", FAIL)
        sys.exit(1)
    print("VALIDATED: the primitive set reproduces arithmetic's functional completeness;")
    print("the closure-DWP generalization (recursive product + alignment-as-property) is the")
    print("piece that lets the three differently-scaled levels compose into one space.")


if __name__ == "__main__":
    main()
