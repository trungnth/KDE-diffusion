﻿"""
Kernel density estimation via diffusion for 2-dimensional input data.
"""
__license__ = 'MIT'


########################################
# Dependencies                         #
########################################
from numpy import array, arange
from numpy import exp, sqrt, pi as π
from numpy import ceil, log2
from numpy import ones
from numpy import product, outer
from numpy import histogram2d
from scipy.fft import dctn, idctn
from scipy.optimize import brentq


########################################
# Main                                 #
########################################

def kde2d(x, y, n=256, limits=None):
    """
    Estimates the 2d density from discrete observations (x, y).

    The input is two lists/arrays `x` and `y` of numbers that represent
    discrete observations of a random variable with two coordinate
    components. The observations are binned on a grid of n×n points,
    where `n` must be a power of 2 or will be coerced to the next one.

    Data `limits` may be specified as a tuple of tuples denoting
    `((xmin, xmax), (ymin, ymax))`. If any of the values are `None`,
    they will be inferred from the data. Each tuple, or even both of
    them, may also be replaced by a single value denoting the upper
    bound of a range centered at zero.

    After binning, the function determines the optimal bandwidth
    according to the diffusion-based method. It then smooths the
    binned data over the grid using a Gaussian kernel with a standard
    deviation corresponding to that bandwidth.

    Returns the estimated `density` and the `grid` (along each of the
    two axes) upon which it was computed, as well as the optimal
    `bandwidth` values (per axis) that the algorithm determined.
    Raises `ValueError` if the algorithm did not converge or `x` and
    `y` are not the same length.
    """

    # Convert to arrays in case a lists are passed in.
    x = array(x)
    y = array(y)

    # Make sure the number of data points is consistent.
    N = len(x)
    if len(y) != N:
        raise ValueError('x and y must have the same length.')

    # Round up the number of bins to the next power of 2.
    n = int(2**ceil(log2(n)))

    # Determine missing data limits.
    if limits is None:
        xmin = xmax = ymin = ymax = None
    elif isinstance(limits, tuple):
        (xlimits, ylimits) = limits
        if xlimits is None:
            xmin = xmax = None
        elif isinstance(xlimits, tuple):
            (xmin, xmax) = xlimits
        else:
            xmin = -xlimits
            xmax = +xlimits
        if ylimits is None:
            ymin = ymax = None
        elif isinstance(ylimits, tuple):
            (ymin, ymax) = ylimits
        else:
            ymin = -ylimits
            ymax = +ylimits
    else:
        xmin = -limits
        xmax = +limits
        ymin = -limits
        ymax = +limits
    if None in (xmin, xmax):
        delta = x.max() - x.min()
        if xmin is None:
            xmin = x.min() - delta/4
        if xmax is None:
            xmax = x.max() + delta/4
    if None in (ymin, ymax):
        delta = y.max() - y.min()
        if ymin is None:
            ymin = y.min() - delta/4
        if ymax is None:
            ymax = y.max() + delta/4
    Δx = xmax - xmin
    Δy = ymax - ymin

    # Bin the samples on a regular grid.
    (binned, xedges, yedges) = histogram2d(x, y, bins=n,
                                           range=((xmin, xmax), (ymin, ymax)))
    grid = (xedges[:-1], yedges[:-1])

    # Compute the 2d discrete cosine transform.
    transformed = dctn(binned/N)
    transformed[0, :] /= 2
    transformed[:, 0] /= 2

    # Pre-compute squared indices and transform before solver loop.
    k  = arange(n, dtype='float')          # "float" avoids integer overflow.
    k2 = k**2
    a2 = transformed**2

    # Define internal functions to be solved iteratively.

    def γ(t):
        Σ = ψ(0, 2, t) + ψ(2, 0, t) + 2*ψ(1, 1, t)
        γ = (2*π*N*Σ)**(-1/3)
        return (t - γ) / γ

    def ψ(i, j, t):
        if i + j <= 4:
            Σψ = ψ(i+1, j, t) + ψ(i, j+1, t)
            C  = (1 + 1/2**(i+j+1)) / 3
            Πi = product(arange(1, 2*i, 2))
            Πj = product(arange(1, 2*j, 2))
            t  = (C*Πi*Πj / (π*N*abs(Σψ))) ** (1/(2+i+j))
        w = 0.5 * ones(n)
        w[0] = 1
        w = w * exp(-π**2 * k2*t)
        wx = w * k2**i
        wy = w * k2**j
        return (-1)**(i+j) * π**(2*(i+j)) * wy @ a2 @ wx

    # Solve for optimal diffusion time t*.
    try:
        ts = brentq(lambda t: t - γ(t), 0, 0.1)
    except ValueError:
        raise ValueError('Bandwidth optimization did not converge.') from None

    # Calculate diffusion times along x- and y-axis.
    ψ02 = ψ(0, 2, ts)
    ψ20 = ψ(2, 0, ts)
    ψ11 = ψ(1, 1, ts)
    tx1 = (ψ02**(3/4) / (4*π*N*ψ20**(3/4) * (ψ11 + sqrt(ψ02*ψ20))) )**(1/3)
    tx2 = (ψ20**(3/4) / (4*π*N*ψ02**(3/4) * (ψ11 + sqrt(ψ02*ψ20))) )**(1/3)

    # Note: This uses the nomenclature from the paper. In the Matlab
    # implementation tx1 is called t_y, while tx2 is t_x. It is strange
    # that they are reversed. This may be related to the fact that
    # image coordinates are typically in (y, x) index order, whereas
    # matrices, such as the binned histogram, are in (x,y) index order.
    # The Matlab code returns image-like index order. However, it never
    # explicitly transposes the density matrix, even though it does
    # start with a histogram, i.e. in matrix index order. It seems that
    # this is implicitly done by the back transformation (idct2d),
    # which in the Matlab code contains only one transposition, not two
    # as in the implementation here. The latter is done in order to
    # return the density in matrix index order, just like a histogram,
    # which is the convention used by other kernel density estimators,
    # such as SciPy's. It is possible that the reference implementation
    # got this detail wrong. In most use cases, this would go unnoticed
    # as the bandwidth value is often just discarded. Mistake or not,
    # the code here returns the same bandwidth and density, except for
    # the aforementioned transposition.

    # Apply the optimized Gaussian kernel.
    smoothed = transformed * outer(exp(-π**2 * k2 * tx2/2),
                                   exp(-π**2 * k2 * tx1/2))

    # Reverse the transformation.
    smoothed[0, :] *= 2
    smoothed[:, 0] *= 2
    inverse = idctn(smoothed)

    # Normalize the density.
    density = inverse * n/Δx * n/Δy

    # Determine bandwidth from diffusion times.
    bandwidth = array([sqrt(tx2)*Δx, sqrt(tx1)*Δy])

    # Return results.
    return (density, grid, bandwidth)
