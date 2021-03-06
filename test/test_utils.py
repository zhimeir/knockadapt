import numpy as np
import unittest
from .context import knockadapt

from knockadapt import graphs, utilities

class TestUtils(unittest.TestCase):
	""" Tests some various utility functions """


	def test_group_manipulations(self):
		""" Tests calc_group_sizes and preprocess_groups """ 

		# Calc group sizes 
		groups = np.concatenate([np.ones(2),
								 np.ones(3) + 1,
								 np.ones(2) + 3])
		group_sizes = utilities.calc_group_sizes(groups)
		expected = np.array([2, 3, 0, 2])
		np.testing.assert_array_almost_equal(
			group_sizes, expected, decimal = 6,
			err_msg = "Incorrectly calculates group sizes"
		)

		# Make sure this raises the correct error for groups
		# which include zero
		groups = np.arange(0, 10, 1)
		self.assertRaisesRegex(
			ValueError, "groups cannot contain 0",
			utilities.calc_group_sizes, groups,
		)

		# Make sure this raises the correct error for groups
		# which include zero
		groups = [1.5, 1.5, 1.8, 20.4]
		self.assertRaisesRegex(
			TypeError, "groups cannot contain non-integer values",
			utilities.calc_group_sizes, groups,
		)

		# Preprocess
		groups = np.array([0.3, 0.24, 0.355, 0.423, 0.423, 0.3])
		processed_groups = utilities.preprocess_groups(groups)
		expected = np.array([2, 1, 3, 4, 4, 2])
		np.testing.assert_array_almost_equal(
			processed_groups, expected, decimal = 6,
			err_msg = "Incorrectly preprocesses groups"
		)

		# Test function which calculates selections
		non_nulls = [-1, 0, -1, 1, 0, 0, 0]
		groups = [1, 1, 2, 2, 3, 3, 3]
		out = utilities.fetch_group_nonnulls(non_nulls, groups)
		expected = np.array([1.0, 1.0, 0.0])
		np.testing.assert_array_almost_equal(
			out, expected, decimal = 6,
			err_msg = "Incorrectly calculates group selections"
		)

	def test_random_permutation(self):
		""" Tests random permutation and seed manipulations """
		
		# Check random state (sort of hacky, I'm unclear on the best way
		# to check that two random states are equal)
		np.random.seed(110)
		x = np.random.randn()

		# Reset seed 
		np.random.seed(110)

		# Calculate random permutation, see if it's the same
		test_list = np.array([0, 5, 3, 6, 32, 2, 1])
		inds, rev_inds = utilities.random_permutation_inds(len(test_list))
		reconstructed = test_list[inds][rev_inds]
		np.testing.assert_array_almost_equal(
			test_list, reconstructed, decimal = 6,
			err_msg = 'Random permutation is not reversible'
		)

		# Check that random state is still the same
		y = np.random.randn()
		np.testing.assert_almost_equal(x, y, decimal = 6, 
			err_msg = 'Random permutation incorrectly resets random seed'
		)

	def test_force_pos_def(self):

		# Random symmetric matrix, will have highly neg eigs
		np.random.seed(110)
		X = np.random.randn(100, 100)
		X = (X.T + X)/2

		# Force pos definite
		tol = 1e-3
		posX = utilities.shift_until_PSD(X, tol=tol)
		mineig = np.linalg.eigh(posX)[0].min()

		# Make sure the difference between the tolerance and is small
		self.assertTrue(
			mineig >= tol - 1e-5, # Acct for num. errors in eigval calc
			msg = 'Minimum eigenvalue is not greater than or equal to tolerance'
		)

	def test_chol2inv(self):

		# Random pos def matrix
		X = np.random.randn(100, 100)
		X = np.dot(X.T, X)

		# Check cholesky decomposition
		inverse = utilities.chol2inv(X)
		np.testing.assert_array_almost_equal(
			np.eye(100), np.dot(X, inverse), decimal = 6,
			err_msg = 'chol2inv fails to correctly calculate inverses'
		)

	def test_misaligned_covariance_estimation(self):

		# Inputs
		seed = 110
		sample_kwargs = {
			'n':640,
			'p':300,
			'method':'daibarber2016',
			'gamma':1,
			'rho':0.8,
		}

		# Extracta couple of constants
		n = sample_kwargs['n']
		p = sample_kwargs['p']

		# Create data generating process
		np.random.seed(seed)
		X, y, beta, _, V = graphs.sample_data(**sample_kwargs)  

		# Make sure this does not raise an error
		# (even though it is ill-conditioned and the graph lasso doesn't fail)
		utilities.estimate_covariance(X, shrinkage='graphicallasso')

	def test_covariance_estimation(self):

		# Random data
		np.random.seed(110)
		n = 50
		p = 100
		rho = 0.3
		V = (1-rho)*np.eye(p) + (rho)*np.ones((p,p))
		X,_,_,_,_ = graphs.sample_data(n=n, corr_matrix=V)

		# Estimate covariance matrix
		Vest,_ = utilities.estimate_covariance(X, tol=1e-2)
		frobenius = np.sqrt(np.power(Vest - V, 2).mean())
		self.assertTrue(
			frobenius < 0.2,
			f"High-dimension covariance estimation is horrible"
		)





if __name__ == '__main__':
	unittest.main()