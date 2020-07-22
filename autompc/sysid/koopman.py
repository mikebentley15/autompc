import numpy as np
import numpy.linalg as la
import scipy.linalg as sla
from pdb import set_trace
from sklearn.linear_model import  Lasso

from ..model import Model
import ConfigSpace as CS
import ConfigSpace.hyperparameters as CSH
import ConfigSpace.conditions as CSC

class Koopman(Model):
    def __init__(self, system, method, lasso_alpha_log10=None, poly_basis=False,
            poly_degree=1, trig_basis=False, trig_freq=1, product_terms=False):
        super().__init__(system)

        self.method = method
        if not lasso_alpha_log10 is None:
            self.lasso_alpha = 10**lasso_alpha_log10
        else:
            self.lasso_alpha = None
        if type(poly_basis) == str:
            poly_basis = True if poly_basis == "true" else False
        self.poly_basis = poly_basis
        self.poly_degree = poly_degree
        if type(trig_basis) == str:
            trig_basis = True if trig_basis == "true" else False
        self.trig_basis = trig_basis
        self.trig_freq = trig_freq
        if type(product_terms) == str:
            self.product_terms = True if product_terms == "true" else False

        self.basis_funcs = [lambda x: x]
        if self.poly_basis:
            self.basis_funcs += [lambda x: x**i for i in range(2, 1+self.poly_degree)]
        if self.trig_basis:
            for i in range(1, 1+self.poly_degree):
                self.basis_funcs += [lambda x: np.sin(i*x), lambda x : np.cos(i*x)]

    @staticmethod
    def get_configuration_space(system):
        cs = CS.ConfigurationSpace()
        method = CSH.CategoricalHyperparameter("method", choices=["lstsq", "lasso"])
        lasso_alpha_log10 = CSH.UniformFloatHyperparameter("lasso_alpha_log10", 
                lower=-10.0, upper=2.0, default_value=0.0)
        use_lasso_alpha = CSC.InCondition(child=lasso_alpha_log10, parent=method, 
                values=["lasso"])

        poly_basis = CSH.CategoricalHyperparameter("poly_basis", 
                choices=["true", "false"], default_value="false")
        poly_degree = CSH.UniformIntegerHyperparameter("poly_degree", lower=2, upper=8,
                default_value=3)
        use_poly_degree = CSC.InCondition(child=poly_degree, parent=poly_basis,
                values=["true"])

        trig_basis = CSH.CategoricalHyperparameter("trig_basis", 
                choices=["true", "false"], default_value="false")
        trig_freq = CSH.UniformIntegerHyperparameter("trig_freq", lower=1, upper=8,
                default_value=1)
        use_trig_freq = CSC.InCondition(child=trig_freq, parent=trig_basis,
                values=["true"])

        product_terms = CSH.CategoricalHyperparameter("product_terms",
                choices=["false"], default_value="false")


        cs.add_hyperparameters([method, lasso_alpha_log10, poly_basis, poly_degree,
            trig_basis, trig_freq, product_terms])
        cs.add_conditions([use_lasso_alpha, use_poly_degree, use_trig_freq])

        return cs


    def _transform_state(self, state):
        tr_state = [b(x) for b in self.basis_funcs for x in state]
        if self.product_terms:
            pr_terms = []
            for i, x in enumerate(tr_state):
                for j, y in enumerate(tr_state):
                    if i < j:
                        pr_terms.append(x*y)
            tr_state += pr_terms

        return np.array(tr_state)

    def traj_to_state(self, traj):
        return self._transform_state(traj[-1].obs[:])
    
    def update_state(self, state, new_ctrl, new_obs):
        return self._transform_state(new_obs)

    @property
    def state_dim(self):
        return len(self.basis_funcs) * self.system.obs_dim

    def train(self, trajs):
        X = np.concatenate([np.apply_along_axis(self._transform_state, 1, 
            traj.obs[:-1,:]) for traj in trajs]).T
        Y = np.concatenate([np.apply_along_axis(self._transform_state, 1, 
            traj.obs[1:,:]) for traj in trajs]).T
        U = np.concatenate([traj.ctrls[:-1,:] for traj in trajs]).T
        
        n = X.shape[0] # state dimension
        m = U.shape[0] # control dimension    
        
        XU = np.concatenate((X, U), axis = 0) # stack X and U together
        if self.method == "lstsq": # Least Squares Solution
            AB = np.dot(Y, sla.pinv2(XU))
            A = AB[:n, :n]
            B = AB[:n, n:]
        elif self.method == "lasso":  # Call lasso regression on coefficients
            print("Call Lasso")
            clf = Lasso(alpha=self.lasso_alpha)
            clf.fit(XU.T, Y.T)
            AB = clf.coef_
            A = AB[:n, :n]
            B = AB[:n, n:]
        elif self.method == 3: # Compute stable A, and B
            print("Compute Stable Koopman")
            # call function

        self.A, self.B = A, B

    def pred(self, state, ctrl):
        xpred = self.A @ state + self.B @ ctrl
        return xpred

    def pred_diff(self, state, ctrl):
        xpred = self.A @ state + self.B @ ctrl

        return xpred, np.copy(self.A), np.copy(self.B)

    def to_linear(self):
        return np.copy(self.A), np.copy(self.B)

    def get_parameters(self):
        return {"A" : np.copy(self.A),
                "B" : np.copy(self.B)}

    def set_parameters(self, params):
        self.A = np.copy(params["A"])
        self.B = np.copy(params["B"])
