'''
Time Elapse for the Krylov method using CPU or GPU
'''

import math
import time

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import expm
from scipy.integrate import odeint

from hylaa.timerutil import Timers
from hylaa.settings import HylaaSettings
from hylaa.util import safe_zeros

def odeint_sim(arg):
    '''
    simulate a given dense a-matrix with the provided initial vector, for a certain number of steps,
    returning the result at each step

    arg is tuple (a_matrix, start_vec, settings)
    '''

    a_matrix, start_vec, settings = arg

    assert a_matrix.shape[1] > 0
    assert isinstance(start_vec, np.ndarray)
    assert isinstance(settings, HylaaSettings)

    step = settings.step
    num_steps = settings.num_steps
    sim_tol = settings.simulation.krylov_odeint_simtol

    if isinstance(a_matrix, np.ndarray):
        # was arnoldi iteration, a_matrix (H) is a dense matrix
        der_func = lambda state, _: np.dot(a_matrix, state)
        a_transpose = a_matrix.transpose().copy()
        jac_func = lambda dummy_state, dummy_t: a_transpose
    else:
        # was lanczos iteration, a_matrix (H) is a sparse matrix
        assert isinstance(a_matrix, csr_matrix)
        der_func = lambda state, _: (a_matrix * state)
        jac_func = None

    times = np.linspace(0, step * num_steps, num=num_steps+1)

    Timers.tic('odeint')
    result = odeint(der_func, start_vec, times, Dfun=jac_func, col_deriv=True, atol=sim_tol, rtol=sim_tol, \
            mxstep=int(1e8)) # mxstep = maximum number of internal steps
    Timers.toc('odeint')

    return result

def format_secs(sec):
    'convert seconds (float) to a human-readable string'

    rv = ""

    if sec < 60:
        rv = "{:.2f} secs".format(sec)
    elif sec < 60 * 60:
        rv = "{:.2f} mins".format(sec / 60.0)
    elif sec < 60 * 60 * 48:
        rv = "{:.2f} hours".format(sec / 60.0 / 60.0)
    else:
        rv = "{:.2f} days".format(sec / 60.0 / 60.0 / 24.0)

    return rv

#def check_available_memory_basis(stdout, s, k, i):
#    'check if enough memory is available to store the basis matrix'

#    required_mb = (s * k * i * 8) / 1024.0 / 1024.0
#    available_mb = get_free_memory_mb()

#    if stdout:
#        print "Basis Matrix Required GB = {:.3f} (+1), available GB = {:.3f} (s = {}, k = {}, i+1 = {})".format(
#            required_mb / 1024.0, available_mb / 1024.0, s, k, i)

#    if required_mb + 1024 > available_mb: # add 1024 mb since we want 1 GB free for other things
#        raise MemoryError("Not enogh memory for storing the basis matrices.")

def init_krylov(time_elapser):
    '''
    initialize krylov interface for the computation

    returns a list of empty matrices to be filled in by the subsequent computation
    '''

    settings = time_elapser.settings
    key_dir_mat = time_elapser.key_dir_mat
    init_space_csc = time_elapser.init_space_csc

    # check available memory before computing
    #i = time_elapser.init_space_csc.shape[1]
    #check_available_memory_basis(settings.print_output, time_elapser.settings.num_steps, key_dir_mat.shape[0], i)

    time_elapser.stats['arnoldi_iter'] = []
    #time_elapser.stats['arnoldi_mem_start'] = get_free_memory_mb()

    rv = []

    # initialize step zero

    step_zero_mat = (key_dir_mat * init_space_csc).toarray()

    rv.append(step_zero_mat)

    if settings.print_output:
        print "Basis matrix shape: {}".format(step_zero_mat.shape)

    safe_zeros('full_basis_matrix', (time_elapser.settings.num_steps * rv[0].shape[0], rv[0].shape[1]), \
                   dtype=float, alloc=False)
        
    # add zeros (allocate storage for result)
    for _ in xrange(0, time_elapser.settings.num_steps):
        rv.append(safe_zeros('basis_matrix', rv[0].shape, dtype=float))

    return rv

