import warnings
import numpy as np
from sklearn import linear_model
from group_lasso import GroupLasso, LogisticGroupLasso
from pyglmnet import GLM, GLMCV
from statsmodels.stats.moment_helpers import cov2corr

from .utilities import random_permutation_inds

DEFAULT_REG_VALS = np.logspace(-4, 1.5, base = 10, num = 10)


def calc_mse(model, X, y):
    """ Gets MSE of a model """ 
    preds = model.predict(X)
    resids = (preds - y)/y.std()
    return np.sum((resids)**2)

def use_reg_lasso(groups):
    """ Parses whether or not to use group lasso """
    # See if we are using regular lasso...
    if groups is not None:
        p = groups.shape[0]
        m = np.unique(groups).shape[0]
        if p == m:
            return True
        else:
            return False
    else:
        return True

def parse_y_dist(kwargs):
    """ Checks whether y_dist is binomial """
    if 'y_dist' in kwargs:
        if kwargs['y_dist'] == 'binomial':
            return True
    return False


def calc_LCD(Z, groups):
    """
    Calculates coefficient differences for knockoffs
    :param Z: statistics for each feature (including knockoffs)
    2p dimensional numpy array
    :param groups: p dimensional numpy array of group membership
    with m discrete values. 
    :returns W: m dimensional array of knockoff LCD statistics
    """

    # If None, all are in their own group
    p = int(Z.shape[0]/2)
    if 2*p != Z.shape[0]:
        raise ValueError("Z statistics must have length 2p, but {Z.shape[0]} is odd")
    if groups is None:
        groups = np.arange(1, p+1, 1)

    # Get dims, initialize output
    m = np.unique(groups).shape[0]
    W = np.zeros(m)

    # Separate
    Z_true = Z[0:p]
    Z_knockoff = Z[p:]

    # Create Wjs
    for j in range(m):
        true_coeffs = Z_true[groups == j + 1]
        knock_coeffs = Z_knockoff[groups == j + 1]
        Wj = np.sum(np.abs(true_coeffs)) - np.sum(np.abs(knock_coeffs))
        W[j] = Wj

    return W

def calc_LSM(Z, groups):
    """
    Calculates signed maximum statistics for knockoffs
    :param Z: statistics for each feature (including knockoffs)
    2p dimensional numpy array
    :param groups: p dimensional numpy array of group membership
    with m discrete values
    :returns W: m dimensional array of knockoff LSM statistics
    """

    # Get dims, initialize output
    p = groups.shape[0]
    m = np.unique(groups).shape[0]

    # Calculate signed maxes
    inds = np.arange(0, p, 1)
    W = np.maximum(Z[inds], Z[inds + p])
    W = W * np.sign(np.abs(Z[inds]) - np.abs(Z[inds + p]))

    # Combine them for each group
    W_group = np.zeros(m)
    for i in range(p):
        W_group[groups[i]-1] += W[i]
        
    return W_group


def calc_lambda_paths(X, knockoffs, y, groups = None, **kwargs):
    """ Calculates locations at which X/knockoffs enter lasso 
    model when regressed on y.
    :param X: n x p design matrix
    :param knockoffs: n x p knockoff matrix
    :param groups: p length numpy array of groups
    :param kwargs: kwargs for sklearn Lasso class 
     """

    # Bind data
    n = X.shape[0]
    p = X.shape[1]
    features = np.concatenate([X, knockoffs], axis = 1)

    # By default, all variables are their own group
    if groups is None:
        groups = np.arange(0, p, 1)
    m = np.unique(groups).shape[0]
    
    # Fit
    alphas, _, coefs = linear_model.lars_path(
        features, y, method='lasso', **kwargs,
    )
    
    # Calculate places where features enter the model
    Z = np.zeros(2*p)
    for i in range(2*p):
        if (coefs[i] != 0).sum() == 0:
            Z[i] = 0
        else:
            Z[i] = alphas[np.where(coefs[i] != 0)[0][0]]

    return Z


def calc_nongroup_LSM(X, knockoffs, y, groups = None, **kwargs):
    """ Calculates difference between average group Lasso signed maxs. 
    Does NOT use a group lasso regression class, unfortunately.
    :param X: n x p design matrix
    :param knockoffs: n x p knockoff matrix
    :param groups: p length numpy array of groups
    :param kwargs: kwargs for sklearn Lasso class
    """
        
    # Z statistics
    Z = calc_lambda_paths(X, knockoffs, y, groups, **kwargs)

    # Calculate group LSM
    W_group = calc_LSM(Z, groups)
        
    return W_group



