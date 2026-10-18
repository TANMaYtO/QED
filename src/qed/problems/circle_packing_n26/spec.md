# Problem Specification: Circle Packing in a Unit Square (n=26)

## 1. Problem Statement

Pack $n = 26$ non-overlapping circles $C_0, C_1, \dots, C_{25}$ entirely inside the closed two-dimensional unit square $[0, 1] \times [0, 1]$ so as to maximize the sum of their radii.

Each circle $C_i$ is defined by its center coordinates $(x_i, y_i) \in \mathbb{R}^2$ and its radius $r_i \in \mathbb{R}$.

$$\text{Maximize } \sum_{i=0}^{25} r_i$$

---

## 2. Precise Definition of a Valid Construction

A configuration $((x_0, y_0, r_0), \dots, (x_{25}, y_{25}, r_{25}))$ is **valid** if and only if all of the following conditions are strictly satisfied:

1. **Strict Positivity of Radii**:
   $$r_i > 0 \quad \forall i \in \{0, \dots, 25\}$$
   Zero or negative radii ($r_i \le 0$) are strictly invalid.

2. **Containment in Unit Square**:
   Every circle $C_i$ must be completely contained within $[0, 1] \times [0, 1]$:
   $$x_i - r_i \ge 0 \quad \text{and} \quad 1 - (x_i + r_i) \ge 0 \quad \forall i \in \{0, \dots, 25\}$$
   $$y_i - r_i \ge 0 \quad \text{and} \quad 1 - (y_i + r_i) \ge 0 \quad \forall i \in \{0, \dots, 25\}$$
   Tangency to any of the four boundaries (exact equality, slack $= 0$) is explicitly **VALID**.

3. **Pairwise Non-overlapping**:
   For every distinct pair of circles $i < j$, the interiors of $C_i$ and $C_j$ must not intersect:
   $$(x_i - x_j)^2 + (y_i - y_j)^2 \ge (r_i + r_j)^2 \quad \forall 0 \le i < j < 26$$
   Tangency between circles (exact equality $(x_i - x_j)^2 + (y_i - y_j)^2 = (r_i + r_j)^2$, slack $= 0$) is explicitly **VALID**.

4. **Exact Rational Score**:
   The score of a valid construction is the exact sum of radii:
   $$\text{Score} = \sum_{i=0}^{25} r_i$$
   computed in exact rational arithmetic as an irreducible fraction $p/q$ ($\gcd(p, q) = 1, q \in \mathbb{Z}^+$).

---

## 3. Fast In-Loop Evaluator Tolerance

The fast in-loop evaluator (`evaluator_fast.py`) uses IEEE 754 floating-point arithmetic for candidate screening during evolutionary search. To accommodate rounding variations in floating-point optimizers, it permits a small numerical slack:

$$\epsilon_{\text{fast}} = 10^{-6}$$

Under `evaluator_fast.py`:
- Boundary containment: $x_i - r_i \ge -\epsilon_{\text{fast}}$, $x_i + r_i \le 1 + \epsilon_{\text{fast}}$, etc.
- Pairwise separation: $\text{dist}(C_i, C_j) \ge r_i + r_j - \epsilon_{\text{fast}}$.

> [!WARNING]
> **fast evaluator only; never gates a claim**
> Any claim of a new record or certified reproduction MUST pass the exact verification layer (`qed.trust`) using exact rational arithmetic (`fractions.Fraction`) with zero tolerance.

---

## 4. Execution Isolation & Sandbox Assessment

To safeguard the host environment during candidate program evaluation:

### Achieved Isolation
1. **Subprocess Wall-Clock Timeout**: Every candidate program runs in an isolated Python subprocess with a hard wall-clock timeout (`communicate(timeout=...)`). Any hung, infinite, or excessively slow process is forcibly terminated.
2. **Environment Sanitization**: Sensitive environment variables (including `GEMINI_API_KEY`, `OPENAI_API_KEY`, and system credentials) are explicitly scrubbed from the subprocess environment before execution.
3. **Execution in Ephemeral Work Directory**: Generated code runs in temporary scratch directories with results communicated via serialized pipes.