def compute_error(correct, estimate, is_relative):
    '''compute the error between two vectors
    if is_relative is False, then this computes the maximum absolute error
    '''

    return relative_error(correct, estimate) if is_relative else absolute_error(correct, estimate)

def absolute_error(correct, estimate):
    'compute maximum absolute error between entries in two vectors'

    rv = abs(correct[0] - estimate[0])

    for i in xrange(2, len(correct)):
        rv = max(rv, abs(correct[i] - estimate[i]))

    return rv

def relative_error(correct, estimate):
    'compute the relative error between the correct value and an estimate'

    rel_error = 1.0e16 # large error is returned if it can't be computed due to numerical issues

    try:
        norm = np.linalg.norm(correct)

        if not math.isinf(norm) and not math.isnan(norm):
            if norm < 1e-13: # if norm is small, return absolute error
                rel_error = norm
            else:
                diff = correct - estimate

                abs_error = np.linalg.norm(diff)

                if not math.isinf(abs_error) and not math.isnan(abs_error):
                    rel_error = abs_error / norm
    except FloatingPointError:
        pass

    assert not math.isinf(rel_error) and not math.isnan(rel_error)

    return rel_error

def get_error(settings, h_mat, pv_mat, arnoldi_iter=None, return_sim=False, limit=None):
    '''
    Get the error given the h and pv matrices, for the given number of arnoldi_iterations.
    If arnoldi_iter is None, then use the full passed-in matrices.

    This compares the error at all time steps.

    If return_sim is True, then a tuple is returned where the second element is list of the
    sim points at each time step.

    if limit is not None, this will break as soon as the error exceeds the limit
    '''

    assert h_mat.shape[0] > 1

    sim = None
    use_rel_error = settings.simulation.krylov_use_rel_error
    error = 0

    # use less arnoldi iterations than what's in the matrices
    if arnoldi_iter is not None:
        h_mat = h_mat[:arnoldi_iter, :arnoldi_iter].copy()
        pv_mat = pv_mat[:, :arnoldi_iter].copy()

    if limit is not None or arnoldi_iter is not None:
        small_h_mat = h_mat[:-1, :-1].copy()
        small_pv_mat = pv_mat[:, :-1].copy()

    if settings.simulation.krylov_use_odeint:
        Timers.tic('get_error odeint')
        start_vec = np.array([1.0 if d == 0 else 0.0 for d in xrange(h_mat.shape[0])], dtype=float)

        if limit is None:
            full_sim = odeint_sim((h_mat, start_vec, settings))

            sim = safe_zeros('projected_sim', (full_sim.shape[0] - 1, pv_mat.shape[0]), dtype=float)

            for i in xrange(1, full_sim.shape[0]): # skip step zero
                sim[i-1] = np.dot(pv_mat, full_sim[i])
        else:
            small_start_vec = start_vec[:-1].copy()
            args = [(h_mat, start_vec, settings), (small_h_mat, small_start_vec, settings)]

            full_sim, small_full_sim = [odeint_sim(a) for a in args]

            if np.all(abs(full_sim[1]) < 1e-9): # was compare with new zeros vec
                if settings.print_output:
                    print "First step of simulation was almost all zeros... increasing num iterations"

                error = limit + 1

            # sample last / middle / first before going through the whole thing
            steps = full_sim.shape[0]

            for step in [steps-1, steps / 2, 1]:
                cur_result = np.dot(pv_mat, full_sim[step])
                small_result = np.dot(small_pv_mat, small_full_sim[step])

                error = max(error, compute_error(cur_result, small_result, use_rel_error))

                if error > limit:
                    if settings.print_output:
                        print "Sim error with {} krylov iterations ({}) above limit ({})".format(
                            h_mat.shape[0], error, limit)
                    break

            if error < limit: # go through each step
                Timers.tic('krylov multiply by PV')

                if settings.print_output:
                    print "Sim error with {} iter at sampled times was low enough, checking all steps...".format(
                        h_mat.shape[0])

                sim = np.dot(full_sim[1:], pv_mat.T)

                for step in xrange(0, sim.shape[0]):
                    cur_result = sim[step]
                    small_result = np.dot(small_pv_mat, small_full_sim[step + 1])

                    error = max(error, compute_error(cur_result, small_result, use_rel_error))

                    if error > limit:
                        if settings.print_output:
                            print "Simulation error at step {} exceeds threshold: {} (limit: {})".format(
                                step, error, limit)

                        sim = None
                        break

                if settings.print_output and error < limit:
                    print "Simulation error was low enough at all steps: {} (limit: {})".format(error, limit)

                Timers.toc('krylov multiply by PV')

        Timers.toc('get_error odeint')
    else:
        Timers.tic('get_error expm')
        matrix_exp = expm(settings.step * h_mat)
        cur_col = matrix_exp[:, 0]
        Timers.toc('get_error expm')

        # for accuracy check
        Timers.tic('get_error expm')
        small_matrix_exp = expm(settings.step * small_h_mat) # step time is already included in loaded a_mat
        small_col = small_matrix_exp[:, 0]
        Timers.toc('get_error expm')

        # do the comparison at the first step
        cur_result = np.dot(pv_mat, cur_col)
        small_result = np.dot(small_pv_mat, small_col)
        error = max(error, compute_error(cur_result, small_result, use_rel_error))

        if return_sim:
            sim = [cur_result]

        for step in xrange(2, settings.num_steps + 1):
            cur_col = np.dot(matrix_exp, cur_col)
            small_col = np.dot(small_matrix_exp, small_col)

            # maybe we want to check error in the middle as well
            cur_result = np.dot(pv_mat, cur_col)
            small_result = np.dot(small_pv_mat, small_col)
            error = max(error, compute_error(cur_result, small_result, use_rel_error))

            if return_sim:
                sim.append(cur_result)

            if limit is not None and error > limit:
                if settings.print_output:
                    print "Error {} exceeded limit {} at step {}".format(error, limit, step)

                break

    return error if not return_sim else (error, sim)

