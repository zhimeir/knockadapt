import warnings
import numpy as np
import scipy as sp
from scipy import stats

# Utility functions
from statsmodels.stats.moment_helpers import cov2corr
from .utilities import force_positive_definite, chol2inv

# Tree methods
import scipy.cluster.hierarchy as hierarchy
import scipy.spatial.distance as ssd

# Graphing
import matplotlib.pyplot as plt

def BandPrecision(p = 500, a = 0.9, rho = 5, c = 1.5):
    """ Generates band precision matrix - DOES NOT work yet
    :param p: number of features
    :param a: decay exponent base
    :param rho: cutoff after which precision matrix entries are zero
    :param c: decay constant"""
    
    vert_dists = np.repeat(np.arange(0, p, 1), p).reshape(p, p)
    dists = np.abs(vert_dists - vert_dists.transpose())
    Q = np.sign(a) * (a**(dists/c)) * (dists <= rho)
    return Q

def AR1(p = 30, a = 1, b = 1):
    """ Generates correlation matrix for AR(1) Gaussian process,
    where $Corr(X_t, X_{t-1})$ are drawn from Beta(a,b),
    independently for each t"""
        
    # Generate rhos, take log to make multiplication easier
    rhos = np.log(stats.beta.rvs(size = p, a = a, b = b))
    rhos[0] = 0 
    
    # Log correlations between x_1 and x_i for each i
    cumrhos = np.cumsum(rhos).reshape(p, 1)
    # Use cumsum tricks to calculate all correlations
    log_corrs = -1 * np.abs(cumrhos - cumrhos.transpose())
    
    return np.exp(log_corrs)

def ErdosRenyi(p = 300, delta = 0.8, 
               values = [-0.8, -0.3, -0.05, 0.05, 0.3, 0.8],
               tol = 1e-3):
    """ Randomly samples bernoulli flags as well as values
    for partial correlations to generate sparse precision
    matrices."""
    
    # Initialization
    values = np.array(values)
    Q = np.zeros((p, p))
    triang_size = int((p**2 + p)/2)
    
    # Sample the upper triangle
    mask = stats.bernoulli.rvs(delta, size = triang_size)
    vals = np.random.choice(values, size = triang_size, replace = True)
    triang = mask * vals
    
    # Set values and add diagonal
    upper_inds = np.triu_indices(p, 0)
    Q[upper_inds] = triang
    Q = np.dot(Q, Q.T)
    
    # Force to be positive definite - 
    Q = force_positive_definite(Q, tol = tol)
    
    return Q

def daibarber2016_graph(n = 3000, 
                        p = 1000, 
                        m = None, 
                        k = 20, 
                        rho = 0.5,
                        gamma = 0,
                        seed = 110):
    """ Same data-generating process as Dai and Barber 2016
    (see https://arxiv.org/abs/1602.03589).
    """
    
    np.random.seed(seed)

    # Set default values
    if m is None:
        m = int(p/5)

    # Set k
    if k is None and p == 1000:
        k = 20
    else:
        k = int(m/2)

    # Create groups
    groups = np.array([int(i / (p / m)) for i in range(p)])

    # Helper fn for covariance matrix
    # Add a tinnnyyyy bit of noise to make sure that the
    # cutoff method works properly
    def get_corr(g1, g2):
        if g1 == g2:
            return rho
        else:
            return gamma * rho 
    get_corr = np.vectorize(get_corr)
    
    # Create correlation matrix, invert
    Xcoords, Ycoords = np.meshgrid(groups, groups)
    Sigma = get_corr(Xcoords, Ycoords)
    Sigma += np.eye(p) - np.diagflat(np.diag(Sigma))
    Q = chol2inv(Sigma)

    # Create beta
    chosen_groups = np.random.choice(np.unique(groups), 
                                     k,
                                     replace = False)
    beta = np.array(
        [3.5 if i in chosen_groups else 0 for i in groups]
    )
    signs = (1 - 2*stats.bernoulli.rvs(0.5, size = p))
    beta = beta * signs
    
    # Sample design matrix
    mu = np.zeros(p)
    X = stats.multivariate_normal.rvs(mean = mu, 
                                      cov = Sigma,
                                      size = n)
    # Sample y
    y = np.dot(X, beta) + stats.norm.rvs(size = n)
    
    return X, y, beta, Q, Sigma, groups + 1


