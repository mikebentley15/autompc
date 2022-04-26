# Created by William Edwards (wre2@illinois.edu), 2021-01-24

# Standard library includes
import unittest

# Internal library includes
import autompc as ampc
from autompc.sysid import ARX
from autompc.costs import QuadCost, SumCost
from autompc.ocp import OCP, QuadCostFactory, GaussRegFactory
from autompc.optim import IterativeLQR

# External library includes
import numpy as np
import ConfigSpace as CS

def doubleint_dynamics(y, u):
    """
    Parameters
    ----------
        y : states
        u : control

    Returns
    -------
        A list describing the dynamics of the cart cart pole
    """
    x, dx = y
    return np.array([dx, u])

def dt_doubleint_dynamics(y,u,dt):
    y += dt * doubleint_dynamics(y,u[0])
    return y

def uniform_random_generate(system, task, dynamics, rng, init_min, init_max, 
        traj_len, n_trajs):
    trajs = []
    for _ in range(n_trajs):
        state0 = [rng.uniform(minval, maxval, 1)[0] for minval, maxval 
                in zip(init_min, init_max)]
        y = state0[:]
        traj = ampc.zeros(system, traj_len)
        traj.obs[:] = y
        umin, umax = task.get_ctrl_bounds().T
        for i in range(traj_len):
            traj[i].obs[:] = y
            u = rng.uniform(umin, umax, 1)
            y = dynamics(y, u)
            traj[i].ctrl[:] = u
        trajs.append(traj)
    return trajs

