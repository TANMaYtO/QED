# Problem Specification: Circle Packing in a Unit Square (n=26)

## 1. Problem Statement

Pack $n = 26$ non-overlapping circles $C_0, C_1, \dots, C_{25}$ entirely inside the closed two-dimensional unit square $[0, 1] \times [0, 1]$ so as to maximize the sum of their radii.

Each circle $C_i$ is defined by its center coordinates $(x_i, y_i) \in \mathbb{R}^2$ and its radius $r_i \in \mathbb{R}$.

$$\text{Maximize } \sum_{i=0}^{25} r_i$$

---

## 2. Precise Definition of a Valid Construction

A configuration $((x_0, y_0, r_0), \dots, (x_{25}, y_{25}, r_{25}))$ is **valid** if and only if all of the following conditions are strictly satisfied:

1. **Non-negativity of Radii**:
   $$r_i \ge 0 \quad \forall i \in \{0, \dots, 25\}$$

2. **Containment in Unit Square**:
   Every circle $C_i$ must be completely contained within $[0, 1] \times [0, 1]$:
   $$x_i - r_i \ge 0 \quad \text{and} \quad x_i + r_i \le 1 \quad \forall i \in \{0, \dots, 25\}$$
   $$y_i - r_i \ge 0 \quad \text{and} \quad y_i + r_i \le 1 \quad \forall i \in \{0, \dots, 25\}$$

3. **Pairwise Non-overlapping**:
   For every distinct pair of circles $i \ne j$, the interiors of $C_i$ and $C_j$ do not intersect:
   $$\sqrt{(x_i - x_j)^2 + (y_i - y_j)^2} \ge r_i + r_j \quad \forall 0 \le i < j < 26$$
   Equivalently, in squared Euclidean distance:
   $$(x_i - x_j)^2 + (y_i - y_j)^2 \ge (r_i + r_j)^2$$

4. **Completeness & Determinism**:
   The output must contain exactly $n = 26$ circles with finite numeric coordinates and radii (no `NaN` or infinite values).

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
