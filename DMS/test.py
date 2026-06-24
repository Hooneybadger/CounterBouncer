from util import solution_check
import json
import numpy as np
import time
from myalgorithm import algorithm
from util import Order, Rider
import os
import copy

INF = int(1e9)

def get_scores(problem_folder, debug=False):
    score = []
    feasibility = []
    
    files = sorted(os.listdir(problem_folder))
    for file_name in files:
        file_path = os.path.join(problem_folder, file_name)
        if not os.path.isfile(file_path): continue
        
        res = get_result(file_path, debug=debug)
        feasibility.append(res["feasible"])
        if res["feasible"] == False:
            score.append(INF)
            print("wrong answer")
        if res['timelimit_exception']:
            score.append(INF)
            print("time limit exceeded")
        else:
            score.append(res["avg_cost"])
            print(f"cost:{res['avg_cost']}, time:{res['time']}, feasibility:{res['feasible']}")
    return np.mean(score), score, feasibility

def get_result(problem_file, default_timelimit = 180, debug=False)->float:
    with open(problem_file, 'r') as f:
        prob = json.load(f)

    K = prob['K']

    ALL_ORDERS = [Order(order_info) for order_info in prob['ORDERS']]
    ALL_RIDERS = [Rider(rider_info) for rider_info in prob['RIDERS']]

    DIST = np.array(prob['DIST'])
    for r in ALL_RIDERS:
        r.T = np.round(DIST/r.speed + r.service_time)

    timelimit = default_timelimit
    if "timelimit" in prob.keys():
        timelimit = prob["timelimit"]
        
    ## FOR TEST
    if K == 2000: timelimit = 300  # 1
    if K == 1000: timelimit = 300 # 5
    if K == 750: timelimit = 30 # 6
    if K == 500: timelimit = 15 # 8
    if K == 300: timelimit = 15 #10
        
    # run algo
    alg_start_time = time.time()
    exception = None
    solution = None
    if debug:
        solution = algorithm(K, copy.deepcopy(ALL_ORDERS), copy.deepcopy(ALL_RIDERS), copy.deepcopy(DIST), timelimit)
    else:
        try:
            # Run algorithm!
            solution = algorithm(K, copy.deepcopy(ALL_ORDERS), copy.deepcopy(ALL_RIDERS), copy.deepcopy(DIST), timelimit)
        except Exception as e:
            exception = f'{e}'
    alg_end_time = time.time()


    # check
    checked_solution = solution_check(K, ALL_ORDERS, ALL_RIDERS, DIST, solution)
    checked_solution['time'] = alg_end_time - alg_start_time
    checked_solution['timelimit_exception'] = (alg_end_time - alg_start_time) > timelimit + 1 # allowing additional 1 second!
    checked_solution['exception'] = exception
    checked_solution['prob_name'] = prob['name']

    return checked_solution



#print(get_scores("../data_to_test"))
print(get_scores("../data_to_test", debug = True))