class QuadCostFactoryTest(unittest.TestCase):
    def setUp(self):
        simple_sys = ampc.System(["x", "y"], ["u"])
        self.system = simple_sys
        self.model = ARX(self.system)

        # Initialize OCP
        Q = np.eye(2)
        R = np.eye(1)
        F = np.eye(2)
        cost = QuadCost(self.system, Q, R, F, goal=[-1,0])
        self.ocp = OCP(self.system)
        self.ocp.set_cost(cost)
        self.ocp.set_ctrl_bound("u", -20.0, 20.0)

    def test_config_space(self):
        factory = QuadCostFactory(self.system)
        cs = factory.get_config_space()
        self.assertIsInstance(cs, CS.ConfigurationSpace)

        hyper_names = cs.get_hyperparameter_names()
        target_hyper_names = ["x_Q", "y_Q", "x_F", "y_F", "u_R"]
        self.assertEqual(set(hyper_names), set(target_hyper_names))

    def test_fixed_hyperparameters(self):
        factory = QuadCostFactory(self.system)
        factory.fix_Q_value("x", 0.0)
        factory.fix_F_value("y", 1.5)
        factory.fix_R_value("u", 2.0)
        cs = factory.get_config_space()
        self.assertIsInstance(cs, CS.ConfigurationSpace)

        hyper_names = cs.get_hyperparameter_names()
        target_hyper_names = ["y_Q", "x_F"]
        self.assertEqual(set(hyper_names), set(target_hyper_names))

        cfg = cs.get_default_configuration()

        factory.set_config(cfg)
        transformed_ocp = factory(self.ocp)
        cost = transformed_ocp.get_cost()

        self.assertIsInstance(cost, QuadCost)
        Q, R, F = cost.get_cost_matrices()
        
        self.assertTrue((Q == np.diag([0.0, 1.0])).all())
        self.assertTrue((F == np.diag([1.0, 1.5])).all())
        self.assertTrue((R == np.diag([2.0])).all())

    def test_adjust_bounds(self):
        factory = QuadCostFactory(self.system)
        factory.set_Q_bounds("x", 0.01, 50.0, 2.0, False)
        factory.set_F_bounds("y", 0.05, 25.0, 0.5, True)
        factory.set_R_bounds("u", 10.0, 20.0, 15.0, False)
        cs = factory.get_config_space()
        self.assertIsInstance(cs, CS.ConfigurationSpace)
        self.assertEqual(cs.get_hyperparameter("x_Q").lower, 0.01)
        self.assertEqual(cs.get_hyperparameter("x_Q").upper, 50.0)
        self.assertEqual(cs.get_hyperparameter("x_Q").default_value, 2.0)
        self.assertEqual(cs.get_hyperparameter("x_Q").log, False)
        self.assertEqual(cs.get_hyperparameter("y_F").lower, 0.05)
        self.assertEqual(cs.get_hyperparameter("y_F").upper, 25.0)
        self.assertEqual(cs.get_hyperparameter("y_F").default_value, 0.5)
        self.assertEqual(cs.get_hyperparameter("y_F").log, True)
        self.assertEqual(cs.get_hyperparameter("u_R").lower, 10.0)
        self.assertEqual(cs.get_hyperparameter("u_R").upper, 20.0)
        self.assertEqual(cs.get_hyperparameter("u_R").default_value, 15.0)
        self.assertEqual(cs.get_hyperparameter("u_R").log, False)
        self.assertEqual(cs.get_hyperparameter("x_F").lower, 1e-3)
        self.assertEqual(cs.get_hyperparameter("x_F").upper, 1e4)
        self.assertEqual(cs.get_hyperparameter("x_F").default_value, 1.0)
        self.assertEqual(cs.get_hyperparameter("x_F").log, True)

    def test_tunable_goal(self):
        factory = QuadCostFactory(self.system, goal=np.zeros(self.system.obs_dim))
        factory.set_tunable_goal("x", -10.0, 20.0, 10.0, False)
        cs = factory.get_config_space()
        self.assertIsInstance(cs, CS.ConfigurationSpace)
        self.assertEqual(cs.get_hyperparameter("x_Goal").lower, -10.0)
        self.assertEqual(cs.get_hyperparameter("x_Goal").upper, 20.0)
        self.assertEqual(cs.get_hyperparameter("x_Goal").default_value, 10.0)
        self.assertEqual(cs.get_hyperparameter("x_Goal").log, False)

        cfg = cs.get_default_configuration()
        cfg["x_Goal"] = 5.0
        factory.set_config(cfg)
        transformed_ocp = factory(self.ocp)
        cost = transformed_ocp.get_cost()
        self.assertTrue(np.allclose(cost._goal, np.array([5.0, 0.0])))

    def test_call_factory(self):
        factory = QuadCostFactory(self.system)
        cs = factory.get_config_space()
        cfg = cs.get_default_configuration()

        factory.set_config(cfg)
        ocp = factory(self.ocp)
        cost = ocp.get_cost()

        self.assertIsInstance(cost, QuadCost)
        Q, R, F = cost.get_cost_matrices()
        
        self.assertTrue((Q == np.eye(self.system.obs_dim)).all())
        self.assertTrue((F == np.eye(self.system.obs_dim)).all())
        self.assertTrue((R == np.eye(self.system.ctrl_dim)).all())

class SumCostTest(unittest.TestCase):
    def setUp(self):
        double_int = ampc.System(["x", "y"], ["u"])
        self.system = double_int

        Q1 = np.eye(2)
        R1 = np.eye(1)
        F1 = np.eye(2)
        goal1 = np.array([0.0, 0.0])
        self.cost1 = QuadCost(self.system, Q1, R1, F1, goal1)

        Q2 = np.diag([1.0, 2.0])
        R2 = 0.1 * np.eye(1)
        F2 = np.diag([1.0, 3.0])
        goal2 = np.array([0.0, 0.0])
        self.cost2 = QuadCost(self.system, Q2, R2, F2, goal2)

        Q3 = np.diag([0.0, 3.0])
        R3 = 0.5 * np.eye(1)
        F3 = np.diag([3.0, 0.0])
        goal3 = np.array([1.0, 0.0])
        self.cost3 = QuadCost(self.system, Q3, R3, F3, goal3)

    def test_operator_overload(self):
        sum1 = (self.cost1 + self.cost2) + self.cost3
        sum2 = self.cost1 + (self.cost2 + self.cost3)
        sum3 = self.cost1 + self.cost2 + self.cost3

        targ_costs = [self.cost1, self.cost2, self.cost3]
        for sum_cost in (sum1, sum2, sum3):
            self.assertEqual(len(sum_cost.costs), len(targ_costs))
            for cost, targ_cost in zip(sum_cost.costs, targ_costs):
                self.assertIs(cost, targ_cost)

    def test_properties(self):
        sum1 = self.cost1 + self.cost2
        sum2 = self.cost1 + self.cost3

        self.assertTrue(sum1.is_quad)
        self.assertTrue(sum1.has_goal)
        self.assertTrue(sum1.is_convex)
        self.assertTrue(sum1.is_diff)
        self.assertTrue(sum1.is_twice_diff)

        self.assertFalse(sum2.is_quad)
        self.assertFalse(sum2.has_goal)
        self.assertTrue(sum2.is_convex)
        self.assertTrue(sum2.is_diff)
        self.assertTrue(sum2.is_twice_diff)

    def test_evals(self):
        sum1 = self.cost1 + self.cost2 + self.cost3

        obs = np.array([-1, 1])

        res = sum1.eval_obs_cost(obs)
        self.assertEqual(res, 8)
        res, jac = sum1.eval_obs_cost_diff(obs)
        self.assertEqual(res, 8)
        self.assertTrue((jac == np.array([-4,12])).all())
        res, jac, hess = sum1.eval_obs_cost_hess(obs)
        self.assertEqual(res, 8)
        self.assertTrue((jac == np.array([-4,12])).all())
        self.assertTrue((hess == np.diag([4,12])).all())