### Unachieved Isolation (OS Constraints)
- **Kernel-level Network Namespace**: On Windows host environments, unprivileged user processes cannot create isolated network namespaces (such as Linux `unshare -n` or `bubblewrap --unshare-net`). Complete socket isolation without administrator privileges or container virtualization (e.g. Windows Containers / Hyper-V) is unachieved.
- **Resource Memory Cgroups**: Windows job objects can limit memory, but unprivileged Python scripts rely on standard OS process limits.

---

## 5. Construction File Format

This section defines the canonical data interchange format for 26-circle packings. An independent checker written blind from this specification alone must enforce every rule specified here.

### 5.1 JSON Object Schema
A construction file must be a single UTF-8 encoded JSON object with exactly two keys:
- `"centers"`: a list of exactly 26 items. Each item must be a two-element list of strings: `[x_i, y_i]`.
- `"radii"`: a list of exactly 26 strings: `r_i`.

Any of the following constitutes an immediate format error (file rejection):
- Missing keys (e.g. `"radii"` omitted).
- Extra keys (e.g. a `"metadata"` or `"notes"` key present).
- Duplicate keys in the JSON object (e.g. two `"radii"` keys; parsers must reject duplicate keys).
- Top-level value is not a JSON object (e.g. a list or scalar).
- `"centers"` length is not 26, or any coordinate pair is not a 2-element list.
- `"radii"` length is not 26.
- Any coordinate or radius is not a JSON string (e.g. bare JSON numbers `0.5`, booleans, null).

### 5.2 Exact Number String Grammar
Every number string in `"centers"` and `"radii"` represents an exact rational number $\frac{p}{q} \in \mathbb{Q}$.
The string must strictly conform to either the **Decimal** or **Fraction** format without exception:

1. **Decimal Grammar**:
   - Matches regular expression: `^[+-]?(?:\d+\.\d+|\d+\.|\.\d+|\d+)$`
   - Consists of an optional sign (`+` or `-`), followed by digits with at most one decimal point `.`.
   - Examples of valid patterns:
     - Digits on both sides: `0.5`, `-0.125`, `+12.34567`
     - Leading dot: `.5`, `-.001`, `+.25`
     - Trailing dot: `5.`, `-10.`, `+0.`
     - Pure integer digits: `0`, `1`, `-5`, `+42`, `007`
   - Leading zeros in the integer or fractional portion are allowed.

2. **Fraction Grammar**:
   - Matches regular expression: `^[+-]?\d+/[1-9]\d*$`
   - Consists of an optional sign (`+` or `-`), followed by one or more numerator digits, followed by a literal slash `/`, followed by one or more denominator digits.
   - The denominator MUST be strictly positive ($q \ge 1$); a denominator of zero is rejected (`/0` or `/00` is invalid).
   - The denominator MUST NOT have a sign (no `/-2` or `/+2`).

3. **Strictly Rejected Syntax**:
   - **Whitespace**: Any whitespace (leading, trailing, or internal) is forbidden (e.g. `" 1/2"`, `"1/2 "`, `"1 / 2"`).
   - **Scientific notation**: Exponential markers `e` or `E` are forbidden (e.g. `"1e-5"`, `"2.5E+3"`).
   - **Special symbols**: `NaN`, `Inf`, `Infinity` (case-insensitive) are forbidden.
   - **Multiple operators/delimiters**: Multiple dots or slashes are forbidden (e.g. `"1.2.3"`, `"1/2/3"`).
   - **Non-numeric characters**: Alphabetic or trailing garbage is forbidden (e.g. `"abc"`, `"1/2abc"`).
   - **Empty string**: `""` is forbidden.

