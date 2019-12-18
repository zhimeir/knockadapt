import copy
import numpy as np
import unittest
from .context import knockadapt

from knockadapt import utilities, graphs, adaptive
from knockadapt.adaptive import GroupKnockoffEval

class TestGroupKnockoffEval(unittest.TestCase):
	""" Tests GroupKnockoffEval class """


	@classmethod
	def setUpClass(cls):

		# Create dgp
		cls.n = 200
		cls.p = 30
		cls.q = 0.4
		np.random.seed(110)
		cls.X, cls.y, cls.beta, _, cls.corr_matrix, cls.groups = graphs.daibarber2016_graph(
			n = cls.n, p = cls.p, y_dist = 'binomial', k = 3
		)
		cls.link = graphs.create_correlation_tree(
            cls.corr_matrix, method = 'average'
        )

		# Create class
		cls.gkval = GroupKnockoffEval(cls.corr_matrix, cls.q, cls.beta, verbose = False,
									  feature_stat_kwargs = {'use_pyglm':False})

		# Repeat, but with gamma = 1 and a larger p
		cls.n2 = 1000
		cls.p2 = 100
		cls.q2 = 0.2
		np.random.seed(110)
		cls.X2, cls.y2, cls.beta2, _, cls.corr_matrix2, _ = graphs.daibarber2016_graph(
			n = cls.n2, p = cls.p2, gamma = 0.01, y_dist = 'binomial'
		)
		cls.groups2 = np.arange(0, cls.p2, 1) + 1
		cls.link2 = graphs.create_correlation_tree(
            cls.corr_matrix2, method = 'average'
        )

		# Create class
		cls.gkval2 = GroupKnockoffEval(cls.corr_matrix2, cls.q2, cls.beta2, 
									   feature_stat_kwargs = {'use_pyglm':True},
									   verbose = True,
									   method = 'ASDP')





	def test_combine_S_kwargs(self):

		old_kwargs = copy.copy(self.gkval.knockoff_kwargs)

		# Test proper kwarg handling
		to_add = {'S':1, 'verbose':True}
		new_kwargs = self.gkval.combine_S_kwargs(to_add)
		self.assertEqual(
			new_kwargs, {'S':1, 'verbose':True, 'sdp_verbose':False},
			msg = 'GroupKnockoffEval does not properly handle new kwargs'
		)

		# Test to make sure default kwargs not changed
		self.assertEqual(
			self.gkval.knockoff_kwargs, old_kwargs,
			msg = 'Adding new kwargs permanently overwrites old ones for GroupKnockoffEval'
		)


	def test_sample_recycling(self):
		""" Tests recycled knockoff samples   """

		n0 = 100
		knockoffs1 = self.gkval.sample_knockoffs(
			self.X, self.groups, recycle_up_to = n0, copies = 1
		)[:, :, 0]

		knockoffs2 = self.gkval.sample_knockoffs(
			self.X, self.groups, recycle_up_to = None, copies = 1
		)[:, :, 0]

		# Ensure recycling happened properly
		testval = np.sum(((knockoffs1 - self.X)[0:n0, :])**2)
		self.assertEqual(
			testval, 0,
			msg = 'Recycled knockoffs are NOT equal to design matrix'
		)

		# And that we aren't recycling by accident
		testval2 = np.min(((knockoffs2 - self.X)[0:n0, :])**2)
		self.assertFalse(
			testval2 == 0,
			msg = 'Non-recycled knockoffs are somehow equal to design matrix'
		)

	def test_eval_knockoff_instance(self):

		# These are fake knockoffs but whatever
		knockoffs = np.random.randn(self.n, self.p)
		fdp, power, epower = self.gkval.eval_knockoff_instance(
			self.X, knockoffs, self.y, self.groups, 
		)


	def test_eval_grouping(self):

		fdp, power, epower = self.gkval.eval_grouping(
			self.X, self.y, self.groups, copies = 2
		)


		#print('============================================')
		# # # Compare knockoffs?

		# knockoffs1 = self.gkval2.sample_knockoffs(
		# 	self.X2, self.groups2, recycle_up_to = 150, copies = 1
		# )[:, :, 0]

		# print(knockoffs1[:, 3].mean(), 'rec')
		# print(knockoffs1[:, 3].std(), 'rec')

		# knockoffs2 = self.gkval2.sample_knockoffs(
		# 	self.X2, self.groups2, recycle_up_to = None, copies = 1
		# )[:, :]
		# print(knockoffs2[:, 3].mean(), 'Non-recycled')
		# print(knockoffs2[:, 3].std(), 'Non-recycled')
		# # print(knockoffs1 - knockoffs2)

		# # Now test in harder case
		# print('================== NO RECYCLING ==========================')
		# print(self.corr_matrix2)
		# fdp, power, epower = self.gkval2.eval_grouping(
		# 	X = self.X2, y = self.y2, groups = self.groups2, copies = 1
		# )
		# print(fdp, power, epower)

		# # Now recycle too
		# print('===================== RECYCLING =======================')
		# fdp, power, epower = self.gkval2.eval_grouping(
		# 	X = self.X2, y = self.y2, groups = self.groups2, copies = 1,
		# 	recycle_up_to = int(self.n2/2)
		# )
		# print(fdp, power, epower)

		# print('===================END=========================')



	def test_eval_many_cutoffs(self):

		# Try in easy case
		cutoffs, fdps, powers, epowers = self.gkval.eval_many_cutoffs(
			X = self.X, y = self.y, link = self.link, reduction = 5,
			copies = 1
		)

		np.testing.assert_array_almost_equal(
			cutoffs, np.array([0.0, 0.5, 1.0]), decimal = 6,
			err_msg = "gkval incorrectly calculates cutoffs"
		)

		for power, epower in zip(powers, epowers):
			self.assertTrue(
				epower >= power,
				msg = 'Empirical power is somehow smaller than actual power'
			)




if __name__ == '__main__':
	unittest.main()