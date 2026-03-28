"""
GJR-GARCH(1,1) with Hansen's Skewed Student-t innovations and Merton jump diffusion.

Variance dynamics (asymmetric / leverage effect):
    sigma^2_t = omega + alpha * eps^2_{t-1} + gamma * eps^2_{t-1} * I(eps_{t-1}<0) + beta * sigma^2_{t-1}

Innovations:
    z_t ~ SkewedStudentT(nu, lambda)   [Hansen 1994]

Jump component (Merton-style):
    J_t ~ Bernoulli(jump_prob) * Normal(jump_mean, jump_std)
    r_t = mu + sigma_t * z_t + J_t
"""

from __future__ import annotations

import numpy as np
from scipy import stats
from scipy.optimize import minimize
from scipy.special import gammaln
from typing import Tuple

from ..config import MonteCarloConfig


# ======================================================================
# Hansen's Skewed Student-t distribution
# ======================================================================

def _skewed_t_constants(nu: float, lam: float) -> Tuple[float, float, float]:
    """Compute constants a, b, c for Hansen's skewed Student-t.

    Parameters
    ----------
    nu  : degrees of freedom (> 2)
    lam : skewness parameter (-1, 1)

    Returns
    -------
    a, b, c : constants used in the PDF and sampling
    """
    c = np.exp(
        gammaln((nu + 1.0) / 2.0)
        - gammaln(nu / 2.0)
        - 0.5 * np.log(np.pi * (nu - 2.0))
    )
    a = 4.0 * lam * c * (nu - 2.0) / (nu - 1.0)
    b2 = 1.0 + 3.0 * lam ** 2 - a ** 2
    b = np.sqrt(np.maximum(b2, 1e-12))
    return a, b, c


def skewed_t_logpdf(z: np.ndarray, nu: float, lam: float) -> np.ndarray:
    """Log-PDF of Hansen's (1994) skewed Student-t distribution.

    Parameters
    ----------
    z   : standardised innovations
    nu  : degrees of freedom (> 2)
    lam : skewness in (-1, 1). lam < 0 => left-skewed (heavier left tail).
    """
    a, b, c = _skewed_t_constants(nu, lam)
    y = b * z + a  # shifted and scaled

    # Two branches: left tail uses (1-lam), right tail uses (1+lam)
    mask_left = z < (-a / b)
    denom = np.where(mask_left, 1.0 - lam, 1.0 + lam)

    kernel = 1.0 + (1.0 / (nu - 2.0)) * (y / denom) ** 2
    log_kernel = -(nu + 1.0) / 2.0 * np.log(kernel)
    return np.log(b) + np.log(c) + log_kernel