#### Examples of Accepted Number Strings (14 examples)
| String | Parsed Rational Value | Notes |
|---|---|---|
| `"0"` | $0$ | Integer zero |
| `"1"` | $1$ | Positive integer |
| `"-5"` | $-5$ | Negative integer |
| `"+7"` | $7$ | Explicit positive sign |
| `"0.5"` | $1/2$ | Standard decimal |
| `".5"` | $1/2$ | Decimal without leading zero |
| `"5."` | $5$ | Decimal with trailing point |
| `"-0.125"` | $-1/8$ | Negative decimal |
| `"+007.25"` | $29/4$ | Leading zeros allowed |
| `"1/2"` | $1/2$ | Irreducible fraction |
| `"-3/4"` | $-3/4$ | Negative numerator |
| `"+26/1"` | $26$ | Positive fraction with unit denominator |
| `"12345/67890"` | $823/4526$ | Reducible large fraction |
| `"0/1"` | $0$ | Fraction representing zero |

#### Examples of Rejected Number Strings (14 examples)
| String | Rejection Reason |
|---|---|
| `""` | Empty string |
| `"   "` | Whitespace only |
| `" 1/2"` | Leading whitespace |
| `"1/2 "` | Trailing whitespace |
| `"1 / 2"` | Internal whitespace |
| `"1e-5"` | Scientific notation (`e`) |
| `"2.5E+3"` | Scientific notation (`E`) |
| `"nan"` / `"NaN"` | Not-a-Number special value |
| `"inf"` / `"-infinity"` | Infinity special values |
| `"1/0"` | Zero denominator |
| `"1/-2"` | Signed / negative denominator |
| `"1/2/3"` | Multiple slashes |
| `"1.2.3"` | Multiple decimal points |
| `"1/2abc"` / `"abc"` | Alphabetic / trailing junk |

### 5.3 Geometric Validity Rules in Plain Math
Given parsed exact rational centers $(x_i, y_i) \in \mathbb{Q}^2$ and radii $r_i \in \mathbb{Q}$ for $i \in \{0, \dots, 25\}$:

1. **Circle Count**: Exactly 26 circles must be present.
2. **Strict Positivity**:
   $$\forall i \in \{0, \dots, 25\}: \quad r_i > 0$$
   Any radius $r_i \le 0$ produces a `non_positive_radius` violation with slack $= r_i \le 0$.
3. **Unit Square Containment**:
   Every circle $C_i$ must lie inside $[0, 1] \times [0, 1]$:
   - Left boundary: $x_i - r_i \ge 0$ (slack: $x_i - r_i$)
   - Right boundary: $1 - (x_i + r_i) \ge 0$ (slack: $1 - (x_i + r_i)$)
   - Bottom boundary: $y_i - r_i \ge 0$ (slack: $y_i - r_i$)
   - Top boundary: $1 - (y_i + r_i) \ge 0$ (slack: $1 - (y_i + r_i)$)
   **Tangency rule**: Contact with any boundary (slack $= 0$) is explicitly **VALID**.
4. **Pairwise Non-overlapping**:
   For every pair $0 \le i < j < 26$:
   $$(x_i - x_j)^2 + (y_i - y_j)^2 - (r_i + r_j)^2 \ge 0$$
   Overlap slack is defined as $((x_i - x_j)^2 + (y_i - y_j)^2) - (r_i + r_j)^2$.
   **Tangency rule**: Circles touching at a single point (slack $= 0$) are explicitly **VALID**.
5. **Exact Score**:
   The objective score is:
   $$\text{Score} = \sum_{i=0}^{25} r_i$$
   computed in exact arithmetic as an irreducible fraction $p/q$ ($\gcd(p, q) = 1, q \ge 1$).

### 5.4 Checker Output Convention
Any conforming verification tool or checker script must follow this stdout convention:
- **On Success (Valid construction)**:
  Print a single line starting with `VALID` followed by the exact score as an irreducible fraction $p/q$:
  ```
  VALID 38/15
  ```
- **On Failure (Invalid construction)**:
  Print `INVALID` on the first line, followed by one line per detected constraint violation reporting the violation type, circle indices, and exact rational slack:
  ```
  INVALID
  circle_overlap: indices=(0, 1), slack=-3/100
  boundary_left_breach: indices=(5,), slack=-1/20
  ```