def calc_nongroup_LCD(X, knockoffs, y, groups = None, **kwargs):
    """ Calculates difference in absolute coefficient sums over groups. 
    Uses the place where X/knockoffs enter the path, not the coefficients.
    This and the prev function should be renamed.
    :param X: n x p design matrix
    :param knockoffs: n x p knockoff matrix
    :param groups: p length numpy array of groups
    :param kwargs: kwargs for sklearn Lasso class
    """
        
    # Z statistics
    Z = calc_lambda_paths(X, knockoffs, y, groups, **kwargs)

    # Calculate group LSM
    W_group = calc_LCD(Z, groups)
        
    return W_group


def fit_lasso(X, knockoffs, y, y_dist = 'gaussian', **kwargs):

    # Bind data
    n = X.shape[0]
    p = X.shape[1]
    features = np.concatenate([X, knockoffs], axis = 1)


    # Randomize coordinates to make sure everything is symmetric
    inds, rev_inds = random_permutation_inds(2*p)
    features = features[:, inds]

    # Fit lasso
    warnings.filterwarnings("ignore")
    if y_dist == 'gaussian':
        gl = linear_model.LassoCV(
            alphas = DEFAULT_REG_VALS,
            normalize = True,
            cv = 2, verbose = False,
            max_iter = 50, tol = 1e-3
        ).fit(features, y)
    elif y_dist == 'binomial':
        gl = linear_model.LogisticRegressionCV(
            Cs = 1/DEFAULT_REG_VALS,
            penalty = 'l1', max_iter = 50,
            cv = 2, verbose = False,
            solver = 'liblinear', tol = 1e-3
        ).fit(features, y)
    else:
        raise ValueError(f"y_dist must be one of gaussian, binomial, not {y_dist}")
    warnings.resetwarnings()

    return gl, rev_inds


def fit_group_lasso(X, knockoffs, y, groups, 
                    use_pyglm = True, 
                    y_dist = 'gaussian',
                    **kwargs):
    """ Fits a group lasso model.
    :param X: n x p design matrix
    :param knockoffs: n x p knockoff matrix
    :param groups: p length numpy array of groups
    :param use_pyglm: If true, use the pyglmnet grouplasso
    Else use the regular one
    :param kwargs: kwargs for group-lasso GroupLasso class.
    In particular includes reg_vals, a list of regularizations
    (lambda values) which defaults to [(0.05, 0.05)]. In each
    tuple of the list, the first value is the group regularization,
    the second value is the individual regularization.
    """

    warnings.filterwarnings("ignore")

    # Bind data
    n = X.shape[0]
    p = X.shape[1]
    features = np.concatenate([X, knockoffs], axis = 1)

    # By default, all variables are their own group
    if groups is None:
        groups = np.arange(1, p+1, 1)
        m = p
    else:
        m = np.unique(groups).shape[0]

    # If m == p, meaning each variable is their own group,
    # just fit a regular lasso
    if m == p: 
        return fit_lasso(X, knockoffs, y, y_dist, **kwargs)

    # Make sure variables and their knockoffs are in the same group
    # This is necessary for antisymmetry
    doubled_groups = np.concatenate([groups, groups], axis = 0)

    # Randomize coordinates to make sure everything is symmetric
    inds, rev_inds = random_permutation_inds(2*p)
    features = features[:, inds]
    doubled_groups = doubled_groups[inds]

    # Standardize - important for pyglmnet performance, 
    # highly detrimental for group_lasso performance
    if use_pyglm:
        features = (features - features.mean())/features.std()
        if y_dist == 'gaussian':
            y = (y - y.mean())/y.std()

    # Get regularizations
    if 'reg_vals' in kwargs:
        reg_vals = kwargs['reg_vals']
        kwargs.pop('reg_vals')
    else:
        reg_vals = [(x,x) for x in DEFAULT_REG_VALS]

    # Fit pyglm model using warm starts
    if use_pyglm:

        l1_regs = [x[0] for x in reg_vals]

        gl = GLMCV(distr=y_dist,
                 tol=5e-2, group=doubled_groups, alpha=1.0,
                 learning_rate=3, max_iter=20,
                 reg_lambda = l1_regs,
                 cv = 2,
                 solver = 'cdfast')
        gl.fit(features, y)

        # Pull score, rename
        best_score = -1*calc_mse(gl, features, y)
        best_gl = gl

    # Fit model
    if not use_pyglm:
        best_gl = None
        best_score = -1*np.inf
        for group_reg, l1_reg in reg_vals:

            # Fit logistic/gaussian group lasso 
            if not use_pyglm:
                if y_dist.lower() == 'gaussian':
                    gl = GroupLasso(
                        groups=doubled_groups, tol = 5e-2, 
                        group_reg = group_reg, l1_reg = l1_reg, **kwargs
                    )
                elif y_dist.lower() == 'binomial':
                    gl = LogisticGroupLasso(
                        groups=doubled_groups, tol = 5e-2, 
                        group_reg = group_reg, l1_reg = l1_reg, **kwargs
                    )
                else:
                    raise ValueError(f"y_dist must be one of gaussian, binomial, not {y_dist}")

                gl.fit(features, y.reshape(n, 1))
                score = -1*calc_mse(gl, features, y.reshape(n, 1))


            # Score, possibly select
            if score > best_score:
                best_score = score
                best_gl = gl

    warnings.resetwarnings()

    return best_gl, rev_inds


