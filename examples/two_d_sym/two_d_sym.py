'''
2d symmetric Example in Hylaa-Continuous
'''

import math

import numpy as np
from scipy.sparse import csr_matrix, csc_matrix

from hylaa.hybrid_automaton import LinearHybridAutomaton
from hylaa.engine import HylaaSettings
from hylaa.engine import HylaaEngine
from hylaa.settings import PlotSettings, SimulationSettings
from hylaa.star import Star

def define_ha():
    '''make the hybrid automaton'''

    ha = LinearHybridAutomaton()

    # with time and affine variable
    a_matrix = np.array([[0.5, 1], [1, 0.5]], dtype=float)
    a_matrix = csr_matrix(a_matrix, dtype=float)

    mode = ha.new_mode('mode')
    mode.set_dynamics(a_matrix)

    error = ha.new_mode('error')

    # x <= -20.0
    output_space = csr_matrix(([1.], [0], [0, 1]), shape=(1, 2), dtype=float)

    mat = csr_matrix(np.array([[1.]], dtype=float))
    rhs = np.array([-20.0], dtype=float)
    trans1 = ha.new_transition(mode, error)
    trans1.set_guard(output_space, mat, rhs)

    return ha

def make_init_star(ha, hylaa_settings):
    '''returns a star'''

    rv = None

    # vec1 is <1, 0> with the constraint that -2 <= vec1 <= -1.5
    # vec2 is <0, 1> with the constraint that 0.5 <= vec2 <= 1

    init_space = csc_matrix(np.array([[1., 0], [0, 1]], dtype=float).transpose())
    init_mat = csr_matrix(np.array([[1., 0], [-1, 0], [0, 1], [0, -1]], dtype=float))
    init_rhs = np.array([[-1.5], [2], [1], [-0.5]], dtype=float)

    rv = Star(hylaa_settings, ha.modes['mode'], init_space, init_mat, init_rhs)

    return rv

def define_settings():
    'get the hylaa settings object'
    plot_settings = PlotSettings()
    plot_settings.plot_mode = PlotSettings.PLOT_INTERACTIVE
    plot_settings.xdim_dir = 0
    plot_settings.ydim_dir = 1

    # save a video file instead
    #plot_settings.make_video("vid.mp4", frames=20, fps=5)

    plot_settings.num_angles = 128
    plot_settings.max_shown_polys = 2048
    plot_settings.label.y_label = '$y$'
    plot_settings.label.x_label = '$x$'
    plot_settings.label.title = 'Reachable States'
    plot_settings.plot_size = (12, 7)
    #plot_settings.label.big(size=48)
    

    settings = HylaaSettings(step=math.pi/4, max_time=3 * math.pi / 4, plot_settings=plot_settings)
    #settings.simulation.sim_mode = SimulationSettings.EXP_MULT
    #settings.simulation.sim_mode = SimulationSettings.MATRIX_EXP
    settings.simulation.sim_mode = SimulationSettings.KRYLOV
    settings.simulation.krylov_use_lanczos = True

    #settings.simulation.exp_mult_output_vec = False
    settings.simulation.check_answer = True

    return settings

def run_hylaa(hylaa_settings):
    'Runs hylaa with the given settings, returning the HylaaResult object.'
    ha = define_ha()
    init = make_init_star(ha, hylaa_settings)

    engine = HylaaEngine(ha, hylaa_settings)
    engine.run(init)

    return engine.result

if __name__ == '__main__':
    run_hylaa(define_settings())