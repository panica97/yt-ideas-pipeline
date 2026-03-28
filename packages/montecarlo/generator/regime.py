"""
N-State Regime Switching model for Monte Carlo simulation.

Detects market regimes (e.g. "calm", "normal", "stressed") from historical
returns via Gaussian HMM-style EM algorithm with Dirichlet persistence prior
and minimum-duration label smoothing.

Supports 2 or 3 states with automatic BIC-based state-count selection.
"""

from __future__ import annotations

import numpy as np
from typing import List, Tuple

from ..config import MonteCarloConfig


# Human-readable labels by state count
_REGIME_LABELS = {
    2: ["normal", "stressed"],
    3: ["calm", "normal", "stressed"],
}


class RegimeDetector:
    """N-State Markov regime switching model.

    States are ordered by variance (ascending): regime 0 has the lowest
    volatility, regime N-1 has the highest.

    After fitting, provides:
      - Transition matrix P (n_states x n_states)
      - Regime-specific return means and variances
      - Smoothed regime probabilities for classification
    """

    def __init__(self, n_states: int = 2) -> None:
        self.n_states = n_states

        # Transition matrix P[i,j] = P(regime_t = j | regime_{t-1} = i)
        self.transition_matrix: np.ndarray | None = None

        # Per-regime parameters
        self.regime_means: np.ndarray | None = None    # (n_states,)
        self.regime_vars: np.ndarray | None = None     # (n_states,)
        self.steady_state: np.ndarray | None = None    # (n_states,)

        # Classification results
        self.regime_labels: np.ndarray | None = None   # (T,) 0..n_states-1
        self.regime_probs: np.ndarray | None = None    # (T, n_states)

        self._fitted = False
        self._bic: float | None = None
        self._log_likelihood: float | None = None

    # ------------------------------------------------------------------
    # Fitting via EM algorithm
    # ------------------------------------------------------------------

    def fit(
        self,
        returns: np.ndarray,
        n_iter: int = 100,
        tol: float = 1e-6,
        min_duration: int = 10,
        verbose: bool = False,
    ) -> RegimeDetector:
        """Fit N-state Gaussian HMM on returns via Baum-Welch EM.

        Parameters
        ----------
        returns      : 1-D array of return observations
        n_iter       : max EM iterations
        tol          : convergence tolerance on log-likelihood
        min_duration : minimum regime segment duration in bars
        """
        T = len(returns)
        if T < MonteCarloConfig.MIN_REGIME_OBSERVATIONS:
            self._single_regime_fallback(returns)
            return self

        self._initialize(returns)

        prev_ll = -np.inf

        for iteration in range(n_iter):
            gamma, xi, log_likelihood = self._e_step(returns)

            if abs(log_likelihood - prev_ll) < tol:
                if verbose:
                    print(f"  Regime EM ({self.n_states}-state) converged at "
                          f"iteration {iteration}, LL={log_likelihood:.2f}")
                break
            prev_ll = log_likelihood

            self._m_step(returns, gamma, xi)

        # Ensure regimes are ordered by ascending variance
        self._order_regimes()

        # Final E-step with ordered parameters
        gamma, _, log_likelihood = self._e_step(returns)
        self.regime_probs = gamma
        self.regime_labels = np.argmax(gamma, axis=1)
        self._log_likelihood = log_likelihood

        # Smooth labels: enforce minimum segment duration
        if min_duration > 1:
            self._smooth_labels(returns, min_duration, verbose)

        self._compute_steady_state()
        self._compute_bic(T)
        self._fitted = True

        if verbose:
            labels = self._get_labels()
            for k in range(self.n_states):
                frac = float(np.mean(self.regime_labels == k))
                print(f"  Regime {k} ({labels[k]}): mu={self.regime_means[k]:.6f}, "
                      f"var={self.regime_vars[k]:.6f}, "
                      f"P(stay)={self.transition_matrix[k,k]:.3f}, "
                      f"frac={frac:.1%}")
            ss_str = ", ".join(
                f"{labels[k]}={self.steady_state[k]:.2%}"
                for k in range(self.n_states)
            )
            print(f"  Steady state: {ss_str}")
            print(f"  BIC={self._bic:.1f}")

        return self

    @classmethod
    def fit_best(
        cls,
        returns: np.ndarray,
        max_states: int = 3,
        min_bars_for_3: int = 5000,
        verbose: bool = False,
        **fit_kwargs,
    ) -> RegimeDetector:
        """Try 2..max_states HMMs and select by BIC."""
        T = len(returns)
        best: RegimeDetector | None = None
        best_bic = np.inf

        for n in range(2, max_states + 1):
            if n >= 3 and T < min_bars_for_3:
                if verbose:
                    print(f"  Regime auto-select: skipping {n}-state "
                          f"(need {min_bars_for_3} bars, have {T})")
                break

            detector = cls(n_states=n)
            detector.fit(returns, verbose=verbose, **fit_kwargs)

            if not detector._fitted:
                continue

            if verbose:
                print(f"  Regime auto-select: {n}-state BIC={detector._bic:.1f}")

            if detector._bic < best_bic:
                best_bic = detector._bic
                best = detector

        if best is None:
            fallback = cls(n_states=2)
            fallback._single_regime_fallback(returns)
            return fallback

        if verbose:
            print(f"  Regime auto-select: chose {best.n_states}-state "
                  f"(BIC={best._bic:.1f})")

        return best

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def simulate_regimes(
        self,
        n_periods: int,
        n_paths: int = 1,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """Generate regime sequences via Markov chain.

        Returns
        -------
        regimes : ndarray of shape (n_paths, n_periods), values 0..n_states-1
        """
        if not self._fitted:
            raise RuntimeError("RegimeDetector must be fitted before simulation")

        if rng is None:
            rng = np.random.default_rng()

        n_states = self.n_states
        regimes = np.zeros((n_paths, n_periods), dtype=np.int32)

        # Initial regime from steady-state distribution
        regimes[:, 0] = rng.choice(n_states, size=n_paths, p=self.steady_state)

        P = self.transition_matrix

        if n_states == 2:
            # Optimised binary path
            for t in range(1, n_periods):
                u = rng.uniform(size=n_paths)
                current = regimes[:, t - 1]
                prob_zero = P[current, 0]
                regimes[:, t] = (u > prob_zero).astype(np.int32)
        else:
            # General N-state Markov chain via cumulative probabilities
            for t in range(1, n_periods):
                u = rng.uniform(size=n_paths)
                current = regimes[:, t - 1]
                cum_prob = np.cumsum(P[current], axis=1)
                regimes[:, t] = np.sum(
                    u[:, np.newaxis] > cum_prob[:, :-1], axis=1
                ).astype(np.int32)

        return regimes

    def get_regime_params(self, regime: int) -> dict:
        """Return GARCH-relevant parameters for a specific regime."""
        return {
            "mean": float(self.regime_means[regime]),
            "variance": float(self.regime_vars[regime]),
        }

    # ------------------------------------------------------------------
    # E-step: Forward-Backward algorithm (N-state)
    # ------------------------------------------------------------------

    def _e_step(
        self,
        returns: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Forward-backward algorithm for N-state Gaussian HMM.

        Returns
        -------
        gamma : (T, n_states) smoothed state probabilities
        xi    : (T-1, n_states, n_states) transition probabilities
        log_likelihood : total log-likelihood
        """
        T = len(returns)
        n = self.n_states
        P = self.transition_matrix

        # Emission probabilities: Gaussian likelihood for each regime
        emission = np.zeros((T, n))
        for k in range(n):
            sigma = np.sqrt(np.maximum(self.regime_vars[k], 1e-12))
            emission[:, k] = (
                1.0 / (sigma * np.sqrt(2.0 * np.pi))
                * np.exp(-0.5 * ((returns - self.regime_means[k]) / sigma) ** 2)
            )
        emission = np.maximum(emission, 1e-300)  # numerical floor

        # Forward pass (scaled)
        alpha = np.zeros((T, n))
        scale = np.zeros(T)

        alpha[0] = self.steady_state * emission[0]
        scale[0] = np.sum(alpha[0])
        alpha[0] /= scale[0]

        for t in range(1, T):
            alpha[t] = emission[t] * (alpha[t - 1] @ P)
            scale[t] = np.sum(alpha[t])
            if scale[t] > 0:
                alpha[t] /= scale[t]
            else:
                alpha[t] = 1.0 / n  # uniform fallback
                scale[t] = 1e-300

        log_likelihood = float(np.sum(np.log(np.maximum(scale, 1e-300))))

        # Backward pass (scaled)
        beta = np.zeros((T, n))
        beta[-1] = 1.0

        for t in range(T - 2, -1, -1):
            beta[t] = P @ (emission[t + 1] * beta[t + 1])
            if scale[t + 1] > 0:
                beta[t] /= scale[t + 1]

        # Smoothed probabilities
        gamma = alpha * beta
        gamma_sum = gamma.sum(axis=1, keepdims=True)
        gamma_sum = np.maximum(gamma_sum, 1e-300)
        gamma = gamma / gamma_sum

        # Transition probabilities xi[t, i, j] = P(s_t=i, s_{t+1}=j | data)
        xi = np.zeros((T - 1, n, n))
        for t in range(T - 1):
            numerator = np.outer(alpha[t], emission[t + 1] * beta[t + 1]) * P
            denom = np.sum(numerator)
            if denom > 0:
                xi[t] = numerator / denom
            else:
                xi[t] = 1.0 / (n * n)  # uniform fallback

        return gamma, xi, log_likelihood

    # ------------------------------------------------------------------
    # M-step (with Dirichlet persistence prior)
    # ------------------------------------------------------------------

    def _m_step(
        self,
        returns: np.ndarray,
        gamma: np.ndarray,
        xi: np.ndarray,
    ) -> None:
        """Update parameters from smoothed probabilities.

        The transition matrix update includes a Dirichlet prior that
        favors persistence (staying in the same regime).
        """
        n = self.n_states
        prior = MonteCarloConfig.REGIME_PERSISTENCE_PRIOR

        for k in range(n):
            w = gamma[:, k]
            w_sum = np.sum(w)
            if w_sum < 1e-10:
                continue

            self.regime_means[k] = np.sum(w * returns) / w_sum
            self.regime_vars[k] = np.sum(w * (returns - self.regime_means[k]) ** 2) / w_sum
            # Floor variance
            self.regime_vars[k] = max(self.regime_vars[k], 1e-10)

        # Update transition matrix with Dirichlet persistence prior
        for i in range(n):
            xi_sum = np.sum(xi[:, i, :], axis=0)  # sum over time
            xi_sum[i] += prior          # favor persistence
            for j in range(n):
                if j != i:
                    xi_sum[j] += 1.0    # small count for switching
            total = np.sum(xi_sum)
            if total > 0:
                self.transition_matrix[i] = xi_sum / total
            # Ensure rows sum to 1
            row_sum = np.sum(self.transition_matrix[i])
            if row_sum > 0:
                self.transition_matrix[i] /= row_sum

    # ------------------------------------------------------------------
    # Label smoothing
    # ------------------------------------------------------------------

    def _smooth_labels(
        self,
        returns: np.ndarray,
        min_duration: int,
        verbose: bool = False,
    ) -> None:
        """Smooth regime labels by enforcing minimum segment duration.

        Short segments (< min_duration bars) are iteratively absorbed
        into the longer neighboring segment.
        """
        labels = self.regime_labels.copy()
        T = len(labels)
        n = self.n_states
        n_absorbed = 0

        for _pass in range(50):  # iterative passes
            # Build list of contiguous segments: (start, end, regime)
            segments = []
            i = 0
            while i < T:
                j = i + 1
                while j < T and labels[j] == labels[i]:
                    j += 1
                segments.append((i, j, int(labels[i])))
                i = j

            # Find the shortest segment below the threshold
            min_seg_idx = -1
            min_seg_len = min_duration
            for idx, (s, e, _) in enumerate(segments):
                seg_len = e - s
                if seg_len < min_seg_len:
                    min_seg_idx = idx
                    min_seg_len = seg_len

            if min_seg_idx == -1:
                break  # all segments satisfy min_duration

            s, e, regime = segments[min_seg_idx]

            # Absorb into the longer neighbor
            if min_seg_idx == 0:
                absorb = segments[1][2] if len(segments) > 1 else regime
            elif min_seg_idx == len(segments) - 1:
                absorb = segments[-2][2]
            else:
                prev_len = segments[min_seg_idx - 1][1] - segments[min_seg_idx - 1][0]
                next_len = segments[min_seg_idx + 1][1] - segments[min_seg_idx + 1][0]
                absorb = (segments[min_seg_idx - 1][2] if prev_len >= next_len
                          else segments[min_seg_idx + 1][2])

            labels[s:e] = absorb
            n_absorbed += 1

        self.regime_labels = labels

        # Recompute regime means, vars, transition matrix from smoothed labels
        for k in range(n):
            mask = labels == k
            n_k = int(np.sum(mask))
            if n_k > 0:
                self.regime_means[k] = float(np.mean(returns[mask]))
                self.regime_vars[k] = max(float(np.var(returns[mask])), 1e-10)

        transitions = np.zeros((n, n))
        for t in range(1, T):
            transitions[labels[t - 1], labels[t]] += 1
        for i in range(n):
            row_sum = np.sum(transitions[i])
            if row_sum > 0:
                self.transition_matrix[i] = transitions[i] / row_sum
            else:
                self.transition_matrix[i] = np.ones(n) / n

        # Recompute regime probabilities (hard assignment from labels)
        self.regime_probs = np.zeros((T, n))
        for t in range(T):
            self.regime_probs[t, labels[t]] = 1.0

        self._compute_steady_state()

        if verbose and n_absorbed > 0:
            persist = ", ".join(
                f"{self.transition_matrix[k,k]:.3f}" for k in range(n)
            )
            print(f"  Regime smoothing: absorbed {n_absorbed} short segments "
                  f"(min_duration={min_duration}), P(stay)=[{persist}]")

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _initialize(self, returns: np.ndarray) -> None:
        """Initialise parameters via volatility-based quantile split."""
        n = self.n_states
        T = len(returns)
        window = min(20, T // 5)
        if window < 5:
            window = 5

        rolling_var = np.array([
            np.var(returns[max(0, i - window):i + 1])
            for i in range(T)
        ])

        # Split into n quantiles by rolling variance
        percentiles = np.linspace(0, 100, n + 1)
        boundaries = np.percentile(rolling_var, percentiles)

        self.regime_means = np.zeros(n)
        self.regime_vars = np.zeros(n)

        for k in range(n):
            lo = boundaries[k]
            hi = boundaries[k + 1]
            if k < n - 1:
                mask = (rolling_var >= lo) & (rolling_var < hi)
            else:
                mask = (rolling_var >= lo) & (rolling_var <= hi)

            group = returns[mask]
            if len(group) > 1:
                self.regime_means[k] = np.mean(group)
                self.regime_vars[k] = max(np.var(group), 1e-10)
            else:
                self.regime_means[k] = 0.0
                self.regime_vars[k] = np.var(returns) * (1 + k)

        self.regime_vars = np.maximum(self.regime_vars, 1e-10)

        # Initial transition matrix: high persistence on diagonal
        off_diag = 0.05 / max(n - 1, 1)
        self.transition_matrix = np.full((n, n), off_diag)
        np.fill_diagonal(self.transition_matrix, 1.0 - 0.05)
        # Ensure rows sum to 1
        for i in range(n):
            self.transition_matrix[i] /= self.transition_matrix[i].sum()

        self._compute_steady_state()

    def _order_regimes(self) -> None:
        """Ensure regimes are ordered by ascending variance."""
        order = np.argsort(self.regime_vars)
        if np.all(order == np.arange(self.n_states)):
            return  # already ordered

        self.regime_means = self.regime_means[order]
        self.regime_vars = self.regime_vars[order]
        self.transition_matrix = self.transition_matrix[order][:, order]

    def _compute_steady_state(self) -> None:
        """Compute ergodic (steady-state) probabilities from transition matrix."""
        P = self.transition_matrix
        n = self.n_states

        if n == 2:
            # Analytical formula for 2-state
            p01 = P[0, 1]
            p10 = P[1, 0]
            denom = p01 + p10
            if denom > 1e-10:
                self.steady_state = np.array([p10 / denom, p01 / denom])
            else:
                self.steady_state = np.array([0.5, 0.5])
        else:
            # Eigenvalue decomposition for N-state
            eigenvalues, eigenvectors = np.linalg.eig(P.T)
            idx = np.argmin(np.abs(eigenvalues - 1.0))
            pi = np.real(eigenvectors[:, idx])
            pi = np.abs(pi)
            total = pi.sum()
            if total > 1e-10:
                self.steady_state = pi / total
            else:
                self.steady_state = np.ones(n) / n

    def _compute_bic(self, T: int) -> None:
        """Compute BIC for model selection."""
        if self._log_likelihood is None:
            self._bic = np.inf
            return
        n = self.n_states
        # Free parameters: n*(n-1) transition probs + n means + n variances
        k = n * (n - 1) + 2 * n
        self._bic = -2.0 * self._log_likelihood + k * np.log(T)

    def _single_regime_fallback(self, returns: np.ndarray) -> None:
        """Fallback when data is insufficient for regime detection."""
        n = self.n_states
        mu = np.mean(returns)
        var = max(np.var(returns), 1e-10)
        self.regime_means = np.full(n, mu)
        self.regime_vars = np.full(n, var)
        self.transition_matrix = np.eye(n)
        self.steady_state = np.zeros(n)
        self.steady_state[0] = 1.0
        self.regime_labels = np.zeros(len(returns), dtype=np.int32)
        self.regime_probs = np.zeros((len(returns), n))
        self.regime_probs[:, 0] = 1.0
        self._fitted = True

    def _get_labels(self) -> List[str]:
        """Get human-readable labels for each regime."""
        return _REGIME_LABELS.get(
            self.n_states,
            [f"regime_{k}" for k in range(self.n_states)]
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        if not self._fitted:
            return {"fitted": False}

        labels = self._get_labels()
        d = {
            "fitted": True,
            "n_states": self.n_states,
            "transition_matrix": self.transition_matrix.tolist(),
            "regime_means": self.regime_means.tolist(),
            "regime_vars": self.regime_vars.tolist(),
            "steady_state": self.steady_state.tolist(),
        }

        for k in range(self.n_states):
            d[f"regime_{k}_pct"] = float(self.steady_state[k])
            d[f"regime_{k}_label"] = labels[k]
            d[f"persistence_{labels[k]}"] = float(self.transition_matrix[k, k])

        # Backward compatibility for 2-state
        if self.n_states == 2:
            d["regime_0_label"] = "normal"
            d["regime_1_label"] = "stressed"
            d["persistence_normal"] = float(self.transition_matrix[0, 0])
            d["persistence_stressed"] = float(self.transition_matrix[1, 1])

        if self._bic is not None:
            d["bic"] = float(self._bic)

        return d

    @classmethod
    def from_dict(cls, params: dict) -> RegimeDetector:
        n_states = params.get("n_states", 2)
        obj = cls(n_states=n_states)
        if not params.get("fitted", False):
            return obj

        obj.transition_matrix = np.array(params["transition_matrix"])
        obj.regime_means = np.array(params["regime_means"])
        obj.regime_vars = np.array(params["regime_vars"])
        obj.steady_state = np.array(params["steady_state"])
        obj._bic = params.get("bic")
        obj._fitted = True
        return obj