def group_lasso_LSM(X, knockoffs, y, groups, use_pyglm = True, 
                    **kwargs):
    """ Calculates mean group Lasso signed max. 
    :param X: n x p design matrix
    :param knockoffs: n x p knockoff matrix
    :param groups: p length numpy array of groups
    :param kwargs: kwargs for fit_group_lasso function 
    """
    gl, rev_inds = fit_group_lasso(X, knockoffs, y, groups = groups,
                                   use_pyglm = use_pyglm, **kwargs)

    # See if we are using regular lasso...
    reg_lasso_flag = use_reg_lasso(groups)
    logistic_flag = parse_y_dist(kwargs)

    # Create LSM statistics
    if use_pyglm and not reg_lasso_flag:
        Z = gl.beta_[rev_inds]
    elif reg_lasso_flag and logistic_flag:
        if gl.coef_.shape[0] != 1:
            raise ValueError("Unexpected shape for logistic lasso coefficients (sklearn)")
        Z = gl.coef_[0, rev_inds]
    else:
        Z = gl.coef_[rev_inds]
    W = calc_LSM(Z, groups)
    return W


def group_lasso_LCD(X, knockoffs, y, groups = None,
                    use_pyglm = True, **kwargs):
    """ Calculates group Lasso coefficient difference. 
    I.e. if features 2 and 3 are in the same group, 
    we set W(X, knockoffs, y) = 
    sum(abs coeff of features 2,3) - sum(abs coeff of knockoff features 2,3)
    :param X: n x p design matrix
    :param knockoffs: n x p knockoff matrix
    :param groups: p length numpy array of function
    :params **kwargs: kwargs to fit_group_lasso method 

    """
    gl, rev_inds = fit_group_lasso(X, knockoffs, y, groups = groups, 
                                   use_pyglm = use_pyglm, **kwargs)

    # See if we are using regular lasso...
    reg_lasso_flag = use_reg_lasso(groups)
    logistic_flag = parse_y_dist(kwargs)

    # Create LCD statistics
    if use_pyglm and not reg_lasso_flag:
        Z = gl.beta_[rev_inds]
    elif reg_lasso_flag and logistic_flag:
        if gl.coef_.shape[0] != 1:
            raise ValueError("Unexpected shape for logistic lasso coefficients (sklearn)")
        Z = gl.coef_[0, rev_inds]
    else:
        Z = gl.coef_[rev_inds]

    # Calc LCD
    W = calc_LCD(Z, groups)
    return W

def calc_data_dependent_threshhold(W, fdr=0.10, offset=1):
    """
    This is not efficient but it's definitely not a bottleneck.
    Follows https://github.com/msesia/knockoff-filter/blob/master/R/knockoff/R/knockoff_filter.R
    :param W: p-length numpy array of feature statistics
    :param fdr: desired FDR level (referred to as q in the literature)
    :param offset: if offset = 0, use knockoffs (which control modified FDR).
    Else, if offset = 1, use knockoff+ (controls exact FDR).
    """

    # Possible values for Ts
    Ts = sorted(np.abs(W))
    Ts = np.concatenate([np.array((0,)), Ts], axis = 0)
    
    # Calculate ratios
    def hat_fdp(t):
        return ((W <= -t).sum() + offset)/max(1, np.sum(W >= t))
    hat_fdp = np.vectorize(hat_fdp)
    ratios = hat_fdp(Ts)

    # Find maximum
    acceptable = Ts[ratios <= fdr]
    if acceptable.shape[0] == 0:
        return np.inf
    
    return acceptable[0]
    