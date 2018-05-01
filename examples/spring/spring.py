'''
Spring-Mass Example in Hylaa-Continuous


This is a spring-mass system, where there are two springs next to each mass, and the sides are rigid.
See simulate.py for a visualization.

This example is scalable, where the number of dimensions equals 2 times the number of masses. There
are no inputs (currently).
'''

import numpy as np
from scipy.sparse import csr_matrix, csc_matrix

from hylaa.hybrid_automaton import LinearHybridAutomaton, make_constraint_matrix, make_seperated_constraints
from hylaa.engine import HylaaSettings
from hylaa.engine import HylaaEngine
from hylaa.containers import PlotSettings, SimulationSettings
from hylaa.star import Star

def define_ha():
    '''make the hybrid automaton and return it'''

    ha = LinearHybridAutomaton()

    mode = ha.new_mode('mode')

    #num_masses = 100
    num_masses = 500 # 1 thousand dims
    #num_masses =  2500 # 5 thousand dims
    #num_masses = 5000 # 10 thousand dims -> 800 MB
    #num_masses = 50000 # 100 thousand dims -> memory error (80 GB mem needed)
    #num_masses = 500000 # one million dims (8 TB mem needed)
    #num_masses = 5000000 # ten million dims (800 TB mem needed)
    a_matrix = make_a_matrix(num_masses)
    mode.set_dynamics(csr_matrix(a_matrix))

    error = ha.new_mode('error')

    guard_matrix = csr_matrix(([1], [0], [0, 1]), shape=(1, a_matrix.shape[0]), dtype=float) # x0

    trans = ha.new_transition(mode, error)
    trans.set_guard(guard_matrix, np.array([-2.0], dtype=float)) # x0 <= -2

    return ha

def make_init_star(ha, hylaa_settings):
    '''returns a star'''

    rv = None
    bounds_list = []

    for dim in xrange(ha.dims):
        if dim == 1:
            lb = 0.6
            ub = 1.0
        else:
            lb = -0.2
            ub = 0.2

        bounds_list.append((lb, ub))

    if not hylaa_settings.simulation.seperate_constant_vars or \
            hylaa_settings.simulation.sim_mode != SimulationSettings.KRYLOV:
        init_mat, init_rhs = make_constraint_matrix(bounds_list)
        rv = Star(hylaa_settings, ha.modes['mode'], init_mat, init_rhs)
    else:
        init_mat, init_rhs, variable_dim_list, fixed_dim_tuples = make_seperated_constraints(bounds_list)

        rv = Star(hylaa_settings, ha.modes['mode'], init_mat, init_rhs, \
                  var_lists=[variable_dim_list], fixed_tuples=fixed_dim_tuples)

    return rv

def make_a_matrix(num_masses):
    '''get the A matrix corresponding to the dynamics for the given number of masses'''

    # construct as a csc_matrix
    values = []
    indices = []
    indptr = []

    num_dims = 2*num_masses

    for mass in xrange(num_masses):
        dim = 2*mass

        indptr.append(len(values))

        if dim - 1 >= 0:
            indices.append(dim-1)
            values.append(1.0)

        indices.append(dim+1)
        values.append(-2.0)

        if dim + 3 < num_dims:
            indices.append(dim + 3)
            values.append(1.0)

        indptr.append(len(values))

        indices.append(dim)
        values.append(1.0)

    indptr.append(len(values))

    return csc_matrix((values, indices, indptr), shape=(num_dims, num_dims), dtype=float)

def define_settings(_):
    'get the hylaa settings object'
    plot_settings = PlotSettings()
    plot_settings.plot_mode = PlotSettings.PLOT_NONE

    plot_settings.xdim_dir = 0
    plot_settings.ydim_dir = 1

    # save a video file instead
    # plot_settings.make_video("vid.mp4", frames=220, fps=40)

    plot_settings.num_angles = 128
    plot_settings.max_shown_polys = 2048
    plot_settings.label.y_label = 'Vel'
    plot_settings.label.x_label = 'Pos'
    plot_settings.label.title = ''
    #plot_settings.label.axes_limits = (0, 1, -0.007, 0.006)
    plot_settings.plot_size = (12, 10)
    plot_settings.label.big(size=32)

    settings = HylaaSettings(step=0.01, max_time=10.0, plot_settings=plot_settings)

    settings.simulation.sim_mode = SimulationSettings.KRYLOV
    #settings.simulation.krylov_use_gpu = True
    #settings.simulation.krylov_profiling = True
    #settings.simulation.check_answer = True

    #settings.simulation.sim_mode = SimulationSettings.EXP_MULT

    settings.simulation.pipeline_arnoldi_expm = False
    settings.simulation.seperate_constant_vars = True
    settings.simulation.guard_mode = SimulationSettings.GUARD_DECOMPOSED

    return settings

def run_hylaa():
    'Runs hylaa with the given settings, returning the HylaaResult object.'

    print "Creating automaton..."
    ha = define_ha()
    settings = define_settings(ha)

    print "Defining initial states..."
    init = make_init_star(ha, settings)

    engine = HylaaEngine(ha, settings)

    print "Starting computation..."
    engine.run(init)

    return engine.result

if __name__ == '__main__':
    run_hylaa()