def skewed_t_rvs(
    nu: float,
    lam: float,
    size: Tuple[int, ...],
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample from Hansen's skewed Student-t via inverse-CDF transform.

    Uses the relationship between the skewed-t and the standard t.
    """
    a, b, c = _skewed_t_constants(nu, lam)

    # Sample uniform
    u = rng.uniform(size=size)

    # Threshold probability at z = -a/b
    # For z < -a/b: F uses (1-lam), for z >= -a/b: F uses (1+lam)
    # The split point in u-space:
    p_threshold = (1.0 - lam) / 2.0

    # Standard t quantiles
    # Left branch: u < p_threshold
    # Right branch: u >= p_threshold
    z = np.empty(size)
    left = u < p_threshold
    right = ~left

    if np.any(left):
        # Map u to [0, 1] in the left branch
        u_left = u[left] / p_threshold
        t_quantile = stats.t.ppf(u_left / 2.0, df=nu)  # half the mass
        z[left] = ((1.0 - lam) * t_quantile * np.sqrt((nu - 2.0) / nu) - a) / b

    if np.any(right):
        # Map u to [0, 1] in the right branch
        u_right = (u[right] - p_threshold) / (1.0 - p_threshold)
        t_quantile = stats.t.ppf(0.5 + u_right / 2.0, df=nu)
        z[right] = ((1.0 + lam) * t_quantile * np.sqrt((nu - 2.0) / nu) - a) / b

    return z


# ======================================================================
# GJR-GARCH(1,1) with skewed-t + jump diffusion
# ======================================================================

class GJR_GARCH:
    """GJR-GARCH(1,1) with Hansen's skewed Student-t innovations
    and Merton-style jump diffusion.

    Captures:
    - Volatility clustering (alpha, beta persistence)
    - Leverage / asymmetry effect (gamma — negative shocks inflate vol more)
    - Fat tails (nu — Student-t degrees of freedom)
    - Skewness (lam — Hansen's skew parameter)
    - Discontinuous jumps (jump_prob, jump_mean, jump_std)
    """

    def __init__(self) -> None:
        # GJR-GARCH parameters
        self.omega: float | None = None
        self.alpha: float | None = None
        self.beta: float | None = None
        self.gamma: float | None = None  # leverage / asymmetry

        # Skewed-t parameters
        self.nu: float | None = None     # degrees of freedom
        self.lam: float | None = None    # skewness (-1, 1)

        # Jump diffusion parameters
        self.jump_prob: float | None = None   # probability of jump per period
        self.jump_mean: float | None = None   # mean jump size
        self.jump_std: float | None = None    # jump volatility

        # Return statistics
        self.long_run_var: float | None = None
        self.mu: float | None = None
        self.returns_std: float | None = None

        # AR(1) mean dynamics
        self.phi: float = 0.0  # autoregressive coefficient (0 = no AR)

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(self, returns: np.ndarray, verbose: bool = False) -> GJR_GARCH:
        """Fit GJR-GARCH(1,1) with skewed-t + jump diffusion via MLE.

        Three-stage fitting:
          1. Fit GJR-GARCH + skewed-t (with optional variance targeting)
          2. Fit jump component on residuals
          3. Calibrate nu to match historical kurtosis (post-fit)
        """
        self.mu = float(np.mean(returns))
        self.returns_std = float(np.std(returns))

        # Standardise for numerical stability
        r = (returns - self.mu) / self.returns_std

        # --- Stage 1: GJR-GARCH + skewed-t ---
        use_vt = MonteCarloConfig.GARCH_VARIANCE_TARGETING
        self._fit_gjr_skewed_t(r, verbose, variance_targeting=use_vt)

        # --- Stage 2: Jump detection on residuals ---
        self._fit_jumps(r, verbose)

        # --- Stage 3: Kurtosis calibration ---
        if MonteCarloConfig.GARCH_KURTOSIS_CALIBRATION:
            self._calibrate_kurtosis(r, verbose)

        # --- Stage 4: AR(1) mean dynamics ---
        if MonteCarloConfig.GARCH_AR1_ENABLED:
            self._fit_ar1(returns, verbose)

        return self

    def _fit_gjr_skewed_t(
        self,
        r: np.ndarray,
        verbose: bool,
        variance_targeting: bool = False,
    ) -> None:
        """Fit GJR-GARCH(1,1) with Hansen's skewed Student-t.

        When variance_targeting=True, omega is derived from the sample
        variance: omega = sample_var * (1 - alpha - gamma/2 - beta),
        guaranteeing long_run_var = sample_var.  This removes omega as a
        free parameter and prevents degenerate persistence.
        """
        max_persistence = MonteCarloConfig.GARCH_MAX_PERSISTENCE
        nu_lb = MonteCarloConfig.GARCH_NU_LOWER_BOUND
        sample_var = float(np.var(r))

        if variance_targeting:
            # 5 free params: alpha, gamma, beta, nu, lam
            # omega is computed from the constraint
            bounds = [
                (1e-6, 0.5),     # alpha
                (1e-6, 0.5),     # gamma (leverage)
                (1e-6, 0.999),   # beta
                (nu_lb, 50.0),   # nu
                (-0.9, 0.9),     # lambda (skewness)
            ]
            constraints = {
                "type": "ineq",
                "fun": lambda x: max_persistence - x[0] - x[1] / 2.0 - x[2],
            }

            def _nll_vt(params, returns):
                alpha, gamma, beta, nu, lam = params
                persistence = alpha + gamma / 2.0 + beta
                omega = sample_var * max(1e-6, 1.0 - persistence)
                full_params = np.array([omega, alpha, gamma, beta, nu, lam])
                return GJR_GARCH._neg_log_likelihood_gjr(full_params, returns)

            opts = {"maxiter": MonteCarloConfig.GARCH_MAX_ITER}
            best_result = None

            for attempt in range(MonteCarloConfig.GARCH_N_RESTARTS):
                if attempt == 0:
                    p = MonteCarloConfig.GARCH_INITIAL_PARAMS
                    x0 = [p['alpha'], p.get('gamma', 0.1), p['beta'],
                           p['nu'], p.get('lam', -0.1)]
                else:
                    rng_init = np.random.default_rng(seed=attempt)
                    x0 = [
                        rng_init.uniform(0.01, 0.2),
                        rng_init.uniform(0.01, 0.3),
                        rng_init.uniform(0.5, 0.95),
                        rng_init.uniform(5.0, 20.0),
                        rng_init.uniform(-0.5, 0.1),
                    ]
                try:
                    result = minimize(
                        _nll_vt, x0, args=(r,),
                        method="SLSQP", bounds=bounds,
                        constraints=constraints, options=opts,
                    )
                    if result.success or best_result is None:
                        if best_result is None or result.fun < best_result.fun:
                            best_result = result
                        if result.success:
                            break
                except Exception:
                    continue

            if best_result is None:
                if verbose:
                    print("  GJR-GARCH: variance-targeting fit failed, "
                          "falling back to free-omega")
                self._fit_gjr_skewed_t(r, verbose, variance_targeting=False)
                return

            self.alpha, self.gamma, self.beta, self.nu, self.lam = best_result.x
            persistence = self.alpha + self.gamma / 2.0 + self.beta
            self.omega = sample_var * max(1e-6, 1.0 - persistence)
            self.long_run_var = sample_var  # by construction

            if verbose:
                print(f"  GJR-GARCH fit (VT): omega={self.omega:.6f}, "
                      f"alpha={self.alpha:.4f}, gamma={self.gamma:.4f}, "
                      f"beta={self.beta:.4f}, nu={self.nu:.2f}, "
                      f"lam={self.lam:.4f}, LRV={self.long_run_var:.4f}")
            return

        # --- Free-omega fitting (fallback) ---
        bounds = [
            (1e-6, 1.0),       # omega
            (1e-6, 0.5),       # alpha
            (1e-6, 0.5),       # gamma (leverage)
            (1e-6, 0.999),     # beta
            (nu_lb, 50.0),     # nu
            (-0.9, 0.9),       # lambda (skewness)
        ]
        constraints = {
            "type": "ineq",
            "fun": lambda x: max_persistence - x[1] - x[2] / 2.0 - x[3],
        }
        opts = {"maxiter": MonteCarloConfig.GARCH_MAX_ITER}

        best_result = None

        for attempt in range(MonteCarloConfig.GARCH_N_RESTARTS):
            if attempt == 0:
                p = MonteCarloConfig.GARCH_INITIAL_PARAMS
                x0 = [
                    p['omega'], p['alpha'], p.get('gamma', 0.1),
                    p['beta'], p['nu'], p.get('lam', -0.1),
                ]
            else:
                rng_init = np.random.default_rng(seed=attempt)
                x0 = [
                    rng_init.uniform(0.01, 0.3),
                    rng_init.uniform(0.01, 0.2),
                    rng_init.uniform(0.01, 0.3),
                    rng_init.uniform(0.5, 0.95),
                    rng_init.uniform(5.0, 20.0),
                    rng_init.uniform(-0.5, 0.1),
                ]

            try:
                result = minimize(
                    self._neg_log_likelihood_gjr,
                    x0,
                    args=(r,),
                    method="SLSQP",
                    bounds=bounds,
                    constraints=constraints,
                    options=opts,
                )
                if result.success or best_result is None:
                    if best_result is None or result.fun < best_result.fun:
                        best_result = result
                    if result.success:
                        break
            except Exception:
                continue

        if best_result is None:
            raise ValueError(
                "GJR-GARCH fitting failed after "
                f"{MonteCarloConfig.GARCH_N_RESTARTS} attempts."
            )

        self.omega, self.alpha, self.gamma, self.beta, self.nu, self.lam = best_result.x

        # Long-run variance: omega / (1 - alpha - gamma/2 - beta)
        denom = 1.0 - self.alpha - self.gamma / 2.0 - self.beta
        self.long_run_var = self.omega / denom if denom > 0 else self.omega / 1e-6

        # Sanity check: if long_run_var is extreme (>10x sample var in
        # standardized space), the persistence is too high.  Refit with
        # a tighter persistence constraint.
        MAX_LRV = 10.0
        if self.long_run_var > MAX_LRV:
            old_lrv = self.long_run_var
            target_denom = self.omega / MAX_LRV
            new_max_p = 1.0 - target_denom
            if new_max_p > 0.5:
                tighter_constraints = {
                    "type": "ineq",
                    "fun": lambda x, _mp=new_max_p: _mp - x[1] - x[2] / 2.0 - x[3],
                }
                try:
                    result2 = minimize(
                        self._neg_log_likelihood_gjr,
                        [self.omega, self.alpha, self.gamma, self.beta, self.nu, self.lam],
                        args=(r,),
                        method="SLSQP",
                        bounds=bounds,
                        constraints=tighter_constraints,
                        options=opts,
                    )
                    if result2.success or result2.fun < best_result.fun * 1.05:
                        self.omega, self.alpha, self.gamma, self.beta, self.nu, self.lam = result2.x
                        denom2 = 1.0 - self.alpha - self.gamma / 2.0 - self.beta
                        self.long_run_var = self.omega / denom2 if denom2 > 0 else MAX_LRV
                except Exception:
                    pass
            if verbose and self.long_run_var < old_lrv:
                print(f"  GJR-GARCH: corrected degenerate LRV "
                      f"({old_lrv:.1f} -> {self.long_run_var:.2f})")

        if verbose:
            print(f"  GJR-GARCH fit: omega={self.omega:.6f}, alpha={self.alpha:.4f}, "
                  f"gamma={self.gamma:.4f}, beta={self.beta:.4f}, "
                  f"nu={self.nu:.2f}, lam={self.lam:.4f}")

    def _calibrate_kurtosis(self, r: np.ndarray, verbose: bool) -> None:
        """Post-fit nu calibration: adjust nu so synthetic kurtosis matches historical.

        Uses multiple seeds for a stable kurtosis estimate and binary-searches
        nu until kurtosis_ratio falls within the target range.
        """
        from scipy.stats import kurtosis as _kurtosis

        target_lo, target_hi = MonteCarloConfig.GARCH_KURTOSIS_TARGET_RATIO
        hist_kurt = float(_kurtosis(r, fisher=True))
        if abs(hist_kurt) < 0.1:
            return  # near-Gaussian, nothing to calibrate

        n_test_paths = MonteCarloConfig.GARCH_KURTOSIS_TEST_PATHS
        seeds = MonteCarloConfig.GARCH_KURTOSIS_SEEDS
        nu_lb = MonteCarloConfig.GARCH_NU_LOWER_BOUND
        nu_lo, nu_hi = nu_lb, 50.0
        original_nu = self.nu

        def _measure_kurtosis(nu_test: float) -> float:
            """Simulate with candidate nu across multiple seeds, return
            median kurtosis ratio for a stable estimate."""
            saved_nu = self.nu
            self.nu = nu_test
            try:
                ratios = []
                for seed in seeds:
                    sim_ret, _ = self.simulate(
                        n_periods=len(r), n_paths=n_test_paths, seed=seed
                    )
                    flat = sim_ret.ravel()
                    flat = flat[np.isfinite(flat)]
                    if len(flat) < 100:
                        continue
                    synth_kurt = float(_kurtosis(flat, fisher=True))
                    ratio = synth_kurt / hist_kurt if abs(hist_kurt) > 0.01 else 1.0
                    ratios.append(ratio)
                return float(np.median(ratios)) if ratios else 99.0
            finally:
                self.nu = saved_nu

        # Check current ratio first
        current_ratio = _measure_kurtosis(self.nu)
        if target_lo <= current_ratio <= target_hi:
            if verbose:
                print(f"  Kurtosis calibration: ratio={current_ratio:.2f} "
                      f"already in [{target_lo}, {target_hi}], nu={self.nu:.2f}")
            return

        # Binary search: higher nu → thinner tails → lower kurtosis ratio
        best_nu = self.nu
        best_dist = abs(current_ratio - 1.0)

        for _ in range(15):
            nu_mid = (nu_lo + nu_hi) / 2.0
            ratio = _measure_kurtosis(nu_mid)
            dist = abs(ratio - 1.0)

            if dist < best_dist:
                best_dist = dist
                best_nu = nu_mid

            if target_lo <= ratio <= target_hi:
                best_nu = nu_mid
                break

            if ratio > target_hi:
                # Tails too fat → need higher nu
                nu_lo = nu_mid
            else:
                # Tails too thin → need lower nu
                nu_hi = nu_mid

            if nu_hi - nu_lo < 0.2:
                break

        self.nu = best_nu
        final_ratio = _measure_kurtosis(self.nu)

        if target_lo <= final_ratio <= target_hi:
            if verbose:
                print(f"  Kurtosis calibration: nu {original_nu:.2f} -> {self.nu:.2f}, "
                      f"ratio {current_ratio:.2f} -> {final_ratio:.2f}")
        else:
            # Always warn when calibration cannot reach target range
            print(f"  Kurtosis calibration: could not reach target "
                  f"[{target_lo}, {target_hi}]. nu {original_nu:.2f} -> "
                  f"{self.nu:.2f}, ratio={final_ratio:.2f} "
                  f"(best achievable)")

    def _fit_jumps(self, r: np.ndarray, verbose: bool) -> None:
        """Detect and fit jump component from standardised residuals.

        Uses a threshold-based approach: observations beyond 3σ of the
        fitted GARCH conditional vol are classified as jumps.
        """
        T = len(r)
        sigma2 = self._compute_sigma2(r)
        sigma = np.sqrt(np.maximum(sigma2, 1e-10))

        # Standardised residuals
        std_resid = r / sigma

        # Jump threshold: |z| > 3 (beyond 3 sigma of the GARCH model)
        jump_threshold = MonteCarloConfig.JUMP_THRESHOLD
        is_jump = np.abs(std_resid) > jump_threshold
        n_jumps = int(np.sum(is_jump))

        if n_jumps < 3:
            # Too few jumps to estimate parameters — disable jump component
            self.jump_prob = 0.0
            self.jump_mean = 0.0
            self.jump_std = 0.0
            if verbose:
                print(f"  Jumps: {n_jumps} detected (< 3), jump component disabled")
            return

        self.jump_prob = float(n_jumps / T)

        # Jump sizes = residual beyond what GARCH explains
        jump_sizes = std_resid[is_jump]
        self.jump_mean = float(np.mean(jump_sizes))
        self.jump_std = float(np.std(jump_sizes))

        # Scale back to original return scale
        self.jump_mean *= self.returns_std
        self.jump_std *= self.returns_std

        if verbose:
            print(f"  Jumps: {n_jumps} detected ({self.jump_prob:.2%}), "
                  f"mu_J={self.jump_mean:.6f}, sigma_J={self.jump_std:.6f}")

    def _fit_ar1(self, returns: np.ndarray, verbose: bool) -> None:
        """Fit AR(1) coefficient if returns show significant autocorrelation.

        Uses Ljung-Box test on first 5 lags.  If significant, estimates
        phi via OLS: r_t - mu = phi * (r_{t-1} - mu) + eps_t.
        """
        from scipy.stats import chi2

        self.phi = 0.0
        alpha = MonteCarloConfig.GARCH_AR1_LJUNGBOX_ALPHA

        # Ljung-Box test on demeaned returns (first 5 lags)
        y = returns - self.mu
        T = len(y)
        if T < 50:
            return

        max_lag = min(5, T // 10)
        acf_vals = []
        for k in range(1, max_lag + 1):
            c = np.sum(y[k:] * y[:-k]) / np.sum(y ** 2)
            acf_vals.append(c)

        # Q statistic: T*(T+2) * sum(acf_k^2 / (T-k))
        Q = T * (T + 2) * sum(
            acf_vals[k] ** 2 / (T - k - 1) for k in range(max_lag)
        )
        p_value = 1.0 - chi2.cdf(Q, df=max_lag)

        if p_value >= alpha:
            if verbose:
                print(f"  AR(1): Ljung-Box p={p_value:.3f} >= {alpha}, "
                      f"no significant autocorrelation, phi=0")
            return

        # OLS: phi = cov(y_t, y_{t-1}) / var(y_{t-1})
        phi = float(np.sum(y[1:] * y[:-1]) / np.sum(y[:-1] ** 2))

        # Clamp to stationary range
        phi = max(-0.95, min(0.95, phi))

        self.phi = phi
        if verbose:
            print(f"  AR(1): Ljung-Box p={p_value:.4f}, phi={phi:.4f}")

    def _compute_sigma2(self, r: np.ndarray) -> np.ndarray:
        """Compute conditional variance series for standardised returns."""
        T = len(r)
        sigma2 = np.empty(T)
        sigma2[0] = np.var(r)

        for t in range(1, T):
            leverage = self.gamma * r[t - 1] ** 2 * (r[t - 1] < 0)
            sigma2[t] = (
                self.omega
                + self.alpha * r[t - 1] ** 2
                + leverage
                + self.beta * sigma2[t - 1]
            )

        return np.maximum(sigma2, 1e-10)

    def in_sample_sigma(self, returns: np.ndarray) -> np.ndarray:
        """Compute in-sample conditional std in original return space.

        Standardises returns, runs the GARCH filter, and converts back
        to original scale.  Result is aligned with *returns* (same length).
        """
        r = (returns - self.mu) / self.returns_std
        sigma2_std = self._compute_sigma2(r)
        return np.sqrt(sigma2_std) * self.returns_std

    # ------------------------------------------------------------------
    # Negative log-likelihood
    # ------------------------------------------------------------------

    @staticmethod
    def _neg_log_likelihood_gjr(params: np.ndarray, returns: np.ndarray) -> float:
        """Skewed Student-t log-likelihood for GJR-GARCH(1,1)."""
        omega, alpha, gamma, beta, nu, lam = params
        T = len(returns)
        sigma2 = np.empty(T)
        sigma2[0] = np.var(returns)

        for t in range(1, T):
            leverage = gamma * returns[t - 1] ** 2 * (returns[t - 1] < 0)
            sigma2[t] = (
                omega
                + alpha * returns[t - 1] ** 2
                + leverage
                + beta * sigma2[t - 1]
            )

        sigma2 = np.maximum(sigma2, 1e-10)

        # Standardised residuals
        z = returns / np.sqrt(sigma2)

        # Hansen's skewed-t log-likelihood
        ll = np.sum(
            skewed_t_logpdf(z, nu, lam) - 0.5 * np.log(sigma2)
        )
        return -ll

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def simulate(
        self,
        n_periods: int,
        n_paths: int = 1,
        seed: int | None = None,
        initial_sigma2: float = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Simulate returns and conditional variances with GJR-GARCH
        + skewed-t innovations + jump diffusion.

        Returns
        -------
        returns : ndarray of shape (n_paths, n_periods)
        sigma2  : ndarray of shape (n_paths, n_periods)
        """
        rng = np.random.default_rng(seed)

        returns = np.zeros((n_paths, n_periods))
        sigma2 = np.zeros((n_paths, n_periods))
        init_s2 = initial_sigma2 if initial_sigma2 is not None else self.long_run_var
        # Cap initial variance to prevent explosive simulation from degenerate fits
        sigma2[:, 0] = min(init_s2, 10.0)

        # Skewed Student-t innovations — all up-front
        innovations = skewed_t_rvs(self.nu, self.lam, (n_paths, n_periods), rng)

        # Jump component
        has_jumps = self.jump_prob is not None and self.jump_prob > 0.001
        if has_jumps:
            # Bernoulli jump arrivals
            jump_mask = rng.uniform(size=(n_paths, n_periods)) < self.jump_prob
            # Jump sizes (in standardised space)
            jump_sizes = rng.normal(
                self.jump_mean / self.returns_std,
                self.jump_std / self.returns_std if self.jump_std > 0 else 1e-6,
                size=(n_paths, n_periods),
            )
            jump_component = jump_mask * jump_sizes
        else:
            jump_component = np.zeros((n_paths, n_periods))

        phi = getattr(self, 'phi', 0.0) or 0.0

        for t in range(n_periods):
            # AR(1)-GARCH return: phi * r_{t-1} + sigma_t * z_t + jump
            ar_term = phi * returns[:, t - 1] if (t > 0 and phi != 0.0) else 0.0
            returns[:, t] = ar_term + np.sqrt(sigma2[:, t]) * innovations[:, t] + jump_component[:, t]

            if t < n_periods - 1:
                # GJR-GARCH variance update: eps = return minus AR component
                eps = returns[:, t] - (phi * returns[:, t - 1] if (t > 0 and phi != 0.0) else 0.0)
                eps2 = eps ** 2
                leverage = self.gamma * eps2 * (eps < 0)
                sigma2[:, t + 1] = (
                    self.omega
                    + self.alpha * eps2
                    + leverage
                    + self.beta * sigma2[:, t]
                )
                # Floor and cap variance to prevent collapse or explosion
                sigma2[:, t + 1] = np.clip(sigma2[:, t + 1], 1e-10, 50.0)

        # Compensate drift for expected jump contribution to avoid
        # double-counting.  mu = mean(all historical returns), which already
        # includes the effect of jump bars.  When we simulate jumps
        # independently, we must subtract their expected value from the drift
        # so that E[simulated return] = mu (the historical mean).
        adjusted_mu = self.mu
        if has_jumps:
            adjusted_mu = self.mu - self.jump_prob * self.jump_mean

        # Transform back to original scale
        returns = returns * self.returns_std + adjusted_mu
        sigma2 = sigma2 * self.returns_std ** 2

        return returns, sigma2

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "model_type": "GJR-GARCH(1,1) + SkewedT + JumpDiffusion",
            "omega": self.omega,
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
            "nu": self.nu,
            "lam": self.lam,
            "jump_prob": self.jump_prob,
            "jump_mean": self.jump_mean,
            "jump_std": self.jump_std,
            "long_run_var": self.long_run_var,
            "mu": self.mu,
            "returns_std": self.returns_std,
            "phi": self.phi,
        }

    @classmethod
    def from_dict(cls, params: dict) -> GJR_GARCH:
        obj = cls()
        obj.omega = params["omega"]
        obj.alpha = params["alpha"]
        obj.beta = params["beta"]
        obj.gamma = params.get("gamma", 0.0)
        obj.nu = params["nu"]
        obj.lam = params.get("lam", 0.0)
        obj.jump_prob = params.get("jump_prob", 0.0)
        obj.jump_mean = params.get("jump_mean", 0.0)
        obj.jump_std = params.get("jump_std", 0.0)
        obj.long_run_var = params["long_run_var"]
        obj.mu = params["mu"]
        obj.returns_std = params["returns_std"]
        obj.phi = params.get("phi", 0.0)
        return obj


# ======================================================================
# Backward-compatible alias
# ======================================================================

# Keep GARCH11 as an alias so existing imports don't break
GARCH11 = GJR_GARCH