def print_error_at_each_step(settings, h_mat, pv_mat):
    '''
    a profiling function. If this is used, output a file with the error for every number of
    arnoldi iteartions, and then quit.
    '''

    filename = 'error.dat'

    print "Printing errors to file: {}".format(filename)

    max_iter = h_mat.shape[0]

    with open(filename, 'w') as f:

        for aiter in xrange(2, max_iter):
            max_error = 0.0

            error = get_error(settings, h_mat, pv_mat, arnoldi_iter=aiter)
            max_error = max(max_error, error)

            if aiter % 10 == 0:
                print "Computed Error {} / {}: {:.25f}".format(aiter, max_iter, error)

            line = "{}\t{:.25f}\n".format(aiter, max_error)
            #print line,
            f.write(line)

    print "print_error_at_each_step data written to {}, exiting".format(filename)
    exit(1)

def arnoldi_sim_with_max_error(time_elapser, init_vec_csr, iterations, error_limit):
    '''
    Run an arnoldi simulation with a fixed number of iterations and a target max error.
    If error_limit is None, just run the whole simulation.

    returns a 2-tuple (a, b) with:
    a: projected simulation at each step, or None if the error limit is exceeded.
    b: the number of arnoldi iterations actually used
    '''

    settings = time_elapser.settings
    stdout = settings.simulation.krylov_stdout
    error = None

    pv_mat, h_mat = time_elapser.krylov_iterator.run_iteration(init_vec_csr, iterations)

    # profiling was desired
    if settings.simulation.krylov_error_stats_iterations is not None:
        print_error_at_each_step(settings, h_mat, pv_mat)

    if stdout:
        print "Finished {}... checking error at each step".format( \
            "Lanczos" if settings.simulation.krylov_lanczos else "Arnoldi")

    if h_mat.shape[0] <= iterations:
        error_limit = None
        iterations = h_mat.shape[0]

        if stdout:
            print "Arnoldi terminated early. Simulating without error limit."

    h_mat = h_mat[:-1, :].copy()
    pv_mat = pv_mat[:, :-1].copy()

    error, projected_sim = get_error(settings, h_mat, pv_mat, return_sim=True, limit=error_limit)

    if error_limit is not None and error == 0 and not settings.simulation.krylov_add_ones_key_dir:
        if stdout:
            print "Error was zero and didn't add ones row to key directions. Increasing iterations."

        rv = None

    elif error_limit is None or error < error_limit:
        if stdout and error_limit is not None:
            print "Error {} was below threshold: {}".format(error, error_limit)

        rv = projected_sim
    else:
        rv = None

    return rv, iterations