class SumCostFactoryTest(unittest.TestCase):
    def setUp(self):
        double_int = ampc.System(["x", "y"], ["u"])
        self.system = double_int
        self.model = ARX(self.system)

        # Initialize ocp
        Q = np.eye(2)
        R = np.eye(1)
        F = np.eye(2)
        cost = QuadCost(self.system, Q, R, F, goal=[-1,0])
        self.ocp = OCP(self.system)
        self.ocp.set_cost(cost)
        self.ocp.set_ctrl_bound("u", -20.0, 20.0)

        # Generate trajectories
        self.trajs = uniform_random_generate(double_int, self.ocp,
                lambda y,u: dt_doubleint_dynamics(y,u,dt=0.05),
                np.random.default_rng(42), init_min=[-1.0, -1.0],
                init_max=[1.0, 1.0], traj_len=20, n_trajs=20)

    def test_config_space(self):
        factory1 = QuadCostFactory(self.system)
        factory2 = GaussRegFactory(self.system)

        sum_factory = factory1 + factory2
        cs = sum_factory.get_config_space()
        self.assertIsInstance(cs, CS.ConfigurationSpace)

        cfg = cs.get_default_configuration()
        cfg_dict = cfg.get_dictionary()
        extr_dicts = []
        for i in range(2):
            extr_dict = dict()
            prfx = "_sum_{}:".format(i)
            for key, val in cfg_dict.items():
                if key.startswith(prfx):
                    extr_key = key.split(":")[1]
                    extr_dict[extr_key] = val
            extr_dicts.append(extr_dict)
        cfg1_dict = factory1.get_default_config().get_dictionary()
        cfg2_dict = factory2.get_default_config().get_dictionary()
        self.assertEqual(extr_dicts[0], cfg1_dict)
        self.assertEqual(extr_dicts[1], cfg2_dict)

    def test_call(self):
        factory1 = QuadCostFactory(self.system)
        factory2 = GaussRegFactory(self.system)
        sum_factory = factory1 + factory2

        cfg = sum_factory.get_default_config()
        cfg1 = factory1.get_default_config()
        cfg2 = factory2.get_default_config()

        sum_factory.set_config(cfg)
        factory1.set_config(cfg1)
        factory2.set_config(cfg2)
        factory2.train(self.trajs)
        cost = sum_factory(self.ocp).get_cost()
        cost1 = factory1(self.ocp).get_cost()
        cost2 = factory2(self.ocp).get_cost()

        self.assertIsInstance(cost, SumCost)

        obs = np.array([-1, 2])
        val = cost.eval_obs_cost(obs)
        val1 = cost1.eval_obs_cost(obs)
        val2 = cost2.eval_obs_cost(obs)

        self.assertEqual(val, val1+val2)