def create_correlation_tree(corr_matrix, method = 'single'):
    """ Creates hierarchical clustering (correlation tree)
    from a correlation matrix
    :param corr_matrix: the correlation matrix
    :param method: 'single', 'average', 'fro', or 'complete'
    
    returns: 'link' of the correlation tree, as in scipy"""
    
    p = corr_matrix.shape[0]
    
    # Distance matrix for tree method
    if method == 'fro':
        dist_matrix = np.around(1-np.power(corr_matrix, 2), decimals = 7)
    else:
        dist_matrix = np.around(1-np.abs(corr_matrix), decimals = 7)
    dist_matrix -= np.diagflat(np.diag(dist_matrix))

    condensed_dist_matrix = ssd.squareform(dist_matrix)

    # Create linkage
    if method == 'single':
        link = hierarchy.single(condensed_dist_matrix)
    elif method == 'average' or method == 'fro':
        link = hierarchy.average(condensed_dist_matrix)
    elif method == 'complete':
        link = hierarchy.complete(condensed_dist_matrix)
    else:
        raise ValueError(f'Only "single", "complete", "average", "fro" are valid methods, not {method}')
        
        
    return link

def sample_data(p = 100, n = 50, coeff_size = 1, 
                sparsity = 0.5, method = 'ErdosRenyi',
                Q = None, corr_matrix = None, beta = None,
               **kwargs):
    """ Creates a random covariance matrix using method
    and then samples Gaussian data from it. It also creates
    a linear response y with sparse coefficients.
    :param p: Dimensionality
    :param n: Sample size
    :param coeff_size: The standard deviation of the
    sparse linear coefficients. (The noise of the 
    response itself is standard normal).
    :param method: How to generate the covariance matrix.
    One of 'ErdosRenyi', 'AR1', 'identity', 'daibarber2016'
    :param Q: p x p precision matrix. If supplied, will not generate
    a new covariance matrix.
    :param corr_matrix: p x p correlation matrix. If supplied, will 
    not generate a new correlation matrix.
    :param kwargs: kwargs to the graph generator (e.g. AR1 kwargs).
    If there's a seed in this, will set the seed to generate cov matrix
    but will NOT use the seed to generate the random data. (To do that, 
    set the seed outside the function call).
    """
    
    # Create Graph
    if Q is None and corr_matrix is None:

        method = str(method).lower()
        if method == 'erdosrenyi':
            Q = ErdosRenyi(p = p, **kwargs)
            corr_matrix = cov2corr(chol2inv(Q))
            corr_matrix -= np.diagflat(np.diag(corr_matrix))
            corr_matrix += np.eye(p)
            Q = chol2inv(corr_matrix)
        elif method == 'ar1':
            corr_matrix = AR1(p = p, **kwargs)
            Q = chol2inv(corr_matrix)
        elif method == 'identity':
            corr_matrix = 1e-3 * stats.norm.rvs(size = (p,p))
            corr_matrix = np.dot(corr_matrix.T, corr_matrix)
            corr_matrix -= np.diagflat(np.diag(corr_matrix))
            corr_matrix += np.eye(p)
            Q = corr_matrix
        elif method == 'daibarber2016':
            _, _, beta, Q, corr_matrix, _ = daibarber2016_graph(
                p = p, n = n, **kwargs
            )
        else:
            raise ValueError("Other methods not implemented yet")

    elif Q is None:
        Q = chol2inv(corr_matrix)
    elif corr_matrix is None:
        corr_matrix = cov2corr(chol2inv(Q))
    else:
        pass

    # Sample design matrix
    mu = np.zeros(p)
    X = stats.multivariate_normal.rvs(mean = mu, cov = corr_matrix, size = n)

    # Create sparse coefficients and y
    if beta is None:
        num_nonzero = int(np.floor(sparsity * p))
        mask = np.array([1]*num_nonzero + [0]*(p-num_nonzero))
        np.random.shuffle(mask)
        signs = 1 - 2*stats.bernoulli.rvs(0.5, size = p)
        beta = coeff_size * mask * signs
    y = np.einsum('np,p->n', X, beta) + np.random.standard_normal((n))
    
    return X, y, beta, Q, corr_matrix

def plot_dendrogram(link, title = None):

    # Get title
    if title is None:
        title = 'Hierarchical Clustering Dendrogram'

    # Plot
    plt.figure(figsize=(15, 10))
    plt.title(str(title))
    plt.xlabel('Index')
    plt.ylabel('Correlation Distance')
    hierarchy.dendrogram(
        link,
        leaf_rotation=90.,  # rotates the x axis labels
        leaf_font_size=8.,  # font size for the x axis labels
    )
    plt.show()