# projected_simulation = arnoldi_projected_simulation(time_elapser, init_vec)
def arnoldi_sim_autotune(time_elapser, init_vec_csr):
    '''
    Perform a projected simulation from a given initial vector. This auto-tunes the number
    of arnoldi iterations based on the error.

    returns the projected simulation at each step.
    '''

    settings = time_elapser.settings
    stdout = settings.simulation.krylov_stdout
    n = time_elapser.a_matrix.shape[0]

    error_limit = settings.simulation.krylov_target_error

    arnoldi_iter = 4
    sim = None

    # if profiling was desired
    if settings.simulation.krylov_error_stats_iterations is not None:
        arnoldi_iter = settings.simulation.krylov_error_stats_iterations

    while True:
        if arnoldi_iter >= n:
            arnoldi_iter = n
            error_limit = None # do not target any error in this case

            if stdout:
                print "Arnoldi iter ({}) reached system dimension; skipping error".format(arnoldi_iter)

        if stdout:
            print "Trying {} {} iterations...".format(arnoldi_iter, \
                "Arnoldi" if not settings.simulation.krylov_lanczos else "Lanczos")

        sim, arnoldi_iter = arnoldi_sim_with_max_error(time_elapser, init_vec_csr, arnoldi_iter, error_limit)

        if sim is not None:
            break
        else:
            arnoldi_iter = int(arnoldi_iter * 1.5)

    # update max used memory
    #prev_mem = time_elapser.stats['min_free_memory']
    #time_elapser.stats['min_free_memory'] = min(prev_mem, get_free_memory_mb('update_mem'))

    time_elapser.krylov_iterator.reset() # done with the current start vector, free memory

    if stdout:
        print "Simulation was accurate enough with {} arnoldi iterations...".format(arnoldi_iter)

    time_elapser.stats['arnoldi_iter'].append(arnoldi_iter)

    return sim

def assign_from_sim(rv, sim, index, settings):
    'assign a simulation to the result object'

    assert len(sim) == len(rv) - 1, "Got sim of length {}, expected {}".format(len(sim), len(rv) - 1)
    Timers.tic('update result list')

    for i in xrange(len(sim)):

        if settings.simulation.krylov_add_ones_key_dir:
            piece = sim[i][:-1]
        else:
            piece = sim[i][:]

        if settings.simulation.krylov_transpose:
            rv[i+1][index] = piece
        else:
            rv[i+1][:, index] = piece

    Timers.toc('update result list')

def make_cur_basis_mat_list(time_elapser):
    '''
    Main work function. This returns the basis matrix at every step.

    This is called one time, and returns a list, element N is the basis matrix at step N
    '''

    # numpy raise errors overflow errors, ignore underflow
    np.seterr(all='warn', over='raise', under='ignore')

    settings = time_elapser.settings

    rv = init_krylov(time_elapser)

    if settings.simulation.krylov_transpose:
        init_space = time_elapser.key_dir_mat
    else:
        init_space = csr_matrix(time_elapser.init_space_csc.transpose())

    start = last_print = time.time()
    num_init_vecs = init_space.shape[0]

    if settings.print_output:
        print "Simulating from {} initial vector(s)".format(num_init_vecs)

    for init_index in xrange(num_init_vecs):
        sim = arnoldi_sim_autotune(time_elapser, init_space[init_index])

        assign_from_sim(rv, sim, init_index, settings)

        if settings.print_output:
            now = time.time()

            if now - last_print > 1.0: # print every second
                last_print = now
                frac = float(init_index) / num_init_vecs

                if frac > 1e-9:
                    elapsed_sec = now - start
                    total_sec = elapsed_sec / frac
                    eta_sec = total_sec - elapsed_sec
                    eta = format_secs(eta_sec)

                    print "Arnoldi {} / {} ({:.2f}%, ETA: {})".format(
                        init_index, num_init_vecs, 100.0 * frac, eta)

    if settings.print_output:
        elapsed = format_secs(time.time() - start)
        print "Krylov Simulation Total Time: {}\n".format(elapsed)

    # restore numpy error
    np.seterr(all='warn')

    return